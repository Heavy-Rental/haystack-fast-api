#!/usr/bin/env bash
# Project allowlisted fleet tables from postgres-haystack into Neo4j (Cypher MERGE).
# Phase 8.2 T4: admin HTTP + post-sync trigger surface; never drop KG-1 labels.
# Spec: Haystack-Fast-API/specs/005-haystack-neo4j-populate/
# Contract: contracts/neo4j-populate-env.md
#
# Env (defaults):
#   PGHOST / TARGET_HOST=postgres-haystack
#   NEO4J_URI=bolt://neo4j:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=heavyrental
#   FLEET_TABLE_ALLOWLIST=asset,booking,category
#   FLEET_LABELS=Asset,Booking,Category
#   KG1_PROTECTED_LABELS=Document
#   POPULATE_MODE=merge|rebuild
#   POPULATE_TRIGGER_MODE=both|event|interval
#   POPULATE_INTERVAL_SECONDS=60
#   POPULATE_ORPHAN_DELETE=false
#   POPULATE_HTTP_PORT=8089 POPULATE_HTTP_TOKEN= POPULATE_HTTP_ENABLED=true
#   POPULATE_ONCE=false
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER="${SCRIPT_DIR}/populate_neo4j.py"

log() {
  echo "[neo4j-populate] $*"
}

if [[ ! -f "$WORKER" ]]; then
  log "ERROR: worker not found at ${WORKER}"
  exit 1
fi

export PGHOST="${PGHOST:-${TARGET_HOST:-postgres-haystack}}"
export PGPORT="${PGPORT:-${TARGET_PORT:-5432}}"
export PGUSER="${PGUSER:-${TARGET_USER:-postgres}}"
export PGPASSWORD="${PGPASSWORD:-${TARGET_PASSWORD:-postgres}}"
export PGDATABASE="${PGDATABASE:-${TARGET_DB:-heavy_rental}}"

export NEO4J_URI="${NEO4J_URI:-bolt://neo4j:7687}"
export NEO4J_USER="${NEO4J_USER:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-heavyrental}"
export NEO4J_DATABASE="${NEO4J_DATABASE:-neo4j}"

export FLEET_TABLE_ALLOWLIST="${FLEET_TABLE_ALLOWLIST:-${SYNC_TABLE_ALLOWLIST:-asset,booking,category}}"
export FLEET_LABELS="${FLEET_LABELS:-Asset,Booking,Category}"
export KG1_PROTECTED_LABELS="${KG1_PROTECTED_LABELS:-Document}"
export POPULATE_MODE="${POPULATE_MODE:-merge}"
export POPULATE_TRIGGER_MODE="${POPULATE_TRIGGER_MODE:-both}"
export POPULATE_INTERVAL_SECONDS="${POPULATE_INTERVAL_SECONDS:-60}"
export POPULATE_ORPHAN_DELETE="${POPULATE_ORPHAN_DELETE:-false}"
export POPULATE_HTTP_PORT="${POPULATE_HTTP_PORT:-8089}"
export POPULATE_HTTP_ENABLED="${POPULATE_HTTP_ENABLED:-true}"
POPULATE_ONCE="${POPULATE_ONCE:-false}"

log "Entrypoint: worker=${WORKER} once=${POPULATE_ONCE} mode=${POPULATE_MODE} trigger_mode=${POPULATE_TRIGGER_MODE} http_port=${POPULATE_HTTP_PORT}"
log "Source: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE} → ${NEO4J_URI} fleet=${FLEET_LABELS} kg1_protected=${KG1_PROTECTED_LABELS}"

ARGS=()
case "${POPULATE_ONCE,,}" in
  1|true|yes|on) ARGS+=(--once) ;;
esac

for arg in "$@"; do
  case "$arg" in
    --once) ARGS+=(--once) ;;
    --no-http) ARGS+=(--no-http) ;;
  esac
done

exec python3 "$WORKER" "${ARGS[@]+"${ARGS[@]}"}"
