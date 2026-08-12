"""DocumentStore helpers for the indexing pipeline.

Default backend is Haystack ``InMemoryDocumentStore`` (process-local, CI-safe).

Phase 5 / I0: ``build_document_store()`` selects ``memory`` or ``pgvector`` via
``INDEXING_DOCUMENT_STORE``.

Phase 5 / I1: ``create_session_document_store()`` wires the factory into Call 1
ingest + session registry. ``memory`` still allocates a **fresh** InMemory store
per ingest; ``pgvector`` shares a table and relies on meta filters + delete/TTL.
"""

from __future__ import annotations

from typing import Any, Literal

from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.utils import Secret

from app.config import Settings, get_settings

DocumentStoreMode = Literal["memory", "pgvector"]

_ALLOWED_MODES = frozenset({"memory", "pgvector"})

# Stable table for project-spec chunks on Postgres-Haystack (I1).
PGVECTOR_TABLE_NAME = "indexing_project_chunks"

_document_store: InMemoryDocumentStore | None = None


def get_document_store() -> InMemoryDocumentStore:
    """Return the shared in-memory document store (lazy singleton).

    Always process-local InMemory — does **not** follow ``INDEXING_DOCUMENT_STORE``
    so a host env of ``pgvector`` cannot break ad-hoc callers that still use the
    singleton helper.
    """
    global _document_store
    if _document_store is None:
        _document_store = InMemoryDocumentStore()
    return _document_store


def reset_document_store() -> InMemoryDocumentStore:
    """Replace the shared store (tests / explicit flush)."""
    global _document_store
    _document_store = InMemoryDocumentStore()
    return _document_store


def normalize_document_store_mode(mode: str | None) -> DocumentStoreMode:
    """Normalize and validate DocumentStore backend mode."""
    normalized = str(mode if mode is not None else "memory").strip().lower()
    if normalized not in _ALLOWED_MODES:
        allowed = ", ".join(sorted(_ALLOWED_MODES))
        raise ValueError(
            f"unsupported INDEXING_DOCUMENT_STORE mode: {mode!r}; "
            f"allowed: {allowed}"
        )
    return normalized  # type: ignore[return-value]


def _psycopg_url_to_libpq(url: str) -> str:
    """Map SQLAlchemy-style URLs to libpq URI for PgvectorDocumentStore."""
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url.removeprefix("postgresql+asyncpg://")
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgres://"):
        return "postgresql://" + url.removeprefix("postgres://")
    return url


def _connection_string_for_pgvector(
    *,
    settings: Settings,
    connection_string: str | None,
) -> str:
    raw = connection_string if connection_string is not None else settings.database_url
    if not raw or not str(raw).strip():
        raise ValueError(
            "pgvector DocumentStore requires a non-empty connection string "
            "(connection_string=... or DATABASE_URL / POSTGRES_* settings)"
        )
    return _psycopg_url_to_libpq(str(raw).strip())


def build_document_store(
    *,
    mode: str | None = None,
    settings: Settings | None = None,
    embedding_dimension: int | None = None,
    connection_string: str | None = None,
    recreate_table: bool = False,
) -> Any:
    """Create a DocumentStore from ``INDEXING_DOCUMENT_STORE`` (or explicit mode).

    * ``memory`` (default) — ``InMemoryDocumentStore``; no network/DB.
    * ``pgvector`` — Haystack ``PgvectorDocumentStore`` (lazy import); uses
      connection string + ``INDEXING_EMBEDDING_DIM``. May open a DB connection
      on construct — callers/tests must mock when Postgres is unavailable.
    """
    cfg = settings if settings is not None else get_settings()
    resolved_mode = normalize_document_store_mode(
        mode if mode is not None else cfg.indexing_document_store
    )
    dim = (
        embedding_dimension
        if embedding_dimension is not None
        else cfg.indexing_embedding_dim
    )

    if resolved_mode == "memory":
        return InMemoryDocumentStore()

    # pgvector
    try:
        from haystack_integrations.document_stores.pgvector import (  # type: ignore[import-untyped]
            PgvectorDocumentStore,
        )
    except ImportError as exc:
        raise ImportError(
            "PgvectorDocumentStore is not available. "
            "Install pgvector-haystack (pip/uv: pgvector-haystack) "
            "or use INDEXING_DOCUMENT_STORE=memory."
        ) from exc

    conn = _connection_string_for_pgvector(
        settings=cfg,
        connection_string=connection_string,
    )
    return PgvectorDocumentStore(
        connection_string=Secret.from_token(conn),
        embedding_dimension=dim,
        table_name=PGVECTOR_TABLE_NAME,
        recreate_table=recreate_table,
        create_extension=True,
    )


def create_session_document_store(
    *,
    settings: Settings | None = None,
    mode: str | None = None,
    connection_string: str | None = None,
    embedding_dimension: int | None = None,
) -> Any:
    """DocumentStore for one Call 1 ingest session (I1 wire).

    * ``memory`` — always a **new** ``InMemoryDocumentStore`` (process-local
      isolation without meta filters; matches pre-I1 per-ingest behaviour).
    * ``pgvector`` — shared-table store from ``build_document_store``; tenants
      isolate via ``user_id`` / ``ingest_id`` filters on retrieval and delete.
    """
    cfg = settings if settings is not None else get_settings()
    resolved = normalize_document_store_mode(
        mode if mode is not None else cfg.indexing_document_store
    )
    if resolved == "memory":
        return InMemoryDocumentStore()
    return build_document_store(
        mode="pgvector",
        settings=cfg,
        connection_string=connection_string,
        embedding_dimension=embedding_dimension,
    )


def tenant_meta_filters(
    *,
    user_id: str,
    ingest_id: str | None = None,
) -> dict[str, Any]:
    """Filter dict matching ``meta.user_id`` (+ optional ``meta.ingest_id``)."""
    uid = (user_id or "").strip()
    conditions: list[dict[str, Any]] = [
        {"field": "meta.user_id", "operator": "==", "value": uid}
    ]
    iid = (ingest_id or "").strip() if ingest_id is not None else ""
    if iid:
        conditions.append(
            {"field": "meta.ingest_id", "operator": "==", "value": iid}
        )
    if len(conditions) == 1:
        return conditions[0]
    return {"operator": "AND", "conditions": conditions}


def delete_ingest_chunks(
    document_store: Any,
    *,
    user_id: str,
    ingest_id: str,
) -> int:
    """Delete all documents for ``(user_id, ingest_id)``. Return deleted count."""
    uid = (user_id or "").strip()
    iid = (ingest_id or "").strip()
    if not uid or not iid:
        raise ValueError("user_id and ingest_id are required for delete_ingest_chunks")
    if document_store is None:
        return 0
    filters = tenant_meta_filters(user_id=uid, ingest_id=iid)
    docs = list(document_store.filter_documents(filters=filters) or [])
    ids = [str(d.id) for d in docs if getattr(d, "id", None)]
    if not ids:
        return 0
    document_store.delete_documents(ids)
    return len(ids)
