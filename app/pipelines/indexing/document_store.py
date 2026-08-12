"""DocumentStore helpers for the indexing pipeline.

Default backend is Haystack ``InMemoryDocumentStore`` (process-local, CI-safe).

Phase 5 / I0: ``build_document_store()`` selects ``memory`` or ``pgvector`` via
``INDEXING_DOCUMENT_STORE``. The ingest pipeline still uses InMemory until I1
wires the factory into Branch A writer + session registry.
"""

from __future__ import annotations

from typing import Any, Literal

from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.utils import Secret

from app.config import Settings, get_settings

DocumentStoreMode = Literal["memory", "pgvector"]

_ALLOWED_MODES = frozenset({"memory", "pgvector"})

_document_store: InMemoryDocumentStore | None = None


def get_document_store() -> InMemoryDocumentStore:
    """Return the shared in-memory document store (lazy singleton).

    Always process-local InMemory — does **not** follow ``INDEXING_DOCUMENT_STORE``
    so a host env of ``pgvector`` cannot break CI or accidental singleton use
    before I1 pipeline wiring.
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
) -> Any:
    """Create a DocumentStore from ``INDEXING_DOCUMENT_STORE`` (or explicit mode).

    * ``memory`` (default) — ``InMemoryDocumentStore``; no network/DB.
    * ``pgvector`` — Haystack ``PgvectorDocumentStore`` (lazy import); uses
      connection string + ``INDEXING_EMBEDDING_DIM``. May open a DB connection
      on construct — callers/tests must mock when Postgres is unavailable.

    Ingest pipeline wiring of this factory is **I1** (not I0).
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
        recreate_table=False,
    )
