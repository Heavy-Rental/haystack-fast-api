"""S7.8 — Worker [5] live KG-1 tools (project_vector_search + project_kg_query).

BDD scenarios:

Feature: Project Worker [5] grounds needs in session KG-1 tools

  Scenario: Live tools run before decompose
    Given catalog tools for vector + KG-1 and a stub decomposer
    When  the project worker runs
    Then  both tools are invoked
    And   project.research_notes and project.graph_notes are populated
    And   project.needs[] is still produced

  Scenario: Empty retrieval is explicit
    Given tools that return []
    When  the project worker runs
    Then  notes say there were no hits
    And   decompose still runs

  Scenario: Missing tools do not block recommend
    Given a catalog without KG-1 tools
    When  the project worker runs
    Then  notes record the skip
    And   needs[] is still produced
    And   fleet tools are not called by Worker [5]

  Scenario: Tool error is soft-fail
    Given a vector tool that raises
    When  the project worker runs
    Then  notes mention unavailability
    And   decompose still runs
    And   no exception escapes
"""

from __future__ import annotations

import json
from pathlib import Path

from haystack.dataclasses import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.agents.recommend_graph import run_recommend_graph
from app.agents.recommend_nodes import make_project_worker
from app.agents.recommend_state import empty_recommend_state
from app.agents.tool_factory import build_recommend_tool_catalog
from app.agents.tools import (
    TOOL_PROJECT_KG_QUERY,
    TOOL_PROJECT_VECTOR_SEARCH,
    ProjectTool,
)
from app.config import Settings
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.schemas.recommendations import DecomposedNeed
from app.services.project_knowledge_session import ProjectKnowledgeSession

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


class FixtureOneNeedDecomposer:
    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        del source_text
        return [
            DecomposedNeed(
                need_id="need_access",
                description="Need scissors lift for indoor elevated work ~8m",
                equipment_hints=["scissor lift"],
                quantity=1,
            )
        ]


def _seed() -> tuple[list[dict], list[dict]]:
    data = json.loads((FIXTURES / "fleet_seed.json").read_text(encoding="utf-8"))
    return data["assets"], data["bookings"]


def _recording_tool(name: str, hits: list[dict], calls: list[str]) -> ProjectTool:
    def _run(query: str, top_k: int | None = None, limit: int | None = None) -> list[dict]:
        del top_k, limit
        calls.append(query)
        return list(hits)

    return ProjectTool(name=name, description=name, func=_run)


def test_project_worker_calls_vector_and_kg_before_decompose() -> None:
    """Scenario: Live tools run before decompose."""
    vector_calls: list[str] = []
    kg_calls: list[str] = []
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(
        backend="fake",
        assets=assets,
        bookings=bookings,
        project_vector_tool=_recording_tool(
            TOOL_PROJECT_VECTOR_SEARCH,
            [{"content": "Indoor elevated work ~8m scissors lift"}],
            vector_calls,
        ),
        project_kg_tool=_recording_tool(
            TOOL_PROJECT_KG_QUERY,
            [{"node_type": "document", "content_preview": "platform height 8m indoor"}],
            kg_calls,
        ),
    )
    state = empty_recommend_state(user_id="u-w5", ingest_id="ing-w5", indexing_ok=True)
    result = make_project_worker(
        "Need a scissors lift indoors at 8m.",
        catalog=catalog,
        decomposer=FixtureOneNeedDecomposer(),
    )(state)

    assert vector_calls
    assert kg_calls
    project = result["project"]
    assert "8m" in project["research_notes"] or "passage" in project["research_notes"]
    assert "platform" in project["graph_notes"] or "node" in project["graph_notes"]
    assert project["needs"]
    assert project["needs"][0]["need_id"] == "need_access"
    assert project.get("research_hits")
    assert project.get("graph_hits")

    traces = result["tool_traces"]
    tools = [t.get("tool") for t in traces if t.get("tool")]
    assert TOOL_PROJECT_VECTOR_SEARCH in tools
    assert TOOL_PROJECT_KG_QUERY in tools
    assert "decompose_project_needs" in tools
    vec_i = tools.index(TOOL_PROJECT_VECTOR_SEARCH)
    kg_i = tools.index(TOOL_PROJECT_KG_QUERY)
    dec_i = tools.index("decompose_project_needs")
    assert vec_i < dec_i
    assert kg_i < dec_i


def test_project_worker_empty_hits_are_explicit() -> None:
    """Scenario: Empty retrieval is explicit."""
    catalog = build_recommend_tool_catalog(
        backend="fake",
        project_vector_tool=_recording_tool(TOOL_PROJECT_VECTOR_SEARCH, [], []),
        project_kg_tool=_recording_tool(TOOL_PROJECT_KG_QUERY, [], []),
    )
    state = empty_recommend_state(user_id="u", ingest_id="ing", indexing_ok=True)
    result = make_project_worker(
        "Need equipment.",
        catalog=catalog,
        decomposer=FixtureOneNeedDecomposer(),
    )(state)
    notes = result["project"]["research_notes"].lower()
    graph = result["project"]["graph_notes"].lower()
    assert "no" in notes and ("hit" in notes or "passage" in notes)
    assert "no" in graph
    assert result["project"]["needs"][0]["need_id"] == "need_access"


def test_project_worker_missing_tools_do_not_block() -> None:
    """Scenario: Missing tools do not block recommend."""
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(backend="fake", assets=assets, bookings=bookings)
    assert TOOL_PROJECT_VECTOR_SEARCH not in catalog
    assert TOOL_PROJECT_KG_QUERY not in catalog

    state = run_recommend_graph(
        user_id="u-w5-skip",
        ingest_id="ing-w5-skip",
        indexing_ok=True,
        source_text="Need a scissors lift.",
        start_date="2026-09-01",
        end_date="2026-09-14",
        catalog=catalog,
        decomposer=FixtureOneNeedDecomposer(),
        fanout_cap=1,
    )
    project = state["project"]
    assert (
        "skip" in project["research_notes"].lower()
        or "not registered" in project["research_notes"].lower()
    )
    assert project["needs"]
    assert state["recommendation"]["results_by_need"]
    worker_tools = [
        t.get("tool")
        for t in state["tool_traces"]
        if t.get("node") == "project_worker" and t.get("tool")
    ]
    assert TOOL_PROJECT_VECTOR_SEARCH not in worker_tools
    assert "decompose_project_needs" in worker_tools


def test_project_worker_tool_error_is_soft_fail() -> None:
    """Scenario: Tool error is soft-fail."""

    def boom(query: str, top_k: int | None = None) -> list[dict]:
        del query, top_k
        raise RuntimeError("embedder exploded")

    catalog = build_recommend_tool_catalog(
        backend="fake",
        project_vector_tool=ProjectTool(
            name=TOOL_PROJECT_VECTOR_SEARCH,
            description="vector",
            func=boom,
        ),
        project_kg_tool=_recording_tool(TOOL_PROJECT_KG_QUERY, [], []),
    )
    state = empty_recommend_state(user_id="u", ingest_id="ing", indexing_ok=True)
    result = make_project_worker(
        "Need a lift.",
        catalog=catalog,
        decomposer=FixtureOneNeedDecomposer(),
    )(state)
    assert (
        "unavail" in result["project"]["research_notes"].lower()
        or "error" in result["project"]["research_notes"].lower()
    )
    assert result["project"]["needs"][0]["need_id"] == "need_access"


def test_catalog_registers_session_kg1_tools() -> None:
    dim = 8
    settings = Settings(INDEXING_EMBEDDER="mock", INDEXING_EMBEDDING_DIM=dim)
    store = InMemoryDocumentStore()
    embedder = build_document_embedder(mode="mock", dimension=dim)
    docs = embedder.run(
        documents=[
            Document(
                content="Indoor scissors lift 8m",
                meta={"user_id": "u-sess", "ingest_id": "ing-sess"},
            )
        ]
    )["documents"]
    store.write_documents(docs)
    session = ProjectKnowledgeSession(
        user_id="u-sess",
        ingest_id="ing-sess",
        document_store=store,
        knowledge_graph=None,
    )
    catalog = build_recommend_tool_catalog(
        backend="fake",
        project_session=session,
        settings=settings,
    )
    assert TOOL_PROJECT_VECTOR_SEARCH in catalog
    assert TOOL_PROJECT_KG_QUERY in catalog
    hits = catalog.get(TOOL_PROJECT_VECTOR_SEARCH)("scissors lift")
    assert isinstance(hits, list)
    kg = catalog.get(TOOL_PROJECT_KG_QUERY)("scissors")
    assert kg == []


def test_project_worker_does_not_invent_fleet_ids() -> None:
    catalog = build_recommend_tool_catalog(
        backend="fake",
        project_vector_tool=_recording_tool(
            TOOL_PROJECT_VECTOR_SEARCH,
            [{"content": "Use AST-INVENTED-999 from the yard"}],
            [],
        ),
        project_kg_tool=_recording_tool(TOOL_PROJECT_KG_QUERY, [], []),
    )
    state = empty_recommend_state(user_id="u", ingest_id="ing", indexing_ok=True)
    result = make_project_worker(
        "Need access equipment.",
        catalog=catalog,
        decomposer=FixtureOneNeedDecomposer(),
    )(state)
    needs = result["project"]["needs"]
    blob = json.dumps(needs)
    assert "AST-INVENTED-999" not in blob
    assert all("asset_id" not in need for need in needs)
