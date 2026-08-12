"""project_vector_search tool / retrieval pipeline."""

from haystack.dataclasses import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.agents.tools import (
    TOOL_PROJECT_VECTOR_SEARCH,
    build_project_vector_search_tool,
)
from app.config import Settings
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.retrieval import run_vector_search
from app.services.project_knowledge_session import ProjectKnowledgeSession


def test_run_vector_search_returns_chunk() -> None:
    store = InMemoryDocumentStore()
    embedder = build_document_embedder(mode="mock", dimension=8)
    docs = embedder.run(
        documents=[
            Document(
                content="Site requires a 20-ton excavator on soft clay within 8 weeks."
            )
        ]
    )["documents"]
    store.write_documents(docs)

    hits = run_vector_search(
        store,
        "excavator capacity soft clay",
        top_k=3,
        mode="mock",
        dimension=8,
    )
    assert len(hits) >= 1
    assert "excavator" in hits[0]["content"].lower()


def test_vector_tool_wrapper() -> None:
    # Tool reads embedder mode/dim from Settings — keep store embeddings in sync.
    dim = 8
    settings = Settings(INDEXING_EMBEDDER="mock", INDEXING_EMBEDDING_DIM=dim)
    store = InMemoryDocumentStore()
    embedder = build_document_embedder(mode="mock", dimension=dim)
    docs = embedder.run(
        documents=[Document(content="Boom lift for facade work")]
    )["documents"]
    store.write_documents(docs)
    session = ProjectKnowledgeSession(
        user_id="u",
        ingest_id="ing",
        document_store=store,
    )
    tool = build_project_vector_search_tool(
        session, settings=settings, default_top_k=2
    )
    assert tool.name == TOOL_PROJECT_VECTOR_SEARCH
    assert "DocumentStore" in tool.description or "document" in tool.description.lower()
    hits = tool("boom lift")
    assert isinstance(hits, list)
    assert len(hits) >= 1
    assert "boom" in hits[0]["content"].lower()
