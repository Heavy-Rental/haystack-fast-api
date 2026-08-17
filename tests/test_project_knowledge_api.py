"""HTTP: ingest project-spec then multi-agent Q&A."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.config import get_settings
from app.main import create_app
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.pipeline import build_indexing_pipeline
from app.services.indexing import IndexingIngestService

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
    # HTTP ingest registers the session in-process for the following Q&A call.
    ingest_resp = api_client.post(
        "/internal/v1/recommendations/submitprojectspecification",
        json={
            "user_id": "api_user",
            "project_text": PROJECT_TEXT,
        },
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    body = ingest_resp.json()
    assert body["ingest_id"].startswith("ing_")
    assert body["user_id"] == "api_user"
    assert "excavator" in body["user_requirement_summary"].lower()
    assert "kg_built" not in body
    ingest_id = body["ingest_id"]

    # Call 3 chatbot Q&A (moved from getassetrecommendations)
    qa = api_client.post(
        "/internal/v1/recommendations/project-knowledge/query",
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

    # Call 2 recommend / quote
    rec = api_client.post(
        "/internal/v1/recommendations/project-knowledge/getassetrecommendations",
        json={
            "user_id": "api_user",
            "ingest_id": ingest_id,
            "query": "Need excavator for soft clay",
        },
    )
    assert rec.status_code == 200, rec.text
    quote = rec.json()
    assert quote["user_id"] == "api_user"
    assert quote["ingest_id"] == ingest_id
    assert quote["quoteRef"].startswith("QUO-")
    assert "items" in quote
    assert "answer" not in quote
    # When seed fleet matches excavator, expect at least one item with asset id
    if quote["items"]:
        assert quote["items"][0]["equipment"]["id"]
        assert quote["items"][0]["rankOrder"] >= 1


def test_query_missing_session_404(api_client: TestClient) -> None:
    resp = api_client.post(
        "/internal/v1/recommendations/project-knowledge/query",
        json={
            "user_id": "nobody",
            "ingest_id": "ing_missing",
            "query": "anything",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_recommend_missing_session_404(api_client: TestClient) -> None:
    resp = api_client.post(
        "/internal/v1/recommendations/project-knowledge/getassetrecommendations",
        json={
            "user_id": "nobody",
            "ingest_id": "ing_missing",
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
