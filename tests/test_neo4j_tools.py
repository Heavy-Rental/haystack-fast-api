"""S7.2 + S8.3 — Neo4j tools (templates; fake default; live Bolt + populate HTTP).

BDD scenarios (implementation-plan Stage S7.2 / S8.3):

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

Feature: Live Neo4j client (S8.3)

  Scenario: Default catalog stays fake
    Given unset / NEO4J_BACKEND=fake
    When  the recommend catalog is built
    Then  the backend is FakeNeo4jBackend

  Scenario: Populate with live-mode HTTP stub
    Given a populate URL and an HTTP stub
    When  trigger_neo4j_populate runs
    Then  the stub is POSTed immediately
    And   blocking is false

  Scenario: HTTP populate failure is unavailable
    Given the populate POST raises
    When  trigger_neo4j_populate runs
    Then  status is unavailable
    And   blocking is false
    And   no exception is raised

  Scenario: Recommend is not blocked when Neo4j is unavailable
    Given an unavailable Bolt backend
    When  run_recommend_graph runs with indexing_ok
    Then  fleet SQL tools still run
    And   neo4j_cypher_read is skipped (K-3)

  Scenario: Bolt mapper matches fixture templates
    Given fixture-shaped Bolt records
    When  templates run against the mapped backend
    Then  results match FakeNeo4jBackend
    And   :Document nodes are dropped
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.neo4j_tools import (
    _FLEET_NODES_CYPHER,
    _FLEET_RELS_CYPHER,
    TOOL_NEO4J_CYPHER_READ,
    TOOL_TRIGGER_NEO4J_POPULATE,
    BoltNeo4jBackend,
    FakeNeo4jBackend,
    FreeFormCypherRejected,
    UnavailableNeo4jBackend,
    UnknownNeo4jTemplateError,
    map_fleet_graph,
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
from app.config import Settings
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
    result = neo4j_cypher_read(template="asset_neighbors", asset_id="AST-SL-001", backend=backend)
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
    catalog = build_recommend_tool_catalog(backend="fake", assets=assets, bookings=bookings)
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
    neo4j_calls = [t for t in state["tool_traces"] if t.get("tool") == TOOL_NEO4J_CYPHER_READ]
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
    state = empty_recommend_state(user_id="u-test", ingest_id="ing-test", indexing_ok=True)
    state["project"]["needs"] = [
        {
            "need_id": "need_access",
            "description": "Need scissors lift",
            "equipment_hints": ["scissor lift"],
            "quantity": 1,
        }
    ]
    result = make_delegator(catalog=catalog)(state)
    fleet = next(item for item in result["work_plan"] if item["worker_kind"] == WORKER_KIND_FLEET)
    assert TOOL_NEO4J_CYPHER_READ in (fleet.get("skip_tools") or [])
    assert TOOL_NEO4J_CYPHER_READ not in fleet["tool_allowlist"]


def test_delegator_includes_neo4j_when_graph_present() -> None:
    backend = FakeNeo4jBackend.from_fixture(FIXTURES / "neo4j_graph.json")
    catalog = build_recommend_tool_catalog(backend="fake", neo4j=backend)
    state = empty_recommend_state(user_id="u-test", ingest_id="ing-test", indexing_ok=True)
    state["project"]["needs"] = [
        {
            "need_id": "need_access",
            "description": "Need scissors lift",
            "equipment_hints": ["scissor lift"],
            "quantity": 1,
        }
    ]
    result = make_delegator(catalog=catalog)(state)
    fleet = next(item for item in result["work_plan"] if item["worker_kind"] == WORKER_KIND_FLEET)
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
    notes = state["fleet_by_need"]["need_access"].get("graph_notes") or []
    note_ids = {n.get("id") for n in notes}
    assert "ATT-SL-RAIL" in note_ids
    assert "kg-2" in (state["fleet_by_need"]["need_access"].get("source_tables") or [])


def test_catalog_default_neo4j_is_fake() -> None:
    """Scenario: Default catalog stays fake."""
    catalog = build_recommend_tool_catalog(backend="fake")
    assert isinstance(catalog.neo4j, FakeNeo4jBackend)
    assert catalog.neo4j.is_available is True
    assert catalog.neo4j.is_empty is True


def test_catalog_respects_fake_settings() -> None:
    settings = Settings(neo4j_backend="fake")
    catalog = build_recommend_tool_catalog(backend="fake", settings=settings)
    assert isinstance(catalog.neo4j, FakeNeo4jBackend)


def test_populate_live_http_stub() -> None:
    """Scenario: Populate with live-mode HTTP stub."""
    posts: list[str] = []

    def http_post(url: str) -> dict:
        posts.append(url)
        return {"status": "accepted", "job_id": "pack-abc"}

    job = trigger_neo4j_populate(
        backend=FakeNeo4jBackend(),
        populate_url="http://neo4j-populate:8089/v1/populate",
        http_post=http_post,
    )
    assert posts == ["http://neo4j-populate:8089/v1/populate"]
    assert job["blocking"] is False
    assert job["status"] == "accepted"
    assert job["job_id"] == "pack-abc"


def test_populate_http_failure_unavailable() -> None:
    """Scenario: HTTP populate failure is unavailable."""

    def http_post(url: str) -> dict:
        del url
        raise TimeoutError("populate timed out")

    job = trigger_neo4j_populate(
        populate_url="http://neo4j-populate:8089/v1/populate",
        http_post=http_post,
    )
    assert job["blocking"] is False
    assert job["status"] == "unavailable"
    assert str(job["job_id"]).startswith("neo4j_pop_")


def test_catalog_bolt_populate_uses_url() -> None:
    posts: list[str] = []

    def http_post(url: str) -> dict:
        posts.append(url)
        return {"status": "queued"}

    settings = Settings(
        neo4j_backend="bolt",
        neo4j_populate_url="http://neo4j-populate:8089/v1/populate",
    )
    catalog = build_recommend_tool_catalog(
        backend="fake",
        settings=settings,
        neo4j=UnavailableNeo4jBackend(),
        populate_url=settings.neo4j_populate_url,
        populate_http=http_post,
    )
    job = catalog.get(TOOL_TRIGGER_NEO4J_POPULATE)()
    assert posts == ["http://neo4j-populate:8089/v1/populate"]
    assert job["blocking"] is False
    assert job["status"] == "queued"


def test_recommend_not_blocked_when_neo4j_unavailable() -> None:
    """Scenario: Recommend is not blocked when Neo4j is unavailable (K-3)."""
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(
        backend="fake",
        assets=assets,
        bookings=bookings,
        neo4j=UnavailableNeo4jBackend(),
    )
    assert catalog.neo4j.is_available is False
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
    neo4j_calls = [t for t in state["tool_traces"] if t.get("tool") == TOOL_NEO4J_CYPHER_READ]
    assert neo4j_calls == []

    plan_fleet = [
        item
        for item in (state.get("work_plan") or [])
        if item.get("worker_kind") == WORKER_KIND_FLEET
    ]
    assert plan_fleet
    assert TOOL_NEO4J_CYPHER_READ in (plan_fleet[0].get("skip_tools") or [])
    results = state["recommendation"]["results_by_need"]
    assert results
    assert results[0]["need_id"] == "need_access"


def test_bolt_mapper_matches_fixture_templates() -> None:
    """Scenario: Bolt mapper matches fixture templates."""
    fake = FakeNeo4jBackend.from_fixture(FIXTURES / "neo4j_graph.json")
    raw_nodes = [
        {
            "labels": [node["label"]],
            "properties": {
                "id": node["id"],
                "category": node.get("category"),
                **(node.get("properties") or {}),
            },
        }
        for node in fake.nodes()
    ]
    raw_rels = [
        {"from": rel["from"], "to": rel["to"], "type": rel["type"]} for rel in fake.relationships()
    ]
    nodes, rels = map_fleet_graph(raw_nodes, raw_rels)
    backend = BoltNeo4jBackend.from_mapped(nodes, rels)
    assert backend.is_available is True
    assert backend.is_empty is False

    for template, kwargs in (
        ("asset_neighbors", {"asset_id": "AST-SL-001"}),
        ("assets_by_category", {"category": "scissor lift"}),
        ("compatible_attachments", {"asset_id": "AST-SL-001"}),
    ):
        live = neo4j_cypher_read(template=template, backend=backend, **kwargs)
        expected = neo4j_cypher_read(template=template, backend=fake, **kwargs)
        assert {row["id"] for row in live} == {row["id"] for row in expected}


def test_bolt_cypher_avoids_missing_document_label_token() -> None:
    """Negative Document filter must not use `:Document` (Neo4j 01N50)."""
    for cypher in (_FLEET_NODES_CYPHER, _FLEET_RELS_CYPHER):
        assert ":Document" not in cypher
        assert "'Document' IN labels(" in cypher


def test_bolt_mapper_drops_document_labels() -> None:
    """Scenario: :Document nodes are dropped."""
    nodes, rels = map_fleet_graph(
        [
            {"labels": ["Document"], "properties": {"id": "doc-1", "content": "spec"}},
            {
                "labels": ["Asset"],
                "properties": {"id": "AST-SL-001", "category": "scissor lift"},
            },
        ],
        [
            {"from": "doc-1", "to": "AST-SL-001", "type": "MENTIONS"},
            {"from": "AST-SL-001", "to": "AST-SL-001", "type": "SELF"},
        ],
    )
    ids = {node["id"] for node in nodes}
    assert "doc-1" not in ids
    assert "AST-SL-001" in ids
    assert all(rel["from"] != "doc-1" and rel["to"] != "doc-1" for rel in rels)
    assert any(rel["type"] == "SELF" for rel in rels)
