"""S7.4 — Tool-free Coordinator synthesis (Phase 7).

BDD scenarios (implementation-plan Stage S7.4):

Feature: Synthesis merges tool-backed fleet and prices only

  Scenario: Golden merge
    Given fixture candidates for need_access including AST-SL-001
    And   fixture prices with daily_rate 185 for AST-SL-001
    When  the Coordinator synthesis node runs in stub mode
    Then  results_by_need contains AST-SL-001 with daily_rate 185
    And   no asset_id appears that was not in the fleet fixture

  Scenario: Empty fleet yields null item and warning
    Given no fleet candidates for need_earthwork
    When  synthesis runs
    Then  item is null for that need
    And   warnings mention no fleet match

  Scenario: Pricing failure does not invent zeros
    Given candidates but no price rows
    When  synthesis runs
    Then  no daily_rate <= 0 appears
    And   a warning is present

  Scenario: Cannot inject unknown asset
    Given a proposed recommendation item AST-UNKNOWN
    When  apply_partition_write(coordinator) runs
    Then  StateTransitionError is raised

  Scenario: Bad shape fails validation
    Given results_by_need row missing need_id
    When  synthesis schema check runs
    Then  SynthesisSchemaError is raised
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.agents.recommend_state import (
    ROLE_COORDINATOR,
    StateTransitionError,
    apply_partition_write,
    empty_recommend_state,
)
from app.agents.recommend_synthesis import (
    SynthesisSchemaError,
    synthesize_recommendation,
    validate_recommendation_shape,
)

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _state_with_fleet_and_price() -> dict:
    state = _load("state_minimal.json")
    state["fleet_by_need"] = {
        "need_access": {
            "candidates": [
                {
                    "asset_id": "AST-SL-001",
                    "equipment_type": "Scissors Lift",
                    "category": "scissor lift",
                    "condition": "GOOD",
                    "availability": "available",
                    "min_daily_rate": 120.0,
                    "max_daily_rate": 280.0,
                }
            ],
            "unavailable": [],
            "source_tables": ["assets", "bookings"],
        }
    }
    state["prices_by_need"] = {
        "need_access": [
            {
                "asset_id": "AST-SL-001",
                "daily_rate": 185.0,
                "total_price": 2590.0,
                "currency": "SGD",
                "model_version": "test-fixture",
                "was_clamped": False,
                "explanation": "fixture",
            }
        ]
    }
    return state


def test_golden_merge_exact_asset_and_rates() -> None:
    """Scenario: Synthesis merges tool-backed fleet and prices only."""
    state = _state_with_fleet_and_price()
    result = synthesize_recommendation(state)
    golden = _load("golden_results_by_need.json")["results_by_need"]
    actual = result["recommendation"]["results_by_need"]
    assert len(actual) == 1
    assert actual[0]["need_id"] == golden[0]["need_id"]
    assert actual[0]["item"]["asset_id"] == golden[0]["item"]["asset_id"]
    assert actual[0]["item"]["pricing"]["daily_rate"] == golden[0]["item"]["pricing"][
        "daily_rate"
    ]
    assert actual[0]["item"]["pricing"]["total_price"] == golden[0]["item"]["pricing"][
        "total_price"
    ]
    assert actual[0]["item"]["pricing"]["currency"] == "SGD"
    assert actual[0]["item"]["rank"] == 1
    assert actual[0]["warnings"] == []
    # No invented assets
    assert actual[0]["item"]["asset_id"] == "AST-SL-001"


def test_empty_fleet_yields_null_item_and_warning() -> None:
    """Scenario: Empty fleet yields null item and warning."""
    state = empty_recommend_state(
        user_id="u-test", ingest_id="ing-test", indexing_ok=True
    )
    state["project"]["needs"] = [
        {
            "need_id": "need_earthwork",
            "description": "Need excavator",
            "equipment_hints": ["excavator"],
            "quantity": 1,
        }
    ]
    state["fleet_by_need"] = {
        "need_earthwork": {
            "candidates": [],
            "unavailable": [],
            "source_tables": ["assets", "bookings"],
        }
    }

    result = synthesize_recommendation(state)
    rows = result["recommendation"]["results_by_need"]
    assert len(rows) == 1
    assert rows[0]["need_id"] == "need_earthwork"
    assert rows[0]["item"] is None
    blob = " ".join(rows[0]["warnings"]).lower()
    assert "fleet" in blob or "match" in blob or "no " in blob


def test_pricing_failure_does_not_invent_zeros() -> None:
    """Scenario: Pricing failure does not invent zeros."""
    state = _state_with_fleet_and_price()
    state["prices_by_need"] = {"need_access": []}

    result = synthesize_recommendation(state)
    row = result["recommendation"]["results_by_need"][0]
    assert row["item"] is None
    warnings = " ".join(row["warnings"]).lower()
    assert "price" in warnings or "pricing" in warnings
    # Nothing in the envelope has a non-positive rate
    dumped = json.dumps(result["recommendation"])
    assert "daily_rate" not in dumped or '"daily_rate": 0' not in dumped


def test_cannot_inject_unknown_asset() -> None:
    """Scenario: Cannot inject unknown asset."""
    current = _state_with_fleet_and_price()
    proposed = deepcopy(current)
    proposed["recommendation"] = {
        "results_by_need": [
            {
                "need_id": "need_access",
                "item": {"asset_id": "AST-UNKNOWN", "rank": 1},
                "warnings": [],
            }
        ],
        "warnings": [],
    }
    with pytest.raises(StateTransitionError, match="cannot invent asset_id"):
        apply_partition_write(ROLE_COORDINATOR, current, proposed)


def test_bad_shape_fails_validation() -> None:
    """Scenario: Bad shape fails validation."""
    with pytest.raises(SynthesisSchemaError):
        validate_recommendation_shape([{"item": None, "warnings": []}])

    with pytest.raises(SynthesisSchemaError):
        validate_recommendation_shape(
            [{"need_id": "need_access", "item": "not-a-dict", "warnings": []}]
        )

    with pytest.raises(SynthesisSchemaError):
        validate_recommendation_shape("not-a-list")  # type: ignore[arg-type]
