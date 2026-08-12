"""S7.3 — Recommend graph fan-out (Phase 7).

BDD scenarios (implementation-plan Stage S7.3):

Feature: Delegator fans out Workers per need with a configurable cap

  Scenario: Multi-need invokes fleet once per need_id
    Given a fixture decomposer returning need_access and need_earthwork
    When  the graph runs
    Then  the fleet worker runs once per need_id

  Scenario: fanout_cap=1 serializes need pipelines
    Given two needs and fanout_cap=1
    When  the graph runs
    Then  sequence is fleet(A), price(A), fleet(B), price(B)

  Scenario: fanout_cap>=2 batches fleet then price
    Given two needs and fanout_cap=2
    When  the graph runs
    Then  both fleets complete before either price
    And   price(X) still never precedes fleet(X)
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.agents.recommend_graph import run_recommend_graph
from app.agents.tool_factory import build_recommend_tool_catalog
from app.schemas.recommendations import DecomposedNeed

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


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


def _run(*, fanout_cap: int):
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(
        backend="fake", assets=assets, bookings=bookings
    )
    return run_recommend_graph(
        user_id="u-test",
        ingest_id="ing-test",
        indexing_ok=True,
        source_text="Need a scissors lift and an excavator.",
        start_date="2026-09-01",
        end_date="2026-09-14",
        catalog=catalog,
        decomposer=FixtureTwoNeedDecomposer(),
        fanout_cap=fanout_cap,
        price_fn=_price_fn,
    )


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


def test_multi_need_fleet_once_per_need_id() -> None:
    """Scenario: Multi-need invokes fleet once per need_id."""
    state = _run(fanout_cap=2)
    starts = _worker_starts(state["tool_traces"])
    fleet_ids = [nid for node, nid in starts if node == "fleet_worker"]
    assert Counter(fleet_ids) == {"need_access": 1, "need_earthwork": 1}
    assert "need_access" in state["fleet_by_need"]
    assert "need_earthwork" in state["fleet_by_need"]


def test_fanout_cap_1_serializes_need_pipelines() -> None:
    """Scenario: fanout_cap=1 serializes need pipelines."""
    state = _run(fanout_cap=1)
    starts = _worker_starts(state["tool_traces"])
    assert starts == [
        ("fleet_worker", "need_access"),
        ("pricing_worker", "need_access"),
        ("fleet_worker", "need_earthwork"),
        ("pricing_worker", "need_earthwork"),
    ]


def test_fanout_cap_2_batches_fleet_then_price() -> None:
    """Scenario: fanout_cap>=2 batches fleet then price."""
    state = _run(fanout_cap=2)
    starts = _worker_starts(state["tool_traces"])
    assert starts == [
        ("fleet_worker", "need_access"),
        ("fleet_worker", "need_earthwork"),
        ("pricing_worker", "need_access"),
        ("pricing_worker", "need_earthwork"),
    ]
    seen_fleet: set[str] = set()
    for node, need_id in starts:
        if node == "fleet_worker":
            seen_fleet.add(need_id)
        else:
            assert need_id in seen_fleet
