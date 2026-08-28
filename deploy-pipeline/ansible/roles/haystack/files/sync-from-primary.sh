#!/usr/bin/env bash
# Merge-sync heavy_rental from REST API postgres-primary into local Haystack db.
# Spec: Haystack-Fast-API/specs/001-haystack-postgres-merge-sync/
# Contract: contracts/db-sync-env.md
#
# Env (defaults):
#   SOURCE_HOST=postgres-primary SOURCE_PORT=5432 SOURCE_USER=postgres
#   SOURCE_PASSWORD=postgres SOURCE_DB=heavy_rental
#   TARGET_HOST=postgres-haystack TARGET_PORT=5432 TARGET_USER=postgres
#   TARGET_PASSWORD=postgres TARGET_DB=heavy_rental
#   STAGING_SCHEMA=primary_snapshot
#   SYNC_INTERVAL_SECONDS=60
#   HALT_ON_PRIMARY_UNAVAILABLE=false
#   PRIMARY_CHECK_RETRIES=5 PRIMARY_CHECK_DELAY_SECONDS=3
#   SCHEMA_EVOLUTION=true          # ADD COLUMN for missing source columns on existing tables
#   ALLOW_UNIQUE_MERGE_KEY=true    # use UNIQUE when no PK
#   SOURCE_SCHEMAS=public          # comma-list; multi-schema beyond public deferred (public only for now)
#   SYNC_MODE=merge|mirror         # mirror enables opt-in parity flags (see apply_sync_mode)
#   DROP_ORPHAN_COLUMNS=false      # drop local columns missing on primary (data loss)
#   SYNC_INDEXES=false             # create non-unique secondary indexes from primary
#   SYNC_UNIQUE_INDEXES=false      # also create unique secondary indexes
#   SAFE_TYPE_WIDENINGS=false      # apply whitelisted type widenings only
#   SYNC_FOREIGN_KEYS=false        # reserved / not implemented (NOT VALID FKs) — logged if true
#   SYNC_TABLE_ALLOWLIST=asset,booking,category
#       # comma-separated public relation names (Phase 4 T2 / D0). Use "all" or "*" for full public merge.
#   NEO4J_POPULATE_TRIGGER_URL=http://neo4j-populate:8089/v1/populate
#       # Phase 8.2 T4: best-effort POST after successful merge (empty disables).
#   NEO4J_POPULATE_TRIGGER_TIMEOUT_SECONDS=5
#   NEO4J_POPULATE_TRIGGER_TOKEN=   # optional X-Populate-Token
set -euo pipefail

SOURCE_HOST="${SOURCE_HOST:-postgres-primary}"
SOURCE_PORT="${SOURCE_PORT:-5432}"
SOURCE_USER="${SOURCE_USER:-postgres}"
SOURCE_PASSWORD="${SOURCE_PASSWORD:-postgres}"
SOURCE_DB="${SOURCE_DB:-heavy_rental}"

TARGET_HOST="${TARGET_HOST:-postgres-haystack}"
TARGET_PORT="${TARGET_PORT:-5432}"
TARGET_USER="${TARGET_USER:-postgres}"
TARGET_PASSWORD="${TARGET_PASSWORD:-postgres}"
TARGET_DB="${TARGET_DB:-heavy_rental}"

STAGING_SCHEMA="${STAGING_SCHEMA:-primary_snapshot}"
SYNC_INTERVAL_SECONDS="${SYNC_INTERVAL_SECONDS:-60}"
HALT_ON_PRIMARY_UNAVAILABLE="${HALT_ON_PRIMARY_UNAVAILABLE:-false}"
PRIMARY_CHECK_RETRIES="${PRIMARY_CHECK_RETRIES:-5}"
PRIMARY_CHECK_DELAY_SECONDS="${PRIMARY_CHECK_DELAY_SECONDS:-3}"
SCHEMA_EVOLUTION="${SCHEMA_EVOLUTION:-true}"
ALLOW_UNIQUE_MERGE_KEY="${ALLOW_UNIQUE_MERGE_KEY:-true}"
SOURCE_SCHEMAS="${SOURCE_SCHEMAS:-public}"
SYNC_MODE="${SYNC_MODE:-merge}"
DROP_ORPHAN_COLUMNS="${DROP_ORPHAN_COLUMNS:-false}"
SYNC_INDEXES="${SYNC_INDEXES:-false}"
SYNC_UNIQUE_INDEXES="${SYNC_UNIQUE_INDEXES:-false}"
SAFE_TYPE_WIDENINGS="${SAFE_TYPE_WIDENINGS:-false}"
SYNC_FOREIGN_KEYS="${SYNC_FOREIGN_KEYS:-false}"
# Phase 4 T2: deterministic fleet table set (D0 schema-contract.md). "all"/"*" = every public table.
SYNC_TABLE_ALLOWLIST="${SYNC_TABLE_ALLOWLIST:all}"
# Phase 8.2 T4 / PR-M: fire fleet Neo4j populate after successful merge (non-blocking for sync).
NEO4J_POPULATE_TRIGGER_URL="${NEO4J_POPULATE_TRIGGER_URL:-}"
NEO4J_POPULATE_TRIGGER_TIMEOUT_SECONDS="${NEO4J_POPULATE_TRIGGER_TIMEOUT_SECONDS:-5}"
NEO4J_POPULATE_TRIGGER_TOKEN="${NEO4J_POPULATE_TRIGGER_TOKEN:-}"

FDW_SERVER_NAME="${FDW_SERVER_NAME:-haystack_primary_src}"

# Allowlist mode: "all" when SYNC_TABLE_ALLOWLIST is all/*; else "list" with ALLOWLIST_TABLES array.
ALLOWLIST_MODE="list"
ALLOWLIST_TABLES=()
CANDIDATE_TABLES=()
SKIPPED_NOT_ALLOWLISTED=0
MERGED_COUNT=0
SKIPPED_NO_KEY=0

parse_table_allowlist() {
  local raw trimmed
  raw="${SYNC_TABLE_ALLOWLIST// /}"
  trimmed="${raw,,}"
  ALLOWLIST_TABLES=()
  if [[ -z "$raw" || "$trimmed" == "all" || "$raw" == "*" ]]; then
    ALLOWLIST_MODE="all"
    log "SYNC_TABLE_ALLOWLIST mode=all (merge every public table with a merge key)"
    return 0
  fi
  ALLOWLIST_MODE="list"
  IFS=',' read -ra ALLOWLIST_TABLES <<< "$raw"
  # Drop empty entries
  local cleaned=()
  local t
  for t in "${ALLOWLIST_TABLES[@]}"; do
    t=$(echo "$t" | tr -d '[:space:]')
    [[ -n "$t" ]] && cleaned+=("$t")
  done
  ALLOWLIST_TABLES=("${cleaned[@]}")
  if ((${#ALLOWLIST_TABLES[@]} == 0)); then
    log "WARN: SYNC_TABLE_ALLOWLIST empty after parse; treating as mode=all"
    ALLOWLIST_MODE="all"
    return 0
  fi
  log "SYNC_TABLE_ALLOWLIST mode=list tables=${ALLOWLIST_TABLES[*]}"
}

table_in_allowlist() {
  local table="$1" t
  if [[ "$ALLOWLIST_MODE" == "all" ]]; then
    return 0
  fi
  for t in "${ALLOWLIST_TABLES[@]}"; do
    if [[ "$t" == "$table" ]]; then
      return 0
    fi
  done
  return 1
}

# Epoch milliseconds (GNU date; postgres:17 image)
now_ms() {
  date +%s%3N 2>/dev/null || echo $(($(date +%s) * 1000))
}

# When SYNC_MODE=mirror, turn on sandbox-breaking parity flags unless already set by env.
# (Values already true/false from env above; mirror forces opt-ins on.)
apply_sync_mode() {
  case "${SYNC_MODE,,}" in
    mirror)
      DROP_ORPHAN_COLUMNS=true
      SAFE_TYPE_WIDENINGS=true
      SYNC_INDEXES=true
      SYNC_UNIQUE_INDEXES=true
      SYNC_FOREIGN_KEYS=true
      log "SYNC_MODE=mirror: enabling DROP_ORPHAN_COLUMNS, SAFE_TYPE_WIDENINGS, SYNC_INDEXES, SYNC_UNIQUE_INDEXES, SYNC_FOREIGN_KEYS"
      ;;
    merge|"")
      SYNC_MODE=merge
      ;;
    *)
      log "WARN: unknown SYNC_MODE=${SYNC_MODE}; treating as merge"
      SYNC_MODE=merge
      ;;
  esac
}

log() {
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

is_truthy() {
  case "${1,,}" in
    true|1|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

target_psql() {
  PGPASSWORD="$TARGET_PASSWORD" psql \
    -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d "$TARGET_DB" \
    -v ON_ERROR_STOP=1 "$@"
}

source_psql() {
  PGPASSWORD="$SOURCE_PASSWORD" psql \
    -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d "$SOURCE_DB" \
    -v ON_ERROR_STOP=1 "$@"
}

wait_for_target() {
  log "Waiting for target ${TARGET_HOST}:${TARGET_PORT}/${TARGET_DB} ..."
  local attempt=0
  until pg_isready -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d "$TARGET_DB" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if (( attempt % 6 == 0 )); then
      log "Still waiting for target (attempt ${attempt}) ..."
    fi
    sleep 2
  done
  log "Target database is ready"
}

source_available() {
  local i
  for ((i = 1; i <= PRIMARY_CHECK_RETRIES; i++)); do
    if pg_isready -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d "$SOURCE_DB" >/dev/null 2>&1; then
      if PGPASSWORD="$SOURCE_PASSWORD" psql \
        -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d "$SOURCE_DB" \
        -v ON_ERROR_STOP=1 -t -A -c "SELECT 1" >/dev/null 2>&1; then
        return 0
      fi
    fi
    log "Source check ${i}/${PRIMARY_CHECK_RETRIES} failed for ${SOURCE_HOST}:${SOURCE_PORT}"
    if (( i < PRIMARY_CHECK_RETRIES )); then
      sleep "$PRIMARY_CHECK_DELAY_SECONDS"
    fi
  done
  return 1
}

quote_ident() {
  local ident="$1"
  ident="${ident//\"/\"\"}"
  printf '"%s"' "$ident"
}

csv_to_quoted_list() {
  local csv="$1" col qcol out="" sep=""
  IFS=',' read -ra arr <<< "$csv"
  for col in "${arr[@]}"; do
    [[ -z "$col" ]] && continue
    qcol=$(quote_ident "$col")
    out+="${sep}${qcol}"
    sep=", "
  done
  printf '%s' "$out"
}

setup_fdw() {
  log "Ensuring postgres_fdw and foreign server ${FDW_SERVER_NAME}"
  target_psql <<SQL
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

DO \$\$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_foreign_server WHERE srvname = '${FDW_SERVER_NAME}') THEN
    EXECUTE format('DROP SERVER %I CASCADE', '${FDW_SERVER_NAME}');
  END IF;
END
\$\$;

CREATE SERVER ${FDW_SERVER_NAME}
  FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (
    host '${SOURCE_HOST}',
    port '${SOURCE_PORT}',
    dbname '${SOURCE_DB}'
  );

CREATE USER MAPPING IF NOT EXISTS FOR CURRENT_USER
  SERVER ${FDW_SERVER_NAME}
  OPTIONS (user '${SOURCE_USER}', password '${SOURCE_PASSWORD}');

DO \$\$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${TARGET_USER}') THEN
    BEGIN
      EXECUTE format(
        'CREATE USER MAPPING IF NOT EXISTS FOR %I SERVER %I OPTIONS (user %L, password %L)',
        '${TARGET_USER}', '${FDW_SERVER_NAME}', '${SOURCE_USER}', '${SOURCE_PASSWORD}'
      );
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;
  END IF;
END
\$\$;
SQL
}

# Build LIMIT TO clause for FDW when allowlist is finite.
fdw_limit_to_clause() {
  if [[ "$ALLOWLIST_MODE" != "list" ]] || ((${#ALLOWLIST_TABLES[@]} == 0)); then
    echo ""
    return 0
  fi
  local parts=() t qt
  for t in "${ALLOWLIST_TABLES[@]}"; do
    qt=$(quote_ident "$t")
    parts+=("${qt}")
  done
  local joined
  joined=$(IFS=', '; echo "${parts[*]}")
  echo "LIMIT TO (${joined})"
}

refresh_staging() {
  log "Refreshing staging schema ${STAGING_SCHEMA}"
  local limit_clause
  limit_clause=$(fdw_limit_to_clause)
  if [[ -n "$limit_clause" ]]; then
    log "FDW IMPORT FOREIGN SCHEMA public ${limit_clause}"
  else
    log "FDW IMPORT FOREIGN SCHEMA public (all tables)"
  fi
  target_psql <<SQL
DROP SCHEMA IF EXISTS $(quote_ident "$STAGING_SCHEMA") CASCADE;
CREATE SCHEMA $(quote_ident "$STAGING_SCHEMA");
IMPORT FOREIGN SCHEMA public
  ${limit_clause}
  FROM SERVER ${FDW_SERVER_NAME}
  INTO $(quote_ident "$STAGING_SCHEMA");
SQL
}

list_source_tables() {
  source_psql -t -A -c \
    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
}

# Fill global CANDIDATE_TABLES array from source public tables + allowlist (Phase 4 T2).
# Must run in the main shell (not process substitution) so SKIPPED_NOT_ALLOWLISTED is visible.
filter_merge_candidates() {
  local all_tables t
  CANDIDATE_TABLES=()
  SKIPPED_NOT_ALLOWLISTED=0
  mapfile -t all_tables < <(list_source_tables | sed '/^$/d')
  for t in "${all_tables[@]}"; do
    t=$(echo "$t" | tr -d '[:space:]')
    [[ -z "$t" ]] && continue
    if table_in_allowlist "$t"; then
      CANDIDATE_TABLES+=("$t")
    else
      SKIPPED_NOT_ALLOWLISTED=$((SKIPPED_NOT_ALLOWLISTED + 1))
      log "SKIP table public.${t}: not in SYNC_TABLE_ALLOWLIST"
    fi
  done
}

# Sets globals: MERGE_KEY_KIND (pk|unique|), MERGE_KEY_COLS (csv)
get_merge_key() {
  local table="$1"
  MERGE_KEY_KIND=""
  MERGE_KEY_COLS=""

  local pk_cols
  pk_cols=$(source_psql -t -A -c "
SELECT string_agg(a.attname, ',' ORDER BY u.ord)
FROM pg_index i
JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS u(attnum, ord) ON true
JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = u.attnum AND NOT a.attisdropped
WHERE i.indrelid = format('%I.%I', 'public', '${table}')::regclass
  AND i.indisprimary;
" | tr -d '[:space:]')

  if [[ -n "$pk_cols" ]]; then
    MERGE_KEY_KIND="pk"
    MERGE_KEY_COLS="$pk_cols"
    return 0
  fi

  if ! is_truthy "$ALLOW_UNIQUE_MERGE_KEY"; then
    return 0
  fi

  # Prefer fewest columns, then constraint name (stable). Non-partial unique constraints only.
  local uk_cols
  uk_cols=$(source_psql -t -A -c "
SELECT cols FROM (
  SELECT
    c.conname,
    (SELECT count(*) FROM unnest(c.conkey)) AS ncol,
    (
      SELECT string_agg(a.attname, ',' ORDER BY u.ord)
      FROM unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord)
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = u.attnum AND NOT a.attisdropped
    ) AS cols
  FROM pg_constraint c
  WHERE c.conrelid = format('%I.%I', 'public', '${table}')::regclass
    AND c.contype = 'u'
) s
WHERE cols IS NOT NULL AND cols <> ''
ORDER BY ncol ASC, conname ASC
LIMIT 1;
" | tr -d '[:space:]')

  if [[ -n "$uk_cols" ]]; then
    MERGE_KEY_KIND="unique"
    MERGE_KEY_COLS="$uk_cols"
    return 0
  fi

  # Unique indexes without a constraint (non-partial, non-expression)
  uk_cols=$(source_psql -t -A -c "
SELECT cols FROM (
  SELECT
    i.indexrelid::regclass::text AS iname,
    (
      SELECT string_agg(a.attname, ',' ORDER BY u.ord)
      FROM unnest(i.indkey) WITH ORDINALITY AS u(attnum, ord)
      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = u.attnum AND NOT a.attisdropped
      WHERE u.attnum > 0
    ) AS cols,
    (SELECT count(*) FROM unnest(i.indkey) x(attnum) WHERE x.attnum > 0) AS ncol
  FROM pg_index i
  WHERE i.indrelid = format('%I.%I', 'public', '${table}')::regclass
    AND i.indisunique
    AND NOT i.indisprimary
    AND i.indpred IS NULL
    AND i.indexprs IS NULL
) s
WHERE cols IS NOT NULL AND cols <> ''
ORDER BY ncol ASC, iname ASC
LIMIT 1;
" | tr -d '[:space:]')

  if [[ -n "$uk_cols" ]]; then
    MERGE_KEY_KIND="unique"
    MERGE_KEY_COLS="$uk_cols"
  fi
}

get_table_columns() {
  local table="$1"
  source_psql -t -A -c "
SELECT string_agg(column_name, ',' ORDER BY ordinal_position)
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = '${table}';
"
}

get_local_columns() {
  local table="$1"
  target_psql -t -A -c "
SELECT string_agg(column_name, ',' ORDER BY ordinal_position)
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = '${table}';
" | tr -d '[:space:]'
}

local_table_exists() {
  local table="$1"
  local exists
  exists=$(target_psql -t -A -c "
SELECT CASE WHEN EXISTS (
  SELECT 1 FROM information_schema.tables
  WHERE table_schema = 'public' AND table_name = '${table}' AND table_type = 'BASE TABLE'
) THEN 'yes' ELSE 'no' END;
")
  [[ "$exists" == "yes" ]]
}

# Create table if missing (LIKE staging). Does not add merge key.
ensure_local_table() {
  local table="$1"
  local qtable qstage
  qtable=$(quote_ident "$table")
  qstage=$(quote_ident "$STAGING_SCHEMA")

  if local_table_exists "$table"; then
    return 0
  fi

  log "CREATE TABLE public.${table} (LIKE staging)"
  target_psql -c \
    "CREATE TABLE public.${qtable} (LIKE ${qstage}.${qtable} INCLUDING DEFAULTS);"
}

# Ensure local has PK or UNIQUE covering merge key columns for ON CONFLICT.
ensure_local_merge_key() {
  local table="$1"
  local key_kind="$2"
  local key_csv="$3"
  local qtable key_sql
  qtable=$(quote_ident "$table")
  key_sql=$(csv_to_quoted_list "$key_csv")

  local has_key
  has_key=$(target_psql -t -A -c "
SELECT CASE WHEN EXISTS (
  SELECT 1
  FROM pg_constraint c
  WHERE c.conrelid = format('%I.%I', 'public', '${table}')::regclass
    AND c.contype IN ('p', 'u')
    AND (
      SELECT string_agg(a.attname, ',' ORDER BY u.ord)
      FROM unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord)
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = u.attnum
    ) = '${key_csv}'
) THEN 'yes' ELSE 'no' END;
")

  if [[ "$has_key" == "yes" ]]; then
    return 0
  fi

  if [[ "$key_kind" == "pk" ]]; then
    log "Adding PRIMARY KEY (${key_csv}) on public.${table}"
    if ! target_psql -c "ALTER TABLE public.${qtable} ADD PRIMARY KEY (${key_sql});"; then
      log "WARN: could not add PRIMARY KEY on public.${table}"
      return 1
    fi
  else
    log "Adding UNIQUE (${key_csv}) on public.${table}"
    if ! target_psql -c "ALTER TABLE public.${qtable} ADD UNIQUE (${key_sql});"; then
      log "WARN: could not add UNIQUE on public.${table}"
      return 1
    fi
  fi
  return 0
}

# Additive schema evolution: ADD COLUMN for source columns missing locally.
evolve_local_schema() {
  local table="$1"
  if ! is_truthy "$SCHEMA_EVOLUTION"; then
    return 0
  fi
  if ! local_table_exists "$table"; then
    return 0
  fi

  local qtable
  qtable=$(quote_ident "$table")

  # col|type|notnull|default  (pipe-separated; default may be empty)
  local rows
  rows=$(source_psql -t -A -F '|' -c "
SELECT
  a.attname,
  format_type(a.atttypid, a.atttypmod),
  CASE WHEN a.attnotnull THEN 't' ELSE 'f' END,
  COALESCE(pg_get_expr(ad.adbin, ad.adrelid), '')
FROM pg_attribute a
LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
WHERE a.attrelid = format('%I.%I', 'public', '${table}')::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
")

  local local_cols
  local_cols=$(get_local_columns "$table")
  local_cols=",${local_cols},"

  local line col typ notnull def qcol sql
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    IFS='|' read -r col typ notnull def <<< "$line"
    [[ -z "$col" ]] && continue
    if [[ "$local_cols" == *",${col},"* ]]; then
      continue
    fi

    qcol=$(quote_ident "$col")
    sql="ALTER TABLE public.${qtable} ADD COLUMN ${qcol} ${typ}"

    # Always add as NULL-able if NOT NULL without default (safer for non-empty tables).
    if [[ -n "$def" ]]; then
      sql+=" DEFAULT ${def}"
    fi
    if [[ "$notnull" == "t" && -z "$def" ]]; then
      log "WARN: adding column public.${table}.${col} as NULL (source is NOT NULL without default)"
    elif [[ "$notnull" == "t" && -n "$def" ]]; then
      sql+=" NOT NULL"
    fi

    log "SCHEMA ADD COLUMN public.${table}.${col} ${typ}"
    if ! target_psql -c "${sql};"; then
      log "WARN: failed to ADD COLUMN public.${table}.${col}; skipping column"
    fi
  done <<< "$rows"

  if is_truthy "$SAFE_TYPE_WIDENINGS"; then
    apply_safe_type_widenings "$table"
  fi

  if is_truthy "$DROP_ORPHAN_COLUMNS"; then
    drop_orphan_columns "$table"
  fi
}

# Whitelisted widenings only (opt-in).
apply_safe_type_widenings() {
  local table="$1"
  local qtable
  qtable=$(quote_ident "$table")

  local rows line col src_typ loc_typ
  rows=$(source_psql -t -A -F '|' -c "
SELECT a.attname, format_type(a.atttypid, a.atttypmod)
FROM pg_attribute a
WHERE a.attrelid = format('%I.%I', 'public', '${table}')::regclass
  AND a.attnum > 0 AND NOT a.attisdropped;
")

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    IFS='|' read -r col src_typ <<< "$line"
    [[ -z "$col" ]] && continue
    loc_typ=$(target_psql -t -A -c "
SELECT format_type(a.atttypid, a.atttypmod)
FROM pg_attribute a
WHERE a.attrelid = format('%I.%I', 'public', '${table}')::regclass
  AND a.attname = '${col}' AND NOT a.attisdropped;
" | head -1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [[ -z "$loc_typ" || "$loc_typ" == "$src_typ" ]] && continue

    local alter_to=""
    # int4/integer → bigint/int8
    if [[ "$loc_typ" =~ ^(integer|int4)$ && "$src_typ" =~ ^(bigint|int8)$ ]]; then
      alter_to="$src_typ"
    # smallint → int/bigint
    elif [[ "$loc_typ" =~ ^(smallint|int2)$ && "$src_typ" =~ ^(integer|int4|bigint|int8)$ ]]; then
      alter_to="$src_typ"
    # varchar(n) → varchar(m) m>=n or text
    elif [[ "$loc_typ" =~ ^character\ varying\(([0-9]+)\)$ ]]; then
      local n="${BASH_REMATCH[1]}"
      if [[ "$src_typ" =~ ^character\ varying\(([0-9]+)\)$ ]]; then
        local m="${BASH_REMATCH[1]}"
        if [[ "$m" -ge "$n" ]]; then
          alter_to="$src_typ"
        fi
      elif [[ "$src_typ" == "text" ]]; then
        alter_to="text"
      fi
    elif [[ "$loc_typ" =~ ^character\ varying && "$src_typ" == "text" ]]; then
      alter_to="text"
    fi

    if [[ -n "$alter_to" ]]; then
      log "SCHEMA TYPE WIDEN public.${table}.${col}: ${loc_typ} -> ${alter_to}"
      if ! target_psql -c "ALTER TABLE public.${qtable} ALTER COLUMN $(quote_ident "$col") TYPE ${alter_to};"; then
        log "WARN: type widen failed for public.${table}.${col}"
      fi
    else
      log "WARN: type mismatch public.${table}.${col} local=${loc_typ} source=${src_typ} (not a safe widening; skipped)"
    fi
  done <<< "$rows"
}

# Opt-in: drop local columns that do not exist on source (data loss).
drop_orphan_columns() {
  local table="$1"
  local qtable
  qtable=$(quote_ident "$table")

  local source_csv local_csv col
  source_csv=$(get_table_columns "$table" | tr -d '[:space:]')
  source_csv=",${source_csv},"
  local_csv=$(get_local_columns "$table")

  IFS=',' read -ra arr <<< "$local_csv"
  for col in "${arr[@]}"; do
    [[ -z "$col" ]] && continue
    if [[ "$source_csv" != *",${col},"* ]]; then
      log "SCHEMA DROP COLUMN public.${table}.${col} (orphan; DROP_ORPHAN_COLUMNS=true)"
      if ! target_psql -c "ALTER TABLE public.${qtable} DROP COLUMN $(quote_ident "$col") RESTRICT;"; then
        log "WARN: could not DROP COLUMN public.${table}.${col} (dependencies?)"
      fi
    fi
  done
}

# Opt-in: create secondary indexes from source.
sync_table_indexes() {
  local table="$1"
  if ! is_truthy "$SYNC_INDEXES" && ! is_truthy "$SYNC_UNIQUE_INDEXES"; then
    return 0
  fi

  local unique_filter
  if is_truthy "$SYNC_UNIQUE_INDEXES" && is_truthy "$SYNC_INDEXES"; then
    unique_filter="TRUE" # both
  elif is_truthy "$SYNC_UNIQUE_INDEXES"; then
    unique_filter="i.indisunique"
  else
    unique_filter="NOT i.indisunique"
  fi

  # index_name|pg_get_indexdef
  local rows
  rows=$(source_psql -t -A -F '|' -c "
SELECT ic.relname,
       pg_get_indexdef(i.indexrelid)
FROM pg_index i
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_class ic ON ic.oid = i.indexrelid
WHERE n.nspname = 'public'
  AND t.relname = '${table}'
  AND NOT i.indisprimary
  AND (${unique_filter})
ORDER BY ic.relname;
")

  local line iname idef exists
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    IFS='|' read -r iname idef <<< "$line"
    [[ -z "$iname" || -z "$idef" ]] && continue

    exists=$(target_psql -t -A -c "
SELECT CASE WHEN EXISTS (
  SELECT 1 FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relname = '${iname}' AND c.relkind = 'i'
) THEN 'yes' ELSE 'no' END;
")
    if [[ "$exists" == "yes" ]]; then
      continue
    fi

    log "INDEX CREATE public.${iname} on ${table}"
    if ! target_psql -c "${idef};"; then
      log "WARN: failed to create index ${iname} on public.${table}"
    fi
  done <<< "$rows"
}

# Intersection of source and local columns (source order), CSV
intersect_columns() {
  local table="$1"
  local source_csv local_csv col
  source_csv=$(get_table_columns "$table" | tr -d '[:space:]')
  local_csv=$(get_local_columns "$table")
  local_csv=",${local_csv},"

  local out="" sep=""
  IFS=',' read -ra arr <<< "$source_csv"
  for col in "${arr[@]}"; do
    [[ -z "$col" ]] && continue
    if [[ "$local_csv" == *",${col},"* ]]; then
      out+="${sep}${col}"
      sep=","
    fi
  done
  printf '%s' "$out"
}

merge_one_table() {
  local table="$1"

  get_merge_key "$table"
  if [[ -z "$MERGE_KEY_COLS" || -z "$MERGE_KEY_KIND" ]]; then
    log "SKIP table public.${table}: no primary key or usable unique key on source"
    SKIPPED_NO_KEY=$((SKIPPED_NO_KEY + 1))
    return 0
  fi

  ensure_local_table "$table"
  evolve_local_schema "$table"

  if ! ensure_local_merge_key "$table" "$MERGE_KEY_KIND" "$MERGE_KEY_COLS"; then
    log "SKIP table public.${table}: could not ensure local merge key (${MERGE_KEY_KIND}:${MERGE_KEY_COLS})"
    SKIPPED_NO_KEY=$((SKIPPED_NO_KEY + 1))
    return 0
  fi

  local cols_csv
  cols_csv=$(intersect_columns "$table")
  if [[ -z "$cols_csv" ]]; then
    log "SKIP table public.${table}: no common columns after evolution"
    SKIPPED_NO_KEY=$((SKIPPED_NO_KEY + 1))
    return 0
  fi

  # Ensure all merge-key columns are present in insert list
  local k
  IFS=',' read -ra key_arr <<< "$MERGE_KEY_COLS"
  for k in "${key_arr[@]}"; do
    [[ -z "$k" ]] && continue
    if [[ ",${cols_csv}," != *",${k},"* ]]; then
      log "SKIP table public.${table}: merge key column ${k} missing locally"
      SKIPPED_NO_KEY=$((SKIPPED_NO_KEY + 1))
      return 0
    fi
  done

  local qtable qstage
  qtable=$(quote_ident "$table")
  qstage=$(quote_ident "$STAGING_SCHEMA")

  local col_list="" key_list="" update_set="" sep="" key_sep="" upd_sep=""
  local col qcol is_key

  IFS=',' read -ra col_arr <<< "$cols_csv"
  for col in "${col_arr[@]}"; do
    [[ -z "$col" ]] && continue
    qcol=$(quote_ident "$col")
    col_list+="${sep}${qcol}"
    sep=", "

    is_key=false
    for k in "${key_arr[@]}"; do
      if [[ "$col" == "$k" ]]; then
        is_key=true
        break
      fi
    done
    if [[ "$is_key" == false ]]; then
      update_set+="${upd_sep}${qcol} = EXCLUDED.${qcol}"
      upd_sep=", "
    fi
  done

  for k in "${key_arr[@]}"; do
    [[ -z "$k" ]] && continue
    qcol=$(quote_ident "$k")
    key_list+="${key_sep}${qcol}"
    key_sep=", "
  done

  local sql
  if [[ -z "$update_set" ]]; then
    sql="INSERT INTO public.${qtable} (${col_list})
SELECT ${col_list} FROM ${qstage}.${qtable}
ON CONFLICT (${key_list}) DO NOTHING;"
  else
    sql="INSERT INTO public.${qtable} (${col_list})
SELECT ${col_list} FROM ${qstage}.${qtable}
ON CONFLICT (${key_list}) DO UPDATE SET ${update_set};"
  fi

  log "MERGE public.${table} (key=${MERGE_KEY_KIND}:${MERGE_KEY_COLS})"
  if ! target_psql -c "$sql"; then
    log "ERROR upsert public.${table}"
    return 1
  fi

  sync_table_indexes "$table"
  MERGED_COUNT=$((MERGED_COUNT + 1))
  return 0
}

run_merge() {
  local table failed=0
  MERGED_COUNT=0
  SKIPPED_NO_KEY=0
  setup_fdw
  refresh_staging

  filter_merge_candidates
  if ((${#CANDIDATE_TABLES[@]} == 0)); then
    log "No allowlisted public tables on source; merge cycle complete (0 tables) skipped_not_allowlisted=${SKIPPED_NOT_ALLOWLISTED}"
    log "METRICS merge tables_candidates=0 merged=0 skipped_no_key=0 skipped_not_allowlisted=${SKIPPED_NOT_ALLOWLISTED} failed=0 allowlist_mode=${ALLOWLIST_MODE}"
    return 0
  fi

  for table in "${CANDIDATE_TABLES[@]}"; do
    table=$(echo "$table" | tr -d '[:space:]')
    [[ -z "$table" ]] && continue
    if ! merge_one_table "$table"; then
      failed=$((failed + 1))
      log "ERROR merging public.${table}; aborting remaining tables this cycle"
      log "METRICS merge tables_candidates=${#CANDIDATE_TABLES[@]} merged=${MERGED_COUNT} skipped_no_key=${SKIPPED_NO_KEY} skipped_not_allowlisted=${SKIPPED_NOT_ALLOWLISTED} failed=${failed} allowlist_mode=${ALLOWLIST_MODE}"
      return 1
    fi
  done

  if is_truthy "$SYNC_FOREIGN_KEYS"; then
    log "WARN: SYNC_FOREIGN_KEYS=true is not implemented yet (planned: NOT VALID FKs); skipping FK sync"
  fi

  log "Merge cycle summary: tables_candidates=${#CANDIDATE_TABLES[@]} merged=${MERGED_COUNT} skipped_no_key=${SKIPPED_NO_KEY} skipped_not_allowlisted=${SKIPPED_NOT_ALLOWLISTED} failed=${failed} mode=${SYNC_MODE} schema_evolution=${SCHEMA_EVOLUTION} unique_merge_key=${ALLOW_UNIQUE_MERGE_KEY} drop_orphan=${DROP_ORPHAN_COLUMNS} indexes=${SYNC_INDEXES}/${SYNC_UNIQUE_INDEXES} type_widen=${SAFE_TYPE_WIDENINGS}"
  log "METRICS merge tables_candidates=${#CANDIDATE_TABLES[@]} merged=${MERGED_COUNT} skipped_no_key=${SKIPPED_NO_KEY} skipped_not_allowlisted=${SKIPPED_NOT_ALLOWLISTED} failed=${failed} allowlist_mode=${ALLOWLIST_MODE}"
  return 0
}

# Phase 8.2 T4: best-effort HTTP trigger to neo4j-populate after successful merge.
# Never fails the sync cycle if populate is down or curl missing.
trigger_neo4j_populate_if_configured() {
  local url timeout token curl_args
  url="${NEO4J_POPULATE_TRIGGER_URL// /}"
  if [[ -z "$url" ]]; then
    log "TRIGGER neo4j-populate status=skip reason=url_unset"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    log "TRIGGER neo4j-populate status=fail reason=curl_missing url=${url}"
    return 0
  fi
  timeout="${NEO4J_POPULATE_TRIGGER_TIMEOUT_SECONDS:-5}"
  token="${NEO4J_POPULATE_TRIGGER_TOKEN:-}"
  curl_args=(-fsS -X POST -m "$timeout" -H "Content-Type: application/json" -d '{"mode":"merge"}')
  if [[ -n "$token" ]]; then
    curl_args+=(-H "X-Populate-Token: ${token}")
  fi
  if curl "${curl_args[@]}" "$url" >/dev/null 2>&1; then
    log "TRIGGER neo4j-populate status=ok url=${url}"
  else
    log "TRIGGER neo4j-populate status=fail url=${url} (sync continues)"
  fi
  return 0
}

attempt_cycle() {
  local cycle_start_ms cycle_end_ms duration_ms status
  cycle_start_ms=$(now_ms)
  log "=== Sync cycle start (source=${SOURCE_HOST} target=${TARGET_HOST} interval_seconds=${SYNC_INTERVAL_SECONDS} expected_max_lag_seconds≈${SYNC_INTERVAL_SECONDS}) ==="

  if ! source_available; then
    if is_truthy "$HALT_ON_PRIMARY_UNAVAILABLE"; then
      cycle_end_ms=$(now_ms)
      duration_ms=$((cycle_end_ms - cycle_start_ms))
      log "HALT: cannot detect connection to ${SOURCE_HOST}:${SOURCE_PORT} (db=${SOURCE_DB}) after ${PRIMARY_CHECK_RETRIES} retries"
      log "Local application tables were not modified. Exiting sync job."
      log "METRICS cycle status=halted duration_ms=${duration_ms} interval_seconds=${SYNC_INTERVAL_SECONDS} expected_max_lag_seconds=${SYNC_INTERVAL_SECONDS}"
      exit 0
    fi
    cycle_end_ms=$(now_ms)
    duration_ms=$((cycle_end_ms - cycle_start_ms))
    log "SKIP: primary unavailable; will retry after ${SYNC_INTERVAL_SECONDS}s"
    log "METRICS cycle status=skipped duration_ms=${duration_ms} interval_seconds=${SYNC_INTERVAL_SECONDS} expected_max_lag_seconds=${SYNC_INTERVAL_SECONDS}"
    log "=== Sync cycle end (skipped) duration_ms=${duration_ms} ==="
    return 0
  fi

  log "Source ${SOURCE_HOST} is reachable; starting merge"
  if run_merge; then
    status="success"
    # Phase 8.2 T4: fire fleet Neo4j populate (scoped; never drops KG-1). Best-effort only.
    trigger_neo4j_populate_if_configured
  else
    status="failed"
  fi
  cycle_end_ms=$(now_ms)
  duration_ms=$((cycle_end_ms - cycle_start_ms))
  # Poll-based lag note (not CDC): row visibility lag is bounded by interval + cycle duration.
  log "METRICS cycle status=${status} duration_ms=${duration_ms} interval_seconds=${SYNC_INTERVAL_SECONDS} expected_max_lag_seconds=${SYNC_INTERVAL_SECONDS} lag_note=poll_not_cdc"
  log "=== Sync cycle end (${status}) duration_ms=${duration_ms} ==="
}

main() {
  apply_sync_mode
  parse_table_allowlist
  log "Haystack merge-sync starting"
  log "Config: mode=${SYNC_MODE} schemas=${SOURCE_SCHEMAS} interval=${SYNC_INTERVAL_SECONDS}s halt=${HALT_ON_PRIMARY_UNAVAILABLE} evolution=${SCHEMA_EVOLUTION} unique_key=${ALLOW_UNIQUE_MERGE_KEY} drop_orphan=${DROP_ORPHAN_COLUMNS} indexes=${SYNC_INDEXES}/${SYNC_UNIQUE_INDEXES} type_widen=${SAFE_TYPE_WIDENINGS} fks=${SYNC_FOREIGN_KEYS} allowlist_mode=${ALLOWLIST_MODE} allowlist=${SYNC_TABLE_ALLOWLIST} neo4j_populate_trigger=${NEO4J_POPULATE_TRIGGER_URL:-unset}"
  if [[ "$SOURCE_SCHEMAS" != "public" ]]; then
    log "WARN: SOURCE_SCHEMAS=${SOURCE_SCHEMAS} — only public is supported in this version; non-public schemas ignored"
  fi
  wait_for_target

  attempt_cycle

  while true; do
    log "Sleeping ${SYNC_INTERVAL_SECONDS}s until next cycle"
    sleep "$SYNC_INTERVAL_SECONDS"
    attempt_cycle
  done
}

main "$@"
