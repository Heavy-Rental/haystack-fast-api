"""S7.0 — RecommendAgentState + partition validation (Phase 7).

BDD scenarios (implementation-plan Stage S7.0):

Feature: Agents write only their state partition (F-2)

  Scenario: Fleet Worker cannot write recommendation
    Given a recommend state with indexing_ok true
    When  fleet_worker proposes a recommendation write
    Then  StateTransitionError is raised

  Scenario: Price for unknown asset_id is rejected
    Given fleet candidates for need_access without AST-UNKNOWN
    When  pricing_worker writes a price for AST-UNKNOWN
    Then  StateTransitionError is raised

  Scenario: Legal fleet_by_need[need_id] write is accepted
    Given indexing_ok true and empty fleet_by_need
    When  fleet_worker writes candidates for need_access
    Then  apply_partition_write succeeds
    And   fleet_by_need[need_id].candidates is populated

  Scenario: Gate false blocks fleet write
    Given run.indexing_ok is false
    When  fleet_worker writes fleet_by_need
    Then  StateTransitionError is raised
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.agents.recommend_state import (
    ROLE_COORDINATOR,
    ROLE_FLEET_WORKER,
    ROLE_PRICING_WORKER,
    StateTransitionError,
    apply_partition_write,
    empty_recommend_state,
    validate_state_transition,
    write_fleet_slice,
    write_price_rows,
)

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_empty_recommend_state_shape() -> None:
    state = empty_recommend_state(user_id="u1", ingest_id="ing1", indexing_ok=True)
    assert state["run"]["mode"] == "recommend"
    assert state["run"]["indexing_ok"] is True
    assert state["fleet_by_need"] == {}
    assert state["prices_by_need"] == {}
    assert state["recommendation"]["results_by_need"] == []
    assert state["tool_traces"] == []


def test_fleet_worker_cannot_write_recommendation() -> None:
    """Scenario: Fleet Worker cannot write recommendation."""
    current = _load("state_minimal.json")
    proposed = deepcopy(current)
    proposed["recommendation"] = {
        "results_by_need": [
            {
                "need_id": "need_access",
                "item": {"asset_id": "AST-SL-001"},
            }
        ],
        "warnings": [],
    }

    with pytest.raises(StateTransitionError, match="cannot write partitions"):
        validate_state_transition(ROLE_FLEET_WORKER, current, proposed)

    with pytest.raises(StateTransitionError):
        apply_partition_write(ROLE_FLEET_WORKER, current, proposed)


def test_price_for_unknown_asset_id_rejected() -> None:
    """Scenario: price for unknown asset_id rejected."""
    current = _load("state_minimal.json")
    current["fleet_by_need"] = {
        "need_access": {
            "candidates": [
                {
                    "asset_id": "AST-SL-001",
                    "category": "scissor lift",
                    "min_daily_rate": 120,
                    "max_daily_rate": 280,
                }
            ],
            "unavailable": [],
            "source_tables": ["assets"],
        }
    }
    proposed = deepcopy(current)
    proposed["prices_by_need"] = {
        "need_access": [
            {
                "asset_id": "AST-UNKNOWN",
                "daily_rate": 185.0,
                "currency": "SGD",
            }
        ]
    }

    with pytest.raises(StateTransitionError, match="unknown asset_id"):
        validate_state_transition(
            ROLE_PRICING_WORKER, current, proposed, need_id="need_access"
        )


def test_legal_fleet_by_need_write_ok() -> None:
    """Scenario: legal fleet_by_need[need_id] write OK."""
    current = _load("state_minimal.json")
    assert current["run"]["indexing_ok"] is True

    result = write_fleet_slice(
        current,
        "need_access",
        candidates=[
            {
                "asset_id": "AST-SL-001",
                "category": "scissor lift",
                "platform_height": 10.0,
                "condition": "GOOD",
                "min_daily_rate": 120,
                "max_daily_rate": 280,
            }
        ],
        unavailable=[],
        source_tables=["assets", "bookings"],
    )

    slice_ = result["fleet_by_need"]["need_access"]
    assert len(slice_["candidates"]) == 1
    assert slice_["candidates"][0]["asset_id"] == "AST-SL-001"
    assert slice_["source_tables"] == ["assets", "bookings"]
    # Other partitions unchanged
    assert result["recommendation"] == current["recommendation"]
    assert result["prices_by_need"] == {}


def test_gate_false_blocks_fleet_write() -> None:
    """Scenario: gate false blocks fleet write."""
    current = _load("state_gate_false.json")
    assert current["run"]["indexing_ok"] is False

    proposed = deepcopy(current)
    proposed["fleet_by_need"] = {
        "need_access": {
            "candidates": [{"asset_id": "AST-SL-001"}],
            "unavailable": [],
            "source_tables": ["assets"],
        }
    }

    with pytest.raises(StateTransitionError, match="indexing_ok is false"):
        validate_state_transition(
            ROLE_FLEET_WORKER, current, proposed, need_id="need_access"
        )

    with pytest.raises(StateTransitionError, match="indexing_ok is false"):
        write_fleet_slice(
            current,
            "need_access",
            candidates=[{"asset_id": "AST-SL-001"}],
        )


def test_legal_price_write_for_known_candidate() -> None:
    current = _load("state_minimal.json")
    current = write_fleet_slice(
        current,
        "need_access",
        candidates=[{"asset_id": "AST-SL-001", "category": "scissor lift"}],
    )
    result = write_price_rows(
        current,
        "need_access",
        [
            {
                "asset_id": "AST-SL-001",
                "daily_rate": 185.0,
                "currency": "SGD",
                "was_clamped": False,
                "model_version": "test",
            }
        ],
    )
    assert result["prices_by_need"]["need_access"][0]["daily_rate"] == 185.0


def test_silent_zero_price_rejected() -> None:
    current = _load("state_minimal.json")
    current = write_fleet_slice(
        current,
        "need_access",
        candidates=[{"asset_id": "AST-SL-001"}],
    )
    proposed = deepcopy(current)
    proposed["prices_by_need"] = {
        "need_access": [{"asset_id": "AST-SL-001", "daily_rate": 0.0}]
    }
    with pytest.raises(StateTransitionError, match="silent zero"):
        validate_state_transition(
            ROLE_PRICING_WORKER, current, proposed, need_id="need_access"
        )


def test_coordinator_cannot_invent_asset_id() -> None:
    current = _load("state_minimal.json")
    current["fleet_by_need"] = {
        "need_access": {
            "candidates": [{"asset_id": "AST-SL-001"}],
            "unavailable": [],
            "source_tables": ["assets"],
        }
    }
    proposed = deepcopy(current)
    proposed["recommendation"] = {
        "results_by_need": [
            {"need_id": "need_access", "item": {"asset_id": "AST-HALLUCINATED"}}
        ],
        "warnings": [],
    }
    with pytest.raises(StateTransitionError, match="cannot invent asset_id"):
        validate_state_transition(ROLE_COORDINATOR, current, proposed)


def test_unknown_role_rejected() -> None:
    current = empty_recommend_state(indexing_ok=True)
    with pytest.raises(StateTransitionError, match="unknown role"):
        validate_state_transition("mega_agent", current, current)


def test_fleet_worker_cannot_write_other_need_slice() -> None:
    current = _load("state_minimal.json")
    current["fleet_by_need"] = {
        "need_access": {
            "candidates": [{"asset_id": "AST-SL-001"}],
            "unavailable": [],
            "source_tables": ["assets"],
        }
    }
    proposed = deepcopy(current)
    proposed["fleet_by_need"] = {
        **current["fleet_by_need"],
        "need_earthwork": {
            "candidates": [{"asset_id": "AST-EX-001"}],
            "unavailable": [],
            "source_tables": ["assets"],
        },
    }
    with pytest.raises(StateTransitionError, match="cannot write"):
        validate_state_transition(
            ROLE_FLEET_WORKER, current, proposed, need_id="need_access"
        )
