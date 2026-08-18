"""LangGraph multi-agent over project DocumentStore + KG-1."""

from pathlib import Path

import pytest
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.agents.graph import run_project_knowledge_agents
from app.agents.tools import TOOL_PROJECT_KG_QUERY, TOOL_PROJECT_VECTOR_SEARCH
from app.config import get_settings
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.pipeline import build_indexing_pipeline
from app.services.indexing import IndexingIngestService
from app.services.project_knowledge_session import get_project_knowledge_registry

PROJECT_TEXT = (
    "Site preparation for foundation work. "
    "Requires a 20-ton excavator operating on soft clay soil. "
    "Project timeline is 8 weeks from mobilisation."
)


def test_multi_agent_invokes_both_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("PROJECT_AGENT_MODE", "stub")
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    get_settings.cache_clear()

    store = InMemoryDocumentStore()
    service = IndexingIngestService(
        pipeline=build_indexing_pipeline(
            document_store=store,
            embedder=build_document_embedder(mode="mock", dimension=8),
        ),
        document_store=store,
    )
    ingest = service.ingest_from_project_spec(
        user_id="agent_user",
        project_text=PROJECT_TEXT,
    )
    session = get_project_knowledge_registry().get("agent_user", ingest.ingest_id)
    assert session.knowledge_graph is not None
    assert session.document_store.count_documents() >= 1

    result = run_project_knowledge_agents(
        session,
        query="What excavator capacity and soil conditions are required?",
        top_k=5,
        agent_mode="stub",
    )

    sources = list(result.get("sources_used") or [])
    assert TOOL_PROJECT_VECTOR_SEARCH in sources
    assert TOOL_PROJECT_KG_QUERY in sources

    traces = list(result.get("tool_traces") or [])
    tools_called = {t.get("tool") for t in traces}
    assert TOOL_PROJECT_VECTOR_SEARCH in tools_called
    assert TOOL_PROJECT_KG_QUERY in tools_called

    answer = str(result.get("final_answer") or "")
    assert "## Answer" in answer
    assert "Vector" in answer
    assert "Graph" in answer
    # Dual-source evidence should mention project content
    assert "excavator" in answer.lower() or "clay" in answer.lower()

    get_settings.cache_clear()
