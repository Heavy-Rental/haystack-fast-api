"""S7.7 — Recommend tool DI factory + Delegator worker_kind allowlist (Phase 7).

BDD scenarios (implementation-plan Stage S7.7):

Feature: Tool DI injects fakes and Delegator stays allowlisted

  Scenario: DI injects fake fleet
    Given build_recommend_runtime with a fake catalog / seed assets
    When  the fleet worker tool is invoked
    Then  it returns the injected seed (not live SQL)

  Scenario: Delegator rejects unknown worker_kind
    Given a work_plan item with worker_kind="invent_stock"
    When  the Delegator / plan validator runs
    Then  UnknownWorkerKindError is raised and the item is not scheduled
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.fleet_tools import (
    TOOL_CHECK_BOOKING_AVAILABILITY,
    TOOL_FILTER_FLEET_CANDIDATES,
    TOOL_RETRIEVE_FLEET_ASSETS,
    UnknownToolError,
)
from app.agents.recommend_nodes import make_delegator, make_execute_needs
from app.agents.recommend_state import empty_recommend_state
from app.agents.tool_factory import (
    ALLOWED_WORKER_KINDS,
    WORKER_TOOL_ALLOWLISTS,
    UnknownWorkerKindError,
    build_recommend_runtime,
    build_recommend_tool_catalog,
    tools_for_worker,
    validate_work_plan,
)
from app.agents.tools import TOOL_PREDICT_ASSET_PRICE

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


def _seed() -> tuple[list[dict], list[dict]]:
    data = json.loads((FIXTURES / "fleet_seed.json").read_text(encoding="utf-8"))
    return data["assets"], data["bookings"]


def test_di_injects_fake_fleet() -> None:
    """Scenario: DI injects fake fleet."""
    assets, bookings = _seed()
    runtime = build_recommend_runtime(
        backend="fake",
        assets=assets,
        bookings=bookings,
        agent_mode="stub",
    )
    assert runtime.agent_mode == "stub"
    assert runtime.catalog.backend_kind == "fake"
    fleet = runtime.catalog.get(TOOL_RETRIEVE_FLEET_ASSETS)(category="scissor lift")
    assert {a["asset_id"] for a in fleet} == {"AST-SL-001", "AST-SL-002"}


def test_worker_kind_allowlists() -> None:
    assert ALLOWED_WORKER_KINDS == frozenset({"fleet_worker", "pricing_worker"})
    assert TOOL_RETRIEVE_FLEET_ASSETS in WORKER_TOOL_ALLOWLISTS["fleet_worker"]
    assert TOOL_FILTER_FLEET_CANDIDATES in WORKER_TOOL_ALLOWLISTS["fleet_worker"]
    assert TOOL_CHECK_BOOKING_AVAILABILITY in WORKER_TOOL_ALLOWLISTS["fleet_worker"]
    assert TOOL_PREDICT_ASSET_PRICE in WORKER_TOOL_ALLOWLISTS["pricing_worker"]
    assert TOOL_PREDICT_ASSET_PRICE not in WORKER_TOOL_ALLOWLISTS["fleet_worker"]
    assert tools_for_worker("fleet_worker") == WORKER_TOOL_ALLOWLISTS["fleet_worker"]


def test_delegator_rejects_unknown_worker_kind() -> None:
    """Scenario: Delegator rejects unknown worker_kind."""
    with pytest.raises(UnknownWorkerKindError, match="invent_stock"):
        validate_work_plan(
            [
                {
                    "worker_kind": "invent_stock",
                    "need_id": "need_access",
                    "tool_allowlist": [],
                }
            ]
        )

    with pytest.raises(UnknownWorkerKindError):
        tools_for_worker("invent_stock")


def test_execute_needs_refuses_unknown_worker_kind() -> None:
    catalog = build_recommend_tool_catalog(backend="fake")
    execute = make_execute_needs(catalog, fanout_cap=1)
    state = empty_recommend_state(
        user_id="u-test", ingest_id="ing-test", indexing_ok=True
    )
    state["project"]["needs"] = [
        {"need_id": "need_access", "description": "lift", "quantity": 1}
    ]
    state["work_plan"] = [
        {
            "worker_kind": "invent_stock",
            "need_id": "need_access",
            "tool_allowlist": [],
        }
    ]
    with pytest.raises(UnknownWorkerKindError, match="invent_stock"):
        execute(state)


def test_delegator_emits_only_allowlisted_kinds() -> None:
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
    result = make_delegator()(state)
    kinds = {item["worker_kind"] for item in result["work_plan"]}
    assert kinds <= ALLOWED_WORKER_KINDS
    validate_work_plan(result["work_plan"])
    for item in result["work_plan"]:
        allowed = WORKER_TOOL_ALLOWLISTS[item["worker_kind"]]
        assert list(item["tool_allowlist"]) == list(allowed)


def test_unknown_tool_still_rejected() -> None:
    runtime = build_recommend_runtime(backend="fake")
    with pytest.raises(UnknownToolError):
        runtime.catalog.get("recommend_everything")
