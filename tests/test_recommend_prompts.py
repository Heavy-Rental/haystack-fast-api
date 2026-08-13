"""S7.7 — Recommend prompts A–L isolated from Stage-1 (Phase 7).

BDD scenarios (implementation-plan Stage S7.7):

Feature: Recommend prompts A–L isolated from Stage-1

  Scenario: Q&A prompts still forbid invent fleet
    Given Stage-1 SYNTHESIS_AGENT_SYSTEM / RESEARCH_AGENT_SYSTEM
    Then  they still forbid inventing fleet inventory, rates, or bookings
    And   they do not mention retrieve_fleet_assets or predict_asset_price

  Scenario: Recommend synthesis prompt has no tools
    Given RECOMMEND_SYNTHESIS_SYSTEM
    Then  it declares tools: none
    And   it forbids inventing asset_id / daily_rate
    And   it states L-1 sequential barrier after need pipelines

  Scenario: Stub path is deterministic
    Given PROJECT_AGENT_MODE=stub and fixture fleet + prices
    When  synthesize_recommendation runs twice
    Then  results_by_need asset_id / daily_rate match the golden fixture
    And   rationale is stable
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.prompts import (
    GRAPH_AGENT_SYSTEM,
    RESEARCH_AGENT_SYSTEM,
    SYNTHESIS_AGENT_SYSTEM,
)
from app.agents.recommend_prompts import (
    DELEGATOR_POLICY_SYSTEM,
    FLEET_WORKER_SYSTEM,
    PRICING_WORKER_SYSTEM,
    PROJECT_WORKER_SYSTEM,
    RECOMMEND_SYNTHESIS_SYSTEM,
    apply_rationale_only,
    stub_recommend_rationale,
)
from app.agents.recommend_synthesis import synthesize_recommendation

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


def _state_with_fleet_and_price() -> dict:
    state = json.loads((FIXTURES / "state_minimal.json").read_text(encoding="utf-8"))
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


def test_qa_prompts_still_forbid_invent_fleet() -> None:
    """Scenario: Q&A prompts still forbid invent fleet."""
    qa_blob = "\n".join(
        [RESEARCH_AGENT_SYSTEM, GRAPH_AGENT_SYSTEM, SYNTHESIS_AGENT_SYSTEM]
    ).lower()
    assert "do not invent" in qa_blob or "not invent" in qa_blob
    assert "fleet" in qa_blob or "inventory" in qa_blob or "stock" in qa_blob
    assert "retrieve_fleet_assets" not in qa_blob
    assert "predict_asset_price" not in qa_blob
    assert "filter_fleet_candidates" not in qa_blob


def test_recommend_synthesis_prompt_has_no_tools() -> None:
    """Scenario: Recommend synthesis prompt has no tools."""
    text = RECOMMEND_SYNTHESIS_SYSTEM.lower()
    assert "tools: none" in text or "tools:none" in text.replace(" ", "")
    assert "asset_id" in text
    assert "daily_rate" in text
    assert "invent" in text
    assert "l-1" in text
    assert "sequential" in text
    assert "barrier" in text
    # Synthesis is tool-free — must not instruct calling fleet/price tools
    assert "retrieve_fleet_assets" not in text
    assert "predict_asset_price" not in text


def test_recommend_role_prompts_encode_a_l_partitions() -> None:
    """Each recommend role prompt names its write partition and seq/par rules."""
    assert "work_plan" in DELEGATOR_POLICY_SYSTEM.lower()
    assert "fleet_by_need" in FLEET_WORKER_SYSTEM.lower()
    assert "prices_by_need" in PRICING_WORKER_SYSTEM.lower()
    assert "project" in PROJECT_WORKER_SYSTEM.lower()
    assert "l-1" in FLEET_WORKER_SYSTEM.lower()
    assert "l-2" in DELEGATOR_POLICY_SYSTEM.lower() or "parallel" in DELEGATOR_POLICY_SYSTEM.lower()
    assert "decompose_project_needs" in PROJECT_WORKER_SYSTEM
    assert "project_vector_search" in PROJECT_WORKER_SYSTEM
    assert "project_kg_query" in PROJECT_WORKER_SYSTEM
    assert "predict_asset_price" in PRICING_WORKER_SYSTEM
    assert "retrieve_fleet_assets" in FLEET_WORKER_SYSTEM


def test_stub_synthesis_path_is_deterministic() -> None:
    """Scenario: Stub path is deterministic."""
    state = _state_with_fleet_and_price()
    first = synthesize_recommendation(state)
    second = synthesize_recommendation(state)
    golden = json.loads(
        (FIXTURES / "golden_results_by_need.json").read_text(encoding="utf-8")
    )["results_by_need"]

    for actual in (first["recommendation"]["results_by_need"], second["recommendation"]["results_by_need"]):
        assert actual[0]["item"]["asset_id"] == golden[0]["item"]["asset_id"]
        assert actual[0]["item"]["pricing"]["daily_rate"] == golden[0]["item"]["pricing"][
            "daily_rate"
        ]
        assert actual[0]["item"]["rationale"] == golden[0]["item"]["rationale"]

    assert first["recommendation"] == second["recommendation"]


def test_stub_rationale_helper_matches_golden_prefix() -> None:
    rationale = stub_recommend_rationale(
        description="Need scissor lift for 8m access",
        asset_id="AST-SL-001",
    )
    assert rationale == "Stub merge: Need scissor lift for 8m access → AST-SL-001."


def test_llm_shaped_payload_cannot_inject_unknown_asset() -> None:
    """LLM rationale-only apply ignores invented asset_id / rates."""
    item = {
        "asset_id": "AST-SL-001",
        "rank": 1,
        "rationale": "Stub merge: Need scissor lift for 8m access → AST-SL-001.",
        "pricing": {"daily_rate": 185.0, "total_price": 2590.0, "currency": "SGD"},
    }
    tainted = {
        "asset_id": "AST-UNKNOWN",
        "daily_rate": 1.0,
        "rationale": "Picked AST-UNKNOWN at $1 because it sounded helpful.",
    }
    cleaned = apply_rationale_only(item, tainted)
    assert cleaned["asset_id"] == "AST-SL-001"
    assert cleaned["pricing"]["daily_rate"] == 185.0
    assert cleaned["rationale"] == tainted["rationale"]
    assert "AST-UNKNOWN" not in cleaned["asset_id"]
