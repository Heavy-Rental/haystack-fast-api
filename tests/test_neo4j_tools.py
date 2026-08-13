"""S7.2 — Neo4j tools (templates only, no-op until S8 / Phase 7).

BDD scenarios (implementation-plan Stage S7.2):

Feature: Allowlisted Neo4j tools (no-op until S8)

  Scenario: Empty backend returns empty list
    Given a FakeNeo4jBackend with no nodes
    When  neo4j_cypher_read(template="asset_neighbors", asset_id="AST-SL-001")
    Then  result is []

  Scenario: Free-form Cypher is rejected
    When  neo4j_cypher_read is called with cypher=... / query=... / raw_cypher=...
    Then  FreeFormCypherRejected is raised

  Scenario: Template query with fixture graph
    Given a fixture graph linking AST-SL-001 to an attachment
    When  neo4j_cypher_read(template="asset_neighbors", asset_id="AST-SL-001")
    Then  neighbors include the fixture node
    And   unknown template names are rejected

  Scenario: Populate trigger is non-blocking
    When  trigger_neo4j_populate runs
    Then  a job_id is returned immediately
    And   status is queued or noop
    And   blocking is false

  Scenario: Recommend is not blocked when Neo4j is empty
    Given default fake catalog (empty graph)
    When  run_recommend_graph runs with indexing_ok
    Then  fleet SQL tools still run
    And   neo4j_cypher_read is skipped (K-3)
    And   results_by_need is still produced
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.neo4j_tools import (
    TOOL_NEO4J_CYPHER_READ,
    TOOL_TRIGGER_NEO4J_POPULATE,
    FakeNeo4jBackend,
    FreeFormCypherRejected,
    UnknownNeo4jTemplateError,
    neo4j_cypher_read,
    trigger_neo4j_populate,
)
from app.agents.recommend_graph import run_recommend_graph
from app.agents.recommend_nodes import make_delegator
from app.agents.recommend_state import empty_recommend_state
from app.agents.tool_factory import (
    WORKER_KIND_FLEET,
    build_recommend_tool_catalog,
)
from app.schemas.recommendations import DecomposedNeed

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


def test_tool_names_stable_contracts() -> None:
    assert TOOL_NEO4J_CYPHER_READ == "neo4j_cypher_read"
    assert TOOL_TRIGGER_NEO4J_POPULATE == "trigger_neo4j_populate"


def test_empty_backend_returns_empty_list() -> None:
    """Scenario: Empty backend returns empty list."""
    backend = FakeNeo4jBackend()
    assert backend.is_empty is True
    result = neo4j_cypher_read(
        template="asset_neighbors", asset_id="AST-SL-001", backend=backend
    )
    assert result == []


def test_freeform_cypher_rejected() -> None:
    """Scenario: Free-form Cypher is rejected."""
    backend = FakeNeo4jBackend()
    for kwargs in (
        {"cypher": "MATCH (n) RETURN n"},
        {"query": "MATCH (n) RETURN n"},
        {"raw_cypher": "MATCH (n) RETURN n"},
        {"sql": "SELECT 1"},
    ):
        with pytest.raises(FreeFormCypherRejected):
            neo4j_cypher_read(template="asset_neighbors", backend=backend, **kwargs)


def test_template_query_with_fixture_graph() -> None:
    """Scenario: Template query with fixture graph."""
    backend = FakeNeo4jBackend.from_fixture(FIXTURES / "neo4j_graph.json")
    assert backend.is_empty is False

    neighbors = neo4j_cypher_read(
        template="asset_neighbors", asset_id="AST-SL-001", backend=backend
    )
    neighbor_ids = {row["id"] for row in neighbors}
    assert "ATT-SL-RAIL" in neighbor_ids
    assert "AST-SL-002" in neighbor_ids

    by_cat = neo4j_cypher_read(
        template="assets_by_category", category="scissor lift", backend=backend
    )
    assert {row["id"] for row in by_cat} == {"AST-SL-001", "AST-SL-002"}

    attachments = neo4j_cypher_read(
        template="compatible_attachments",
        asset_id="AST-SL-001",
        backend=backend,
    )
    assert {row["id"] for row in attachments} == {"ATT-SL-RAIL"}

    with pytest.raises(UnknownNeo4jTemplateError, match="invent_neighbors"):
        neo4j_cypher_read(template="invent_neighbors", backend=backend)


def test_populate_trigger_non_blocking() -> None:
    """Scenario: Populate trigger is non-blocking."""
    empty = trigger_neo4j_populate(backend=FakeNeo4jBackend())
    assert empty["blocking"] is False
    assert str(empty["job_id"]).startswith("neo4j_pop_")
    assert empty["status"] in {"queued", "noop"}
    assert empty["status"] == "noop"

    loaded = trigger_neo4j_populate(
        backend=FakeNeo4jBackend.from_fixture(FIXTURES / "neo4j_graph.json")
    )
    assert loaded["blocking"] is False
    assert str(loaded["job_id"]).startswith("neo4j_pop_")
    assert loaded["status"] == "queued"
    assert loaded["job_id"] != empty["job_id"]


def test_recommend_not_blocked_when_neo4j_empty() -> None:
    """Scenario: Recommend is not blocked when Neo4j is empty (K-3)."""
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(
        backend="fake", assets=assets, bookings=bookings
    )
    assert TOOL_NEO4J_CYPHER_READ in catalog
    assert catalog.neo4j.is_empty is True

    state = run_recommend_graph(
        user_id="u-test",
        ingest_id="ing-test",
        indexing_ok=True,
        source_text="Need a scissors lift.",
        start_date="2026-09-01",
        end_date="2026-09-14",
        catalog=catalog,
        decomposer=FixtureOneNeedDecomposer(),
        fanout_cap=1,
    )

    fleet_starts = [
        t
        for t in state["tool_traces"]
        if t.get("node") == "fleet_worker" and t.get("status") == "start"
    ]
    assert fleet_starts
    neo4j_calls = [
        t
        for t in state["tool_traces"]
        if t.get("tool") == TOOL_NEO4J_CYPHER_READ
    ]
    assert neo4j_calls == []

    plan_fleet = [
        item
        for item in (state.get("work_plan") or [])
        if item.get("worker_kind") == WORKER_KIND_FLEET
    ]
    assert plan_fleet
    assert TOOL_NEO4J_CYPHER_READ in (plan_fleet[0].get("skip_tools") or [])
    assert TOOL_NEO4J_CYPHER_READ not in (plan_fleet[0].get("tool_allowlist") or [])

    results = state["recommendation"]["results_by_need"]
    assert results
    assert results[0]["need_id"] == "need_access"


def test_delegator_skips_neo4j_when_empty() -> None:
    catalog = build_recommend_tool_catalog(backend="fake")
    state = empty_recommend_state(
        user_id="u-test", ingest_id="ing-test", indexing_ok=True
    )
    state["project"]["needs"] = [
        {
            "need_id": "need_access",
            "description": "Need scissors lift",
            "equipment_hints": ["scissor lift"],
            "quantity": 1,
        }
    ]
    result = make_delegator(catalog=catalog)(state)
    fleet = next(
        item
        for item in result["work_plan"]
        if item["worker_kind"] == WORKER_KIND_FLEET
    )
    assert TOOL_NEO4J_CYPHER_READ in (fleet.get("skip_tools") or [])
    assert TOOL_NEO4J_CYPHER_READ not in fleet["tool_allowlist"]


def test_delegator_includes_neo4j_when_graph_present() -> None:
    backend = FakeNeo4jBackend.from_fixture(FIXTURES / "neo4j_graph.json")
    catalog = build_recommend_tool_catalog(backend="fake", neo4j=backend)
    state = empty_recommend_state(
        user_id="u-test", ingest_id="ing-test", indexing_ok=True
    )
    state["project"]["needs"] = [
        {
            "need_id": "need_access",
            "description": "Need scissors lift",
            "equipment_hints": ["scissor lift"],
            "quantity": 1,
        }
    ]
    result = make_delegator(catalog=catalog)(state)
    fleet = next(
        item
        for item in result["work_plan"]
        if item["worker_kind"] == WORKER_KIND_FLEET
    )
    assert TOOL_NEO4J_CYPHER_READ in fleet["tool_allowlist"]
    assert TOOL_NEO4J_CYPHER_READ not in (fleet.get("skip_tools") or [])


def test_fleet_worker_attaches_graph_notes_when_available() -> None:
    assets, bookings = _seed()
    backend = FakeNeo4jBackend.from_fixture(FIXTURES / "neo4j_graph.json")
    catalog = build_recommend_tool_catalog(
        backend="fake", assets=assets, bookings=bookings, neo4j=backend
    )
    state = run_recommend_graph(
        user_id="u-test",
        ingest_id="ing-test",
        indexing_ok=True,
        source_text="Need a scissors lift.",
        start_date="2026-09-01",
        end_date="2026-09-14",
        catalog=catalog,
        decomposer=FixtureOneNeedDecomposer(),
        fanout_cap=1,
    )
    neo4j_ok = [
        t
        for t in state["tool_traces"]
        if t.get("tool") == TOOL_NEO4J_CYPHER_READ and t.get("status") == "ok"
    ]
    assert neo4j_ok
    notes = (state["fleet_by_need"]["need_access"].get("graph_notes") or [])
    note_ids = {n.get("id") for n in notes}
    assert "ATT-SL-RAIL" in note_ids
    assert "kg-2" in (state["fleet_by_need"]["need_access"].get("source_tables") or [])
