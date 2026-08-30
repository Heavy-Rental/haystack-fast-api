#!/usr/bin/env python3
"""SQL → Cypher MERGE: project fleet tables from postgres-haystack into Neo4j.

KG-2 fleet labels only (:Asset, :Booking, :Category).
Never drops KG-1 / DocumentStore labels (default :Document).
Phase 8.2 T4: admin HTTP + post-sync trigger surface.

Spec: Haystack-Fast-API/specs/005-haystack-neo4j-populate/
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import date, datetime, time as dtime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import psycopg
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from psycopg import sql
from psycopg.rows import dict_row

# Table (SQL) → Neo4j node label (KG-2 fleet)
DEFAULT_TABLE_LABELS: dict[str, str] = {
    "asset": "Asset",
    "booking": "Booking",
    "category": "Category",
    "return_records": "Return_Records"
}

# Internal props written by this job (not from SQL)
INTERNAL_PROPS = frozenset({"_source", "_populated_at"})

# In-memory last cycle status for GET /v1/status
_LAST_STATUS: dict[str, Any] = {
    "status": "never_run",
    "duration_ms": None,
    "mode": None,
    "finished_at": None,
}
_CYCLE_LOCK = threading.Lock()


def log(msg: str) -> None:
    print(f"[neo4j-populate] {msg}", flush=True)


def env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None or val == "":
        if default is not None:
            return default
        raise SystemExit(f"Missing required env: {name}")
    return val


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def parse_allowlist(raw: str) -> list[str]:
    raw = (raw or "").replace(" ", "")
    if not raw or raw.lower() in ("all", "*"):
        return list(DEFAULT_TABLE_LABELS.keys())
    cleaned = [t for t in raw.split(",") if t and all(c.isalnum() or c == "_" for c in t)]
    return cleaned or list(DEFAULT_TABLE_LABELS.keys())


def parse_labels(raw: str, *, fallback: set[str] | None = None) -> set[str]:
    labels: set[str] = set()
    for x in (raw or "").split(","):
        label = x.strip()
        if label and label.replace("_", "").isalnum():
            labels.add(label)
    if labels:
        return labels
    return set(fallback) if fallback is not None else set()


def coerce_value(value: Any) -> Any:
    """Convert Postgres values to Neo4j-safe scalars."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str)
    return value


def coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k is None:
            continue
        key = str(k)
        if key.startswith("_"):
            key = f"sql{key}"
        out[key] = coerce_value(v)
    return out


def table_exists(conn: psycopg.Connection, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        return cur.fetchone() is not None


def table_has_column(conn: psycopg.Connection, table: str, column: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            """,
            (table, column),
        )
        return cur.fetchone() is not None


def fetch_rows(conn: psycopg.Connection, table: str) -> list[dict[str, Any]]:
    query = sql.SQL("SELECT * FROM {}.{}").format(
        sql.Identifier("public"),
        sql.Identifier(table),
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query)
        return list(cur.fetchall())


def safe_deletable_labels(fleet_labels: set[str], protected: set[str]) -> set[str]:
    """Fleet labels that are allowed for scoped delete (never KG-1)."""
    blocked = fleet_labels & protected
    if blocked:
        log(
            f"ERROR: FLEET_LABELS overlaps KG1_PROTECTED_LABELS={','.join(sorted(blocked))}; "
            "refusing scoped delete for those labels (never drop KG-1)"
        )
    return set(fleet_labels) - protected


def ensure_constraints(session, labels: set[str]) -> None:
    for label in sorted(labels):
        name = f"fleet_{label.lower()}_id"
        cypher = (
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:`{label}`) REQUIRE n.id IS UNIQUE"
        )
        session.run(cypher)


def clear_fleet_labels(
    session, labels: set[str], protected: set[str]
) -> int:
    """Label-scoped delete only — never full-graph wipe; never KG-1 labels."""
    deletable = safe_deletable_labels(labels, protected)
    deleted = 0
    for label in sorted(deletable):
        count_result = session.run(f"MATCH (n:`{label}`) RETURN count(n) AS c")
        record = count_result.single()
        n = int(record["c"]) if record else 0
        if n:
            session.run(f"MATCH (n:`{label}`) DETACH DELETE n")
            deleted += n
            log(f"scoped_delete label={label} count={n}")
    return deleted


def delete_orphans(
    session,
    label: str,
    keep_ids: list[Any],
    protected: set[str],
) -> int:
    """Delete fleet nodes whose id is not in SQL source. Never touches KG-1."""
    if label in protected:
        log(f"REFUSE orphan_delete label={label}: protected KG-1")
        return 0
    if not keep_ids:
        # Empty source: do not mass-delete fleet (safety); rebuild mode handles full clear
        log(f"SKIP orphan_delete label={label}: empty keep_ids (use rebuild to clear)")
        return 0
    result = session.run(
        f"MATCH (n:`{label}`) WHERE NOT n.id IN $ids "
        f"WITH n DETACH DELETE n RETURN count(*) AS c",
        ids=keep_ids,
    )
    record = result.single()
    return int(record["c"]) if record else 0


def merge_nodes(session, label: str, rows: list[dict[str, Any]], protected: set[str]) -> int:
    if label in protected:
        log(f"REFUSE MERGE label={label}: protected KG-1")
        return 0
    if not rows:
        return 0
    merged = 0
    cypher = (
        f"UNWIND $rows AS row "
        f"MERGE (n:`{label}` {{id: row.id}}) "
        f"SET n += row.props, n._source = 'fleet-mirror', n._populated_at = datetime() "
        f"RETURN count(n) AS c"
    )
    batch: list[dict[str, Any]] = []
    for row in rows:
        props = coerce_row(row)
        if "id" not in props or props["id"] is None:
            continue
        node_id = props["id"]
        for k in list(props.keys()):
            if k in INTERNAL_PROPS:
                props.pop(k, None)
        batch.append({"id": node_id, "props": props})
    if not batch:
        return 0
    chunk_size = 500
    for i in range(0, len(batch), chunk_size):
        chunk = batch[i : i + chunk_size]
        result = session.run(cypher, rows=chunk)
        record = result.single()
        merged += int(record["c"]) if record else len(chunk)
    return merged


def merge_relationships(session, conn: psycopg.Connection) -> dict[str, int]:
    """Best-effort FK edges when columns exist."""
    counts: dict[str, int] = {}

    if (
        table_exists(conn, "asset")
        and table_exists(conn, "category")
        and table_has_column(conn, "asset", "id")
    ):
        cat_col = None
        for candidate in ("category_id", "categoryId", "category"):
            if table_has_column(conn, "asset", candidate):
                cat_col = candidate
                break
        if cat_col:
            query = sql.SQL(
                "SELECT id AS asset_id, {} AS category_id FROM public.asset "
                "WHERE {} IS NOT NULL"
            ).format(sql.Identifier(cat_col), sql.Identifier(cat_col))
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query)
                rows = [
                    {
                        "asset_id": coerce_value(r["asset_id"]),
                        "category_id": coerce_value(r["category_id"]),
                    }
                    for r in cur.fetchall()
                ]
            if rows:
                cypher = (
                    "UNWIND $rows AS row "
                    "MATCH (a:Asset {id: row.asset_id}) "
                    "MATCH (c:Category {id: row.category_id}) "
                    "MERGE (a)-[r:IN_CATEGORY]->(c) "
                    "RETURN count(r) AS c"
                )
                result = session.run(cypher, rows=rows)
                rec = result.single()
                counts["IN_CATEGORY"] = int(rec["c"]) if rec else 0

    if (
        table_exists(conn, "booking")
        and table_exists(conn, "asset")
        and table_has_column(conn, "booking", "id")
    ):
        asset_col = None
        for candidate in ("asset_id", "assetId", "asset"):
            if table_has_column(conn, "booking", candidate):
                asset_col = candidate
                break
        if asset_col:
            query = sql.SQL(
                "SELECT id AS booking_id, {} AS asset_id FROM public.booking "
                "WHERE {} IS NOT NULL"
            ).format(sql.Identifier(asset_col), sql.Identifier(asset_col))
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query)
                rows = [
                    {
                        "booking_id": coerce_value(r["booking_id"]),
                        "asset_id": coerce_value(r["asset_id"]),
                    }
                    for r in cur.fetchall()
                ]
            if rows:
                cypher = (
                    "UNWIND $rows AS row "
                    "MATCH (b:Booking {id: row.booking_id}) "
                    "MATCH (a:Asset {id: row.asset_id}) "
                    "MERGE (b)-[r:FOR_ASSET]->(a) "
                    "RETURN count(r) AS c"
                )
                result = session.run(cypher, rows=rows)
                rec = result.single()
                counts["FOR_ASSET"] = int(rec["c"]) if rec else 0

    return counts


def run_cycle(
    pg_conninfo: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_database: str,
    tables: list[str],
    fleet_labels: set[str],
    protected: set[str],
    mode: str,
    orphan_delete: bool = False,
) -> int:
    """Run one populate cycle. Returns 0 on success/soft-skip."""
    t0 = time.monotonic()
    mode = (mode or "merge").lower().strip()
    if mode not in ("merge", "rebuild"):
        log(f"WARN: unknown POPULATE_MODE={mode!r}; using merge")
        mode = "merge"

    skipped_missing = 0
    skipped_no_id = 0
    nodes_merged = 0
    tables_ok = 0
    deleted = 0
    orphans = 0
    rel_counts: dict[str, int] = {}
    status = "ok"

    try:
        with psycopg.connect(pg_conninfo, connect_timeout=5) as conn:
            driver = GraphDatabase.driver(
                neo4j_uri, auth=(neo4j_user, neo4j_password)
            )
            try:
                driver.verify_connectivity()
                with driver.session(database=neo4j_database) as session:
                    write_labels = safe_deletable_labels(fleet_labels, protected)
                    ensure_constraints(session, write_labels)

                    if mode == "rebuild":
                        deleted = clear_fleet_labels(session, fleet_labels, protected)
                        log(
                            f"rebuild: scoped_delete count={deleted} "
                            f"fleet={','.join(sorted(write_labels))} "
                            f"kg1_protected={','.join(sorted(protected))}"
                        )

                    ids_by_label: dict[str, list[Any]] = {}

                    for table in tables:
                        label = DEFAULT_TABLE_LABELS.get(table)
                        if not label:
                            label = table[:1].upper() + table[1:]
                        if label not in fleet_labels:
                            log(
                                f"SKIP table={table}: label {label} not in FLEET_LABELS "
                                f"(isolation)"
                            )
                            skipped_missing += 1
                            continue
                        if label in protected:
                            log(
                                f"SKIP table={table}: label {label} is KG-1 protected "
                                f"(never drop/write KG-1)"
                            )
                            skipped_missing += 1
                            continue
                        if not table_exists(conn, table):
                            log(f"SKIP table={table}: not found in public")
                            skipped_missing += 1
                            continue
                        if not table_has_column(conn, table, "id"):
                            log(f"SKIP table={table}: no id column")
                            skipped_no_id += 1
                            continue
                        rows = fetch_rows(conn, table)
                        n = merge_nodes(session, label, rows, protected)
                        nodes_merged += n
                        tables_ok += 1
                        keep = [
                            coerce_value(r["id"])
                            for r in rows
                            if r.get("id") is not None
                        ]
                        ids_by_label[label] = keep
                        log(
                            f"MERGE label={label} table={table} "
                            f"rows={len(rows)} merged={n}"
                        )

                    if orphan_delete and mode != "rebuild":
                        for label, keep_ids in ids_by_label.items():
                            o = delete_orphans(session, label, keep_ids, protected)
                            if o:
                                orphans += o
                                log(f"orphan_delete label={label} count={o}")

                    rel_counts = merge_relationships(session, conn)
                    for rel, c in rel_counts.items():
                        log(f"MERGE rel={rel} count={c}")
            finally:
                driver.close()
    except (psycopg.OperationalError, psycopg.Error) as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        status = "skip_pg"
        log(f"SKIP cycle: postgres unavailable: {exc}")
        log(
            f"METRICS populate status={status} duration_ms={duration_ms} "
            f"mode={mode} nodes_merged=0 "
            f"kg1_protected={','.join(sorted(protected))}"
        )
        _update_status(status, duration_ms, mode)
        return 0
    except (ServiceUnavailable, Neo4jError, OSError) as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        status = "skip_neo4j"
        log(f"SKIP cycle: neo4j unavailable: {exc}")
        log(
            f"METRICS populate status={status} duration_ms={duration_ms} "
            f"mode={mode} nodes_merged=0 "
            f"kg1_protected={','.join(sorted(protected))}"
        )
        _update_status(status, duration_ms, mode)
        return 0
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - t0) * 1000)
        status = "error"
        log(f"ERROR cycle failed: {exc}")
        log(
            f"METRICS populate status={status} duration_ms={duration_ms} "
            f"mode={mode} nodes_merged={nodes_merged} "
            f"kg1_protected={','.join(sorted(protected))}"
        )
        _update_status(status, duration_ms, mode)
        return 0

    duration_ms = int((time.monotonic() - t0) * 1000)
    rel_total = sum(rel_counts.values())
    log(
        f"METRICS populate status={status} duration_ms={duration_ms} mode={mode} "
        f"tables_ok={tables_ok} skipped_missing={skipped_missing} "
        f"skipped_no_id={skipped_no_id} nodes_merged={nodes_merged} "
        f"rels_merged={rel_total} rebuild_deleted={deleted} "
        f"orphans_deleted={orphans} "
        f"kg1_protected={','.join(sorted(protected))} "
        f"scoped_delete=fleet_only"
    )
    _update_status(status, duration_ms, mode, extra={
        "tables_ok": tables_ok,
        "nodes_merged": nodes_merged,
        "rebuild_deleted": deleted,
        "orphans_deleted": orphans,
    })
    return 0


def _update_status(
    status: str,
    duration_ms: int,
    mode: str,
    extra: dict[str, Any] | None = None,
) -> None:
    global _LAST_STATUS
    payload = {
        "status": status,
        "duration_ms": duration_ms,
        "mode": mode,
        "finished_at": datetime.utcnow().isoformat() + "Z",
    }
    if extra:
        payload.update(extra)
    _LAST_STATUS = payload


class PopulateConfig:
    """Runtime config shared by HTTP and interval loop."""

    def __init__(self) -> None:
        pg_host = env("PGHOST", env("TARGET_HOST", "postgres-haystack"))
        pg_port = env("PGPORT", env("TARGET_PORT", "5432"))
        pg_user = env("PGUSER", env("TARGET_USER", "postgres"))
        pg_password = env("PGPASSWORD", env("TARGET_PASSWORD", "postgres"))
        pg_db = env("PGDATABASE", env("TARGET_DB", "heavy_rental"))
        self.pg_conninfo = (
            f"host={pg_host} port={pg_port} user={pg_user} "
            f"password={pg_password} dbname={pg_db}"
        )
        self.neo4j_uri = env("NEO4J_URI", "bolt://neo4j:7687")
        self.neo4j_user = env("NEO4J_USER", "neo4j")
        self.neo4j_password = env("NEO4J_PASSWORD", "heavyrental")
        self.neo4j_database = env("NEO4J_DATABASE", "neo4j")
        self.tables = parse_allowlist(
            env(
                "FLEET_TABLE_ALLOWLIST",
                env("SYNC_TABLE_ALLOWLIST", "asset,booking,category"),
            )
        )
        self.fleet_labels = parse_labels(
            env("FLEET_LABELS", "Asset,Booking,Category"),
            fallback=set(DEFAULT_TABLE_LABELS.values()),
        )
        self.protected = parse_labels(
            env("KG1_PROTECTED_LABELS", "Document"),
            fallback={"Document"},
        )
        self.mode = env("POPULATE_MODE", "merge")
        self.interval = max(1, int(env("POPULATE_INTERVAL_SECONDS", "60")))
        self.orphan_delete = env_bool("POPULATE_ORPHAN_DELETE", False)
        self.trigger_mode = env("POPULATE_TRIGGER_MODE", "both").lower().strip()
        if self.trigger_mode not in ("event", "interval", "both"):
            log(f"WARN: unknown POPULATE_TRIGGER_MODE={self.trigger_mode!r}; using both")
            self.trigger_mode = "both"
        self.http_port = int(env("POPULATE_HTTP_PORT", "8089"))
        self.http_token = os.environ.get("POPULATE_HTTP_TOKEN", "").strip()
        self.http_enabled = env_bool("POPULATE_HTTP_ENABLED", True)

    def run_once(self, mode: str | None = None) -> int:
        use_mode = mode or self.mode
        if not _CYCLE_LOCK.acquire(blocking=False):
            log("SKIP cycle: another populate already running")
            return 0
        try:
            return run_cycle(
                self.pg_conninfo,
                self.neo4j_uri,
                self.neo4j_user,
                self.neo4j_password,
                self.neo4j_database,
                self.tables,
                self.fleet_labels,
                self.protected,
                use_mode,
                orphan_delete=self.orphan_delete,
            )
        finally:
            _CYCLE_LOCK.release()


def _make_handler(cfg: PopulateConfig) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            log(f"http {self.address_string()} {fmt % args}")

        def _auth_ok(self) -> bool:
            if not cfg.http_token:
                return True
            return self.headers.get("X-Populate-Token", "") == cfg.http_token

        def _send(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/health", "/"):
                self._send(200, {"status": "ok", "service": "neo4j-populate"})
                return
            if path == "/v1/status":
                if not self._auth_ok():
                    self._send(401, {"error": "unauthorized"})
                    return
                self._send(200, dict(_LAST_STATUS))
                return
            self._send(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in ("/v1/populate", "/trigger", "/populate"):
                self._send(404, {"error": "not_found"})
                return
            if not self._auth_ok():
                self._send(401, {"error": "unauthorized"})
                return

            mode = cfg.mode
            qs = parse_qs(urlparse(self.path).query)
            if "mode" in qs and qs["mode"]:
                mode = qs["mode"][0]
            length = int(self.headers.get("Content-Length") or 0)
            if length > 0:
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                    if isinstance(body, dict) and body.get("mode"):
                        mode = str(body["mode"])
                except json.JSONDecodeError:
                    pass

            # Non-blocking: run cycle in background so sync curl can return quickly
            def _bg() -> None:
                cfg.run_once(mode=mode)

            threading.Thread(target=_bg, name="populate-once", daemon=True).start()
            self._send(
                202,
                {
                    "status": "accepted",
                    "mode": mode,
                    "blocking": False,
                    "message": "populate cycle started",
                },
            )

    return Handler


def start_http_server(cfg: PopulateConfig) -> ThreadingHTTPServer:
    handler = _make_handler(cfg)
    server = ThreadingHTTPServer(("0.0.0.0", cfg.http_port), handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="populate-http",
        daemon=True,
    )
    thread.start()
    log(f"HTTP admin listening on 0.0.0.0:{cfg.http_port} (POST /v1/populate)")
    return server


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    once = "--once" in argv
    no_http = "--no-http" in argv

    cfg = PopulateConfig()

    log(
        f"Config: neo4j={cfg.neo4j_uri} db={cfg.neo4j_database} "
        f"tables={','.join(cfg.tables)} "
        f"fleet_labels={','.join(sorted(cfg.fleet_labels))} "
        f"kg1_protected={','.join(sorted(cfg.protected))} "
        f"mode={cfg.mode} trigger_mode={cfg.trigger_mode} "
        f"interval={cfg.interval}s orphan_delete={cfg.orphan_delete} "
        f"http_port={cfg.http_port} once={once}"
    )

    overlap = cfg.fleet_labels & cfg.protected
    if overlap:
        log(
            f"WARN: FLEET_LABELS ∩ KG1_PROTECTED_LABELS={','.join(sorted(overlap))} "
            "— those labels will never be written or deleted"
        )

    if once:
        return cfg.run_once()

    server = None
    if cfg.http_enabled and not no_http:
        server = start_http_server(cfg)

    # event: HTTP only; interval/both: background poll as safety net
    if cfg.trigger_mode in ("interval", "both"):
        while True:
            cfg.run_once()
            time.sleep(cfg.interval)
    else:
        # event-only: block on HTTP server
        log("trigger_mode=event: waiting for POST /v1/populate (no interval loop)")
        if server is None:
            log("ERROR: event mode requires HTTP; enable POPULATE_HTTP_ENABLED")
            return 1
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
