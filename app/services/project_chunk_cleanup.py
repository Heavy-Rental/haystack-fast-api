"""TTL / delete helpers for temporary project-spec chunks (Phase 5 / I1 · 5.5).

Multi-user project files on a shared DocumentStore (especially pgvector) are
temporary: delete by ``(user_id, ingest_id)`` or purge rows past ``expires_at``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.pipelines.indexing.document_store import delete_ingest_chunks
from app.services.project_knowledge_session import (
    ProjectKnowledgeSessionRegistry,
    get_project_knowledge_registry,
)

logger = logging.getLogger(__name__)


def _parse_expires_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Support trailing Z
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def purge_expired_chunks(
    document_store: Any,
    *,
    now: datetime | None = None,
) -> int:
    """Delete documents whose ``meta.expires_at`` is strictly before ``now``.

    Documents without ``expires_at`` are left untouched. Returns deleted count.
    """
    if document_store is None:
        return 0
    clock = now if now is not None else datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)

    try:
        all_docs = list(document_store.filter_documents() or [])
    except TypeError:
        all_docs = list(document_store.filter_documents(filters=None) or [])

    expired_ids: list[str] = []
    for doc in all_docs:
        meta = dict(getattr(doc, "meta", None) or {})
        exp = _parse_expires_at(meta.get("expires_at"))
        if exp is None:
            continue
        if exp < clock:
            doc_id = getattr(doc, "id", None)
            if doc_id:
                expired_ids.append(str(doc_id))

    if not expired_ids:
        return 0
    document_store.delete_documents(expired_ids)
    logger.info("purge_expired_chunks deleted=%s", len(expired_ids))
    return len(expired_ids)


def discard_project_knowledge_session(
    user_id: str,
    ingest_id: str,
    *,
    registry: ProjectKnowledgeSessionRegistry | None = None,
    document_store: Any | None = None,
    delete_chunks: bool = True,
) -> bool:
    """Remove registry session and optionally delete tenant chunks from store.

    When ``document_store`` is omitted, uses the session's store if present.
    KG JSON artifacts on disk are left in place (optional later cleanup).
    Returns whether a registry entry was removed.
    """
    reg = registry if registry is not None else get_project_knowledge_registry()
    uid = (user_id or "").strip()
    iid = (ingest_id or "").strip()
    store = document_store
    try:
        session = reg.get(uid, iid)
        if store is None:
            store = session.document_store
    except Exception as exc:  # noqa: BLE001 — session may already be gone
        logger.debug(
            "discard_session lookup skipped user_id=%s ingest_id=%s: %s",
            uid,
            iid,
            exc,
        )

    deleted_n = 0
    if delete_chunks and store is not None:
        try:
            deleted_n = delete_ingest_chunks(store, user_id=uid, ingest_id=iid)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "discard_session chunk delete failed user_id=%s ingest_id=%s: %s",
                uid,
                iid,
                exc,
            )

    removed = reg.delete(uid, iid)
    logger.info(
        "discard_project_knowledge_session user_id=%s ingest_id=%s "
        "registry_removed=%s chunks_deleted=%s",
        uid,
        iid,
        removed,
        deleted_n,
    )
    return removed
