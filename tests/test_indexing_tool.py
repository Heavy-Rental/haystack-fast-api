"""S3 — Agent indexing tool R1 + Coordinator gate [4].

BDD scenarios (implementation-plan Phase 3 / stage S3):

Feature: Coordinator gate indexing tool (forced non-LLM)

  Scenario: Tool parity with IndexingIngestService
    Given a project_text fixture with excavator language
    When  run_indexing_from_request is invoked
    And   IndexingIngestService is invoked with the same inputs
    Then  both produce lean fields (ingest_id, user_id, non-empty summary)
    And   a ProjectKnowledgeSession is registered for the tool path

  Scenario: Flag off leaves HTTP unchanged
    Given INDEXING_VIA_AGENT_GATE is false/default
    When  client POSTs submitprojectspecification
    Then  response is lean FR-IX-023 body (as-built)

  Scenario: Flag on uses forced non-LLM gate
    Given INDEXING_VIA_AGENT_GATE is true
    When  client POSTs submitprojectspecification with project_text
    Then  START→index_gate→END runs without LLM tool selection
    And   response DTO matches direct-service lean shape
    And   tool_traces include role=coordinator node=index_gate

  Scenario: MIME hard-fail parity
    Given unsupported binary upload
    When  tool or gated path runs
    Then  BadRequestError / HTTP 400
    And   indexing_ok is false in gate state

  Scenario: Gate failure sets indexing_ok false
    Given indexing fails inside the gate node
    When  graph completes failure handling
    Then  indexing_ok is false
    And   no silent success ingest_id is invented
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.exceptions import BadRequestError
from app.main import create_app
from app.services.indexing import IndexingIngestService, byte_stream_from_upload
from app.services.project_knowledge_session import get_project_knowledge_registry

ENDPOINT = "/internal/v1/recommendations/submitprojectspecification"

PROJECT_TEXT = (
    "Requires a 20-ton excavator on soft clay. Timeline is 8 weeks. "
    "Budget SGD 25000."
)

LEAN_KEYS = {
    "ingest_id",
    "user_id",
    "user_requirement_summary",
    "tentative_start_date",
    "tentative_end_date",
    "needs_summary",
    "expected_budget",
    "warnings",
}


def _assert_lean_fields(body: dict) -> None:
    assert set(body.keys()) <= LEAN_KEYS
    assert body["ingest_id"].startswith("ing_")
    assert body["user_id"]
    assert isinstance(body["user_requirement_summary"], str)
    assert body["user_requirement_summary"].strip()
    assert isinstance(body["warnings"], list)


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    get_settings.cache_clear()
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    monkeypatch.setenv("PROJECT_AGENT_MODE", "stub")
    # Default: flag off unless a test enables it
    monkeypatch.setenv("INDEXING_VIA_AGENT_GATE", "false")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Scenario: Tool parity with IndexingIngestService
# ---------------------------------------------------------------------------


def test_tool_parity_with_indexing_ingest_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given same project_text, tool and service produce lean parity + session."""
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    get_settings.cache_clear()

    from app.agents.tools import TOOL_RUN_INDEXING, run_indexing_from_request

    assert TOOL_RUN_INDEXING == "run_indexing_from_request"

    service = IndexingIngestService()
    service_result = service.ingest_from_project_spec(
        user_id="user_parity_svc",
        project_text=PROJECT_TEXT,
    )
    _assert_lean_fields(service_result.model_dump(mode="json"))

    tool_result = run_indexing_from_request(
        user_id="user_parity_tool",
        project_text=PROJECT_TEXT,
    )
    tool_body = tool_result.model_dump(mode="json")
    _assert_lean_fields(tool_body)
    assert tool_body["user_id"] == "user_parity_tool"
    assert "excavator" in tool_body["user_requirement_summary"].lower()

    # Session registered for Call 2 / Stage-1 tools
    session = get_project_knowledge_registry().get(
        "user_parity_tool", tool_result.ingest_id
    )
    assert session.document_store is not None
    assert session.user_id == "user_parity_tool"

    # Structural field parity (ids differ; shapes match)
    assert set(service_result.model_dump().keys()) == set(tool_result.model_dump().keys())
    assert type(service_result.needs_summary) is type(tool_result.needs_summary)


def test_tool_accepts_injected_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tool DI: injected IndexingIngestService is used (not a free-form path)."""
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    get_settings.cache_clear()

    from app.agents.tools import run_indexing_from_request

    calls: list[str] = []
    original = IndexingIngestService.ingest_from_project_spec

    def _counting(self, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs.get("user_id") or "")
        return original(self, **kwargs)

    monkeypatch.setattr(
        IndexingIngestService, "ingest_from_project_spec", _counting
    )
    svc = IndexingIngestService()
    result = run_indexing_from_request(
        user_id="user_di",
        project_text=PROJECT_TEXT,
        service=svc,
    )
    assert result.ingest_id.startswith("ing_")
    assert calls == ["user_di"]


# ---------------------------------------------------------------------------
# Scenario: Flag off leaves HTTP unchanged
# ---------------------------------------------------------------------------


def test_flag_off_http_unchanged(api_client: TestClient) -> None:
    """Given INDEXING_VIA_AGENT_GATE=false, HTTP returns lean body (as-built)."""
    settings = get_settings()
    assert settings.indexing_via_agent_gate is False

    response = api_client.post(
        ENDPOINT,
        json={
            "user_id": "user_flag_off",
            "project_text": PROJECT_TEXT,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    _assert_lean_fields(body)
    assert body["user_id"] == "user_flag_off"
    assert "excavator" in body["user_requirement_summary"].lower()
    assert "kg_built" not in body


# ---------------------------------------------------------------------------
# Scenario: Flag on uses forced non-LLM gate
# ---------------------------------------------------------------------------


def test_flag_on_uses_forced_non_llm_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given flag true, HTTP uses START→index_gate→END; same lean DTO."""
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    monkeypatch.setenv("INDEXING_VIA_AGENT_GATE", "true")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.indexing_via_agent_gate is True

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            ENDPOINT,
            json={
                "user_id": "user_flag_on",
                "project_text": PROJECT_TEXT,
            },
        )
    get_settings.cache_clear()

    assert response.status_code == 200, response.text
    body = response.json()
    _assert_lean_fields(body)
    assert body["user_id"] == "user_flag_on"
    assert "excavator" in body["user_requirement_summary"].lower()

    # Session still registered via service under the gate
    session = get_project_knowledge_registry().get(
        "user_flag_on", body["ingest_id"]
    )
    assert session is not None


def test_build_indexing_gate_graph_is_forced_non_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Graph is START → index_gate → END; no LLM research/synthesis nodes."""
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    get_settings.cache_clear()

    from app.agents.indexing_gate import (
        build_indexing_gate_graph,
        run_indexing_gate,
    )

    graph = build_indexing_gate_graph()
    # LangGraph compiled graph exposes nodes via get_graph or similar
    node_names = set(graph.get_graph().nodes.keys())
    # Expect index_gate; must not include Q&A agent nodes
    assert "index_gate" in node_names
    assert "research_agent" not in node_names
    assert "graph_agent" not in node_names
    assert "synthesis_agent" not in node_names

    final = run_indexing_gate(
        user_id="user_gate_graph",
        project_text=PROJECT_TEXT,
    )
    assert final.indexing_ok is True
    assert final.response is not None
    assert final.response.ingest_id.startswith("ing_")
    assert final.response.user_id == "user_gate_graph"
    assert "excavator" in final.response.user_requirement_summary.lower()

    # Observability: coordinator gate traces
    assert final.tool_traces
    gate_traces = [
        t
        for t in final.tool_traces
        if t.get("node") == "index_gate" or t.get("tool") == "run_indexing_from_request"
    ]
    assert gate_traces
    t0 = gate_traces[0]
    assert t0.get("role") == "coordinator"
    assert t0.get("node") == "index_gate"
    assert t0.get("tool") == "run_indexing_from_request"
    assert t0.get("indexing_ok") is True
    assert t0.get("ingest_id", "").startswith("ing_")


# ---------------------------------------------------------------------------
# Scenario: MIME hard-fail parity
# ---------------------------------------------------------------------------


def test_tool_mime_hard_fail_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unsupported MIME raises BadRequestError on tool path (parity with service)."""
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    get_settings.cache_clear()

    from app.agents.tools import run_indexing_from_request

    src = byte_stream_from_upload(
        raw=b"MZ\x00\x00",
        filename="tool.exe",
        content_type=None,
    )
    with pytest.raises(BadRequestError) as exc_info:
        run_indexing_from_request(user_id="user_mime", file_sources=[src])
    msg = str(exc_info.value.message).lower()
    assert "unsupported" in msg or "unclassified" in msg


def test_gate_mime_fail_sets_indexing_ok_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gate failure: indexing_ok=false; runner re-raises BadRequestError."""
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    get_settings.cache_clear()

    from app.agents.indexing_gate import run_indexing_gate

    src = byte_stream_from_upload(
        raw=b"MZ\x00\x00",
        filename="payload.bin",
        content_type=None,
    )
    with pytest.raises(BadRequestError):
        run_indexing_gate(user_id="user_gate_fail", file_sources=[src])

    # Direct graph invoke to inspect state after failure handling
    from app.agents.indexing_gate import build_indexing_gate_graph

    graph = build_indexing_gate_graph()
    state = graph.invoke(
        {
            "user_id": "user_gate_fail2",
            "file_sources": [src],
            "indexing_ok": False,
            "tool_traces": [],
        }
    )
    assert state.get("indexing_ok") is False
    assert not state.get("ingest_id")  # no silent success id
    traces = state.get("tool_traces") or []
    assert any(t.get("indexing_ok") is False for t in traces)


def test_flag_on_http_mime_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag on: unsupported multipart still returns HTTP 400."""
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "8")
    monkeypatch.setenv("INDEXING_VIA_AGENT_GATE", "true")
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            ENDPOINT,
            data={"user_id": "user_mime_http"},
            files={"file": ("payload.bin", b"\x00\x01\x02", "application/octet-stream")},
        )
    get_settings.cache_clear()
    assert response.status_code == 400
    body = response.json()
    assert body.get("error") == "bad_request"
    assert "message" in body


# ---------------------------------------------------------------------------
# Config default
# ---------------------------------------------------------------------------


def test_indexing_via_agent_gate_defaults_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INDEXING_VIA_AGENT_GATE", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    # Default must be safe (off) so production stays on direct service path
    assert settings.indexing_via_agent_gate is False
