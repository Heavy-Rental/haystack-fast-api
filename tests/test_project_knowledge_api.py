"""HTTP: ingest project-spec then multi-agent Q&A."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.pipeline import build_indexing_pipeline
from app.services.indexing import IndexingIngestService
from haystack.document_stores.in_memory import InMemoryDocumentStore


PROJECT_TEXT = (
    "Requires a 20-ton excavator on soft clay. Timeline is 8 weeks."
)


@pytest.fixture
def api_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    get_settings.cache_clear()
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("PROJECT_AGENT_MODE", "stub")
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def test_ingest_then_project_knowledge_query(api_client: TestClient) -> None:
    # Use service path with known store so HTTP Q&A can find the session
    # registered by the same process (TestClient shares app process).
    store = InMemoryDocumentStore()
    ingest_service = IndexingIngestService(
        pipeline=build_indexing_pipeline(
            document_store=store,
            embedder=build_document_embedder(mode="mock", dimension=8),
        ),
        document_store=store,
    )
    # Prefer HTTP ingest (registers session with default settings dim=384)
    # Override settings already mock+8; IndexingIngestService() uses settings.
    ingest_resp = api_client.post(
        "/api/v1/recommendations/from-project-spec",
        json={
            "user_id": "api_user",
            "project_text": PROJECT_TEXT,
        },
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    body = ingest_resp.json()
    assert body["kg_built"] is True
    ingest_id = body["ingest_id"]

    qa = api_client.post(
        "/api/v1/recommendations/project-knowledge/query",
        json={
            "user_id": "api_user",
            "ingest_id": ingest_id,
            "query": "What excavator and soil conditions are specified?",
        },
    )
    assert qa.status_code == 200, qa.text
    data = qa.json()
    assert data["user_id"] == "api_user"
    assert data["ingest_id"] == ingest_id
    assert data["answer"]
    assert "project_vector_search" in data["sources_used"]
    assert "project_kg_query" in data["sources_used"]
    tools = {t["tool"] for t in data["tool_traces"]}
    assert "project_vector_search" in tools
    assert "project_kg_query" in tools


def test_query_missing_session_404(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/recommendations/project-knowledge/query",
        json={
            "user_id": "nobody",
            "ingest_id": "ing_missing",
            "query": "anything",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_service_registers_session_for_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("PROJECT_AGENT_MODE", "stub")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    get_settings.cache_clear()

    store = InMemoryDocumentStore()
    result = IndexingIngestService(
        pipeline=build_indexing_pipeline(
            document_store=store,
            embedder=build_document_embedder(mode="mock", dimension=8),
        ),
        document_store=store,
    ).ingest_from_project_spec(
        user_id="svc_user",
        project_text=PROJECT_TEXT,
    )
    from app.services.project_knowledge_qa import ProjectKnowledgeQAService

    qa = ProjectKnowledgeQAService().ask(
        user_id="svc_user",
        ingest_id=result.ingest_id,
        query="excavator soft clay",
    )
    assert "project_vector_search" in qa.sources_used
    assert "project_kg_query" in qa.sources_used
    get_settings.cache_clear()
