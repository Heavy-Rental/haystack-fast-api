"""S7.3 — Recommend LangGraph DAG order + gate refuse (Phase 7).

BDD scenarios (implementation-plan Stage S7.3):

Feature: Recommend graph respects must-seq fleet→price and indexing gate

  Scenario: Never price before fleet for the same need
    Given recording fake fleet + price tools and two needs
    When  run_recommend_graph runs with indexing_ok true
    Then  for each need_id, the first price call is after that need's fleet call

  Scenario: Gate fail refuses fleet and price
    Given indexing_ok false and recording fakes
    When  the recommend graph runs
    Then  fleet and price tools are never called
    And   results_by_need is empty with a gate warning

  Scenario: Stage-1 Q&A graph still isolated
    When  the Q&A graph module is inspected
    Then  it does not import or invoke recommend graph nodes
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

from app.agents.graph import build_project_knowledge_graph
from app.agents.recommend_graph import run_recommend_graph
from app.agents.tool_factory import build_recommend_tool_catalog
from app.schemas.recommendations import DecomposedNeed

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


class FixtureTwoNeedDecomposer:
    """Fixed two-need decomposer matching fleet_seed categories."""

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


def _seed() -> tuple[list[dict], list[dict]]:
    data = json.loads((FIXTURES / "fleet_seed.json").read_text(encoding="utf-8"))
    return data["assets"], data["bookings"]


def _recording_price(calls: list[tuple[str, str]]):
    def price_fn(**kwargs):
        need_id = str(kwargs.pop("_need_id", "") or "")
        asset_id = kwargs.get("asset_id")
        calls.append(("pricing_worker", need_id or str(asset_id)))
        return {
            "asset_id": asset_id,
            "daily_rate": 185.0,
            "total_price": 2590.0,
            "currency": "SGD",
            "model_version": "test-fixture",
            "was_clamped": False,
            "explanation": "fixture",
        }

    return price_fn


def _worker_starts(traces: list[dict]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for t in traces:
        if t.get("status") != "start":
            continue
        node = t.get("node")
        if node not in {"fleet_worker", "pricing_worker"}:
            continue
        out.append((str(node), str(t.get("need_id") or "")))
    return out


def test_never_price_before_fleet_for_same_need() -> None:
    """Scenario: Never price before fleet for the same need."""
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(backend="fake", assets=assets, bookings=bookings)
    price_calls: list[tuple[str, str]] = []

    state = run_recommend_graph(
        user_id="u-test",
        ingest_id="ing-test",
        indexing_ok=True,
        source_text="Need a scissors lift and an excavator.",
        start_date="2026-09-01",
        end_date="2026-09-14",
        catalog=catalog,
        decomposer=FixtureTwoNeedDecomposer(),
        fanout_cap=1,
        price_fn=_recording_price(price_calls),
    )

    starts = _worker_starts(state["tool_traces"])
    seen_fleet: set[str] = set()
    for node, need_id in starts:
        if node == "fleet_worker":
            seen_fleet.add(need_id)
        elif node == "pricing_worker":
            assert need_id in seen_fleet, f"price for {need_id!r} before fleet; starts={starts}"

    assert {"need_access", "need_earthwork"} <= seen_fleet
    assert price_calls  # pricing worker invoked


def test_gate_fail_refuses_fleet_and_price() -> None:
    """Scenario: Gate fail refuses fleet and price."""
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(backend="fake", assets=assets, bookings=bookings)
    price_calls: list[tuple[str, str]] = []

    state = run_recommend_graph(
        user_id="u-test",
        ingest_id="ing-test",
        indexing_ok=False,
        source_text="Need a scissors lift and an excavator.",
        catalog=catalog,
        decomposer=FixtureTwoNeedDecomposer(),
        fanout_cap=1,
        price_fn=_recording_price(price_calls),
    )

    starts = _worker_starts(state["tool_traces"])
    assert starts == []
    assert price_calls == []
    assert state["recommendation"]["results_by_need"] == []
    warnings = " ".join(state["recommendation"].get("warnings") or []).lower()
    assert "indexing" in warnings or "gate" in warnings
    gate_traces = [
        t
        for t in state["tool_traces"]
        if t.get("node") == "check_gate" and t.get("status") == "refused"
    ]
    assert gate_traces


def test_qa_graph_does_not_import_recommend_graph() -> None:
    """Scenario: Stage-1 Q&A graph still isolated."""
    qa_graph = sys.modules[build_project_knowledge_graph.__module__]

    source = inspect.getsource(qa_graph)
    assert "recommend_graph" not in source
    assert "run_recommend_graph" not in source
    assert "recommend_nodes" not in source
    assert not hasattr(qa_graph, "run_recommend_graph")

    # Compiled Q&A graph still uses Stage-1 node names (smoke; no session needed
    # beyond verifying the builder is the Q&A one).
    assert "research_agent" in source
    assert callable(build_project_knowledge_graph)
