"""Phase 5.4: tenant isolation on vector retrieval (shared store, default CI)."""

from __future__ import annotations

from haystack.dataclasses import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.agents.tools import build_project_vector_search_tool
from app.config import Settings
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.retrieval import run_vector_search
from app.services.indexing import IndexingIngestService
from app.services.project_knowledge_session import (
    ProjectKnowledgeSession,
    get_project_knowledge_registry,
)


def _embed_and_write(
    store: InMemoryDocumentStore,
    *,
    content: str,
    user_id: str,
    ingest_id: str,
    dimension: int = 8,
) -> None:
    embedder = build_document_embedder(mode="mock", dimension=dimension)
    docs = embedder.run(
        documents=[
            Document(
                content=content,
                meta={"user_id": user_id, "ingest_id": ingest_id},
            )
        ]
    )["documents"]
    store.write_documents(docs)


def test_shared_store_filter_isolates_users() -> None:
    store = InMemoryDocumentStore()
    dim = 8
    _embed_and_write(
        store,
        content="User Alpha needs a 20-ton excavator on soft clay.",
        user_id="user_a",
        ingest_id="ing_a",
        dimension=dim,
    )
    _embed_and_write(
        store,
        content="User Bravo needs a boom lift for facade work.",
        user_id="user_b",
        ingest_id="ing_b",
        dimension=dim,
    )

    hits_a = run_vector_search(
        store,
        "excavator soft clay",
        top_k=10,
        mode="mock",
        dimension=dim,
        user_id="user_a",
        ingest_id="ing_a",
    )
    assert len(hits_a) >= 1
    for hit in hits_a:
        assert hit["meta"]["user_id"] == "user_a"
        assert hit["meta"]["ingest_id"] == "ing_a"
        assert "excavator" in hit["content"].lower()

    hits_b = run_vector_search(
        store,
        "boom lift facade",
        top_k=10,
        mode="mock",
        dimension=dim,
        user_id="user_b",
        ingest_id="ing_b",
    )
    assert len(hits_b) >= 1
    for hit in hits_b:
        assert hit["meta"]["user_id"] == "user_b"
        assert "boom" in hit["content"].lower()

    # Cross-tenant: user_a filter must not surface user_b content even on boom query
    cross = run_vector_search(
        store,
        "boom lift facade",
        top_k=10,
        mode="mock",
        dimension=dim,
        user_id="user_a",
        ingest_id="ing_a",
    )
    for hit in cross:
        assert hit["meta"]["user_id"] == "user_a"
        assert "boom" not in hit["content"].lower() or hit["meta"]["user_id"] == "user_a"


def test_tool_always_scopes_to_session_tenant() -> None:
    store = InMemoryDocumentStore()
    dim = 8
    settings = Settings(INDEXING_EMBEDDER="mock", INDEXING_EMBEDDING_DIM=dim)
    _embed_and_write(
        store,
        content="Secret tenant A only excavator brief",
        user_id="tenant_a",
        ingest_id="ing_a",
        dimension=dim,
    )
    _embed_and_write(
        store,
        content="Secret tenant B only crane brief",
        user_id="tenant_b",
        ingest_id="ing_b",
        dimension=dim,
    )
    session_a = ProjectKnowledgeSession(
        user_id="tenant_a",
        ingest_id="ing_a",
        document_store=store,
    )
    tool = build_project_vector_search_tool(session_a, settings=settings, default_top_k=5)
    hits = tool("crane excavator brief")
    assert hits
    for hit in hits:
        assert hit["meta"]["user_id"] == "tenant_a"
        assert hit["meta"]["ingest_id"] == "ing_a"
        assert "tenant b" not in hit["content"].lower()


def test_ingest_writes_tenant_meta_on_store() -> None:
    """Stored chunks must carry user_id + ingest_id (filter precondition)."""
    svc = IndexingIngestService()
    resp = svc.ingest_from_project_spec(
        user_id="meta_user",
        project_text="Need a scissor lift for indoor atrium work.",
    )
    session = get_project_knowledge_registry().get("meta_user", resp.ingest_id)
    docs = list(session.document_store.filter_documents() or [])
    assert docs
    for doc in docs:
        meta = dict(doc.meta or {})
        assert meta.get("user_id") == "meta_user"
        assert meta.get("ingest_id") == resp.ingest_id
