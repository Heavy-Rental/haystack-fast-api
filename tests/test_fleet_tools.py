"""S7.1 — In-process fleet / needs tool catalog (Phase 7).

BDD scenarios (implementation-plan Stage S7.1):

Feature: Allowlisted in-process fleet tools (no free-form SQL)

  Scenario: Fake fleet list filter by category
    Given a fake fleet with scissor lifts and excavators
    When  retrieve_fleet_assets / filter_fleet_candidates by category
    Then  only matching category assets are returned

  Scenario: Availability drops overlapping bookings
    Given AST-EX-002 booked 2026-09-01..30
    When  check_booking_availability for 2026-09-01..14
    Then  AST-EX-002 is unavailable; others remain available

  Scenario: Empty fleet returns empty list
    Given a backend with no assets
    When  retrieve_fleet_assets runs
    Then  result is []

  Scenario: Decomposer stub returns fixed needs
    Given StubNeedDecomposer
    When  decompose_project_needs with non-empty text
    Then  a single need_1 row is returned

  Scenario: Free-form SQL is rejected
    When  any fleet tool is called with sql=...
    Then  FreeFormSqlRejected is raised
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.agents.fleet_tools import (
    TOOL_CHECK_BOOKING_AVAILABILITY,
    TOOL_DECOMPOSE_PROJECT_NEEDS,
    TOOL_FILTER_FLEET_CANDIDATES,
    TOOL_RETRIEVE_FLEET_ASSETS,
    FakeFleetBackend,
    FreeFormSqlRejected,
    check_booking_availability,
    decompose_project_needs,
    filter_fleet_candidates,
    retrieve_fleet_assets,
)
from app.services.need_decomposer import StubNeedDecomposer

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


def _seed() -> tuple[list[dict], list[dict]]:
    data = json.loads((FIXTURES / "fleet_seed.json").read_text(encoding="utf-8"))
    return data["assets"], data["bookings"]


def test_tool_names_stable_contracts() -> None:
    assert TOOL_DECOMPOSE_PROJECT_NEEDS == "decompose_project_needs"
    assert TOOL_RETRIEVE_FLEET_ASSETS == "retrieve_fleet_assets"
    assert TOOL_FILTER_FLEET_CANDIDATES == "filter_fleet_candidates"
    assert TOOL_CHECK_BOOKING_AVAILABILITY == "check_booking_availability"


def test_fake_fleet_filter_by_category() -> None:
    """Scenario: Fake fleet list filter by category."""
    assets, bookings = _seed()
    backend = FakeFleetBackend(assets=assets, bookings=bookings)

    all_assets = retrieve_fleet_assets(backend=backend)
    assert len(all_assets) == 4

    scissors = retrieve_fleet_assets(backend=backend, category="scissor lift")
    assert {a["asset_id"] for a in scissors} == {"AST-SL-001", "AST-SL-002"}

    filtered = filter_fleet_candidates(
        assets,
        unit_need={
            "description": "need elevated platform access",
            "equipment_hints": ["scissor lift"],
        },
    )
    assert all(a["category"] == "scissor lift" for a in filtered)
    assert len(filtered) >= 1

    by_cat = filter_fleet_candidates(assets, category="excavator")
    assert {a["asset_id"] for a in by_cat} == {"AST-EX-001", "AST-EX-002"}


def test_availability_drops_overlapping_bookings() -> None:
    """Scenario: availability drops overlapping bookings."""
    assets, bookings = _seed()
    result = check_booking_availability(
        assets,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 14),
        bookings=bookings,
    )
    available_ids = {a["asset_id"] for a in result["available"]}
    unavailable_ids = {a["asset_id"] for a in result["unavailable"]}

    assert "AST-EX-002" in unavailable_ids
    assert "AST-EX-002" not in available_ids
    assert "AST-SL-001" in available_ids
    assert "AST-EX-001" in available_ids


def test_empty_fleet_returns_empty() -> None:
    """Scenario: empty fleet → []."""
    backend = FakeFleetBackend(assets=[], bookings=[])
    assert retrieve_fleet_assets(backend=backend) == []
    assert filter_fleet_candidates([], category="scissor lift") == []
    empty_avail = check_booking_availability(
        [],
        start_date="2026-09-01",
        end_date="2026-09-14",
        bookings=[],
    )
    assert empty_avail == {"available": [], "unavailable": []}


def test_decomposer_stub_returns_fixed_needs() -> None:
    """Scenario: decomposer stub returns fixed needs."""
    needs = decompose_project_needs(
        "Need a scissor lift for facade work",
        decomposer=StubNeedDecomposer(),
    )
    assert len(needs) == 1
    assert needs[0]["need_id"] == "need_1"
    assert "scissor lift" in needs[0]["description"].lower()
    assert needs[0]["quantity"] == 1

    assert decompose_project_needs("   ", decomposer=StubNeedDecomposer()) == []


def test_freeform_sql_rejected() -> None:
    """Scenario: free-form SQL rejected on tool entrypoints."""
    with pytest.raises(FreeFormSqlRejected, match="free-form SQL"):
        retrieve_fleet_assets(sql="SELECT * FROM assets")

    with pytest.raises(FreeFormSqlRejected):
        filter_fleet_candidates([], cypher="MATCH (n) RETURN n")

    with pytest.raises(FreeFormSqlRejected):
        check_booking_availability([], raw_sql="DELETE FROM bookings")

    with pytest.raises(FreeFormSqlRejected):
        decompose_project_needs("x", query_sql="SELECT 1")


def test_filter_min_platform_height() -> None:
    assets, _ = _seed()
    tall = filter_fleet_candidates(
        assets,
        category="scissor lift",
        min_platform_height=11.0,
    )
    assert {a["asset_id"] for a in tall} == {"AST-SL-002"}


def test_availability_without_dates_all_pass() -> None:
    assets, bookings = _seed()
    result = check_booking_availability(assets, bookings=bookings)
    assert len(result["available"]) == len(assets)
    assert result["unavailable"] == []
