"""S7.6 — tool_traces contract (role, need_id, duration_ms).

BDD scenarios (implementation-plan Stage S7.6):

Feature: Recommend graph emits G-1 tool_traces

  Scenario: After graph run, traces include worker roles
    Given fixture catalog and indexing_ok true
    When  run_recommend_graph completes
    Then  traces include role coordinator, delegator, and worker
    And   nodes include check_gate, project_worker, delegator,
          fleet_worker, pricing_worker, synthesis

  Scenario: Fan-out traces have need_id
    Given two fixture needs
    When  the graph runs
    Then  every fleet_worker and pricing_worker trace has need_id

  Scenario: Duration is non-negative
    Given a completed graph run
    When  traces with status ok, completed, error, or refused are inspected
    Then  each has duration_ms >= 0

  Scenario: Empty fleet warning is present
    Given a catalog with no matching assets
    When  the graph runs
    Then  the need item is null
    And   warnings mention no fleet match
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.recommend_graph import run_recommend_graph
from app.agents.tool_factory import build_recommend_tool_catalog
from app.schemas.recommendations import DecomposedNeed

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"

TERMINAL_STATUSES = frozenset({"ok", "completed", "error", "refused"})
REQUIRED_ROLES = frozenset({"coordinator", "delegator", "worker"})
REQUIRED_NODES = frozenset(
    {
        "check_gate",
        "project_worker",
        "delegator",
        "fleet_worker",
        "pricing_worker",
        "synthesis",
    }
)


class FixtureTwoNeedDecomposer:
    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        del source_text
        return [
            DecomposedNeed(
                need_id="need_access",
                description="Need scissors lift for indoor elevated work ~8m",
                equipment_hints=["scissor lift"],
                quantity=1,
            ),
            DecomposedNeed(
                need_id="need_earthwork",
                description="Need excavator for site prep",
                equipment_hints=["excavator"],
                quantity=1,
            ),
        ]


class FixtureEmptyMatchDecomposer:
    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        del source_text
        return [
            DecomposedNeed(
                need_id="need_earthwork",
                description="Need a submarine for underwater work",
                equipment_hints=["submarine"],
                quantity=1,
            )
        ]


def _seed() -> tuple[list[dict], list[dict]]:
    data = json.loads((FIXTURES / "fleet_seed.json").read_text(encoding="utf-8"))
    return data["assets"], data["bookings"]


def _price_fn(**kwargs):
    return {
        "asset_id": kwargs.get("asset_id"),
        "daily_rate": 185.0,
        "total_price": 2590.0,
        "currency": "SGD",
        "model_version": "test-fixture",
        "was_clamped": False,
        "explanation": "fixture",
    }


def _run_happy():
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(
        backend="fake", assets=assets, bookings=bookings
    )
    return run_recommend_graph(
        user_id="u-traces",
        ingest_id="ing-traces",
        indexing_ok=True,
        source_text="Need a scissors lift and an excavator.",
        start_date="2026-09-01",
        end_date="2026-09-14",
        catalog=catalog,
        decomposer=FixtureTwoNeedDecomposer(),
        fanout_cap=2,
        price_fn=_price_fn,
    )


def test_traces_include_worker_roles_and_nodes() -> None:
    """Scenario: After graph run, traces include worker roles."""
    state = _run_happy()
    traces = state["tool_traces"]
    assert traces
    roles = {t.get("role") for t in traces}
    nodes = {t.get("node") for t in traces}
    assert REQUIRED_ROLES <= roles
    assert REQUIRED_NODES <= nodes


def test_fanout_traces_have_need_id() -> None:
    """Scenario: Fan-out traces have need_id."""
    state = _run_happy()
    fanout = [
        t
        for t in state["tool_traces"]
        if t.get("node") in {"fleet_worker", "pricing_worker"}
    ]
    assert fanout
    for event in fanout:
        assert event.get("need_id"), f"missing need_id on {event}"
    need_ids = {str(t["need_id"]) for t in fanout}
    assert {"need_access", "need_earthwork"} <= need_ids


def test_duration_ms_non_negative_on_terminal_spans() -> None:
    """Scenario: Duration is non-negative."""
    state = _run_happy()
    terminal = [
        t for t in state["tool_traces"] if t.get("status") in TERMINAL_STATUSES
    ]
    assert terminal
    for event in terminal:
        assert "duration_ms" in event, f"missing duration_ms on {event}"
        assert float(event["duration_ms"]) >= 0, event


def test_empty_fleet_warning_present() -> None:
    """Scenario: Empty fleet warning is present."""
    catalog = build_recommend_tool_catalog(backend="fake", assets=[], bookings=[])
    state = run_recommend_graph(
        user_id="u-traces",
        ingest_id="ing-empty",
        indexing_ok=True,
        source_text="Need a submarine.",
        catalog=catalog,
        decomposer=FixtureEmptyMatchDecomposer(),
        fanout_cap=1,
        price_fn=_price_fn,
    )
    rows = state["recommendation"]["results_by_need"]
    assert len(rows) == 1
    assert rows[0]["item"] is None
    blob = " ".join(rows[0].get("warnings") or []).lower()
    assert "fleet" in blob or "match" in blob
    fleet_traces = [
        t
        for t in state["tool_traces"]
        if t.get("node") == "fleet_worker" and t.get("need_id") == "need_earthwork"
    ]
    assert fleet_traces
