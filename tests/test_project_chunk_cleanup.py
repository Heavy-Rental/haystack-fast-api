"""Phase 5.5: delete one ingest + TTL purge isolation (default CI / InMemory)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from haystack.dataclasses import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.core.exceptions import NotFoundError
from app.pipelines.indexing.document_store import delete_ingest_chunks
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.services.project_chunk_cleanup import (
    discard_project_knowledge_session,
    purge_expired_chunks,
)
from app.services.project_knowledge_session import (
    ProjectKnowledgeSession,
    get_project_knowledge_registry,
    reset_project_knowledge_registry,
)


def _write(
    store: InMemoryDocumentStore,
    *,
    content: str,
    user_id: str,
    ingest_id: str,
    expires_at: str | None = None,
    dimension: int = 8,
) -> None:
    meta = {"user_id": user_id, "ingest_id": ingest_id}
    if expires_at is not None:
        meta["expires_at"] = expires_at
    embedder = build_document_embedder(mode="mock", dimension=dimension)
    docs = embedder.run(
        documents=[Document(content=content, meta=meta)]
    )["documents"]
    store.write_documents(docs)


def test_delete_ingest_chunks_isolates_other_ingest() -> None:
    store = InMemoryDocumentStore()
    _write(store, content="keep me excavator", user_id="u1", ingest_id="ing_keep")
    _write(store, content="drop me crane", user_id="u1", ingest_id="ing_drop")
    _write(store, content="other user boom", user_id="u2", ingest_id="ing_other")

    deleted = delete_ingest_chunks(store, user_id="u1", ingest_id="ing_drop")
    assert deleted == 1

    remaining = list(store.filter_documents() or [])
    assert len(remaining) == 2
    ids = {(d.meta.get("user_id"), d.meta.get("ingest_id")) for d in remaining}
    assert ("u1", "ing_keep") in ids
    assert ("u2", "ing_other") in ids
    assert ("u1", "ing_drop") not in ids


def test_purge_expired_chunks_only_expired() -> None:
    store = InMemoryDocumentStore()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    _write(
        store,
        content="expired chunk",
        user_id="u",
        ingest_id="ing_old",
        expires_at=past,
    )
    _write(
        store,
        content="fresh chunk",
        user_id="u",
        ingest_id="ing_new",
        expires_at=future,
    )
    _write(
        store,
        content="no ttl chunk",
        user_id="u",
        ingest_id="ing_forever",
        expires_at=None,
    )

    n = purge_expired_chunks(store, now=datetime.now(UTC))
    assert n == 1
    remaining = list(store.filter_documents() or [])
    assert len(remaining) == 2
    contents = {d.content for d in remaining}
    assert "expired chunk" not in contents
    assert "fresh chunk" in contents
    assert "no ttl chunk" in contents


def test_discard_session_deletes_chunks_and_registry() -> None:
    reset_project_knowledge_registry()
    store = InMemoryDocumentStore()
    _write(store, content="session chunk", user_id="u", ingest_id="ing_x")
    reg = get_project_knowledge_registry()
    reg.put(
        ProjectKnowledgeSession(
            user_id="u",
            ingest_id="ing_x",
            document_store=store,
        )
    )
    assert discard_project_knowledge_session("u", "ing_x") is True
    assert len(list(store.filter_documents() or [])) == 0
    try:
        reg.get("u", "ing_x")
        raise AssertionError("session should be gone")
    except NotFoundError as exc:
        assert "not found" in str(exc).lower()
