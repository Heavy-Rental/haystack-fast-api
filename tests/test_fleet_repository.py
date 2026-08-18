"""S4 — Live SQL fleet backend (Phase 4 app / S7.1 leftover).

BDD scenarios:

Feature: Live SQL fleet backend (S4 app / S7.1 leftover)

  Scenario: Repository projects Asset.name as asset_id
    Given mocked Asset+Category rows (name=AST-SL-001, category=Scissors Lift)
    When  list_assets runs
    Then  DTO asset_id is AST-SL-001, category is scissor lift,
          equipment_type is Scissors Lift

  Scenario: Empty mirror returns empty list
    Given a session that returns no rows
    When  retrieve_fleet_assets / list_bookings run
    Then  results are []

  Scenario: Overlapping live-hold booking marks unavailable
    Given AST-EX-002 booked CONFIRMED 2026-09-01..30
    When  check_booking_availability for 2026-09-01..14 via live backend
    Then  AST-EX-002 is unavailable

  Scenario: Cancelled booking is ignored
    Given a CANCELLED overlap
    When  availability is checked
    Then  the asset stays available

  Scenario: Free-form SQL still rejected
    When  a fleet tool is called with sql=...
    Then  FreeFormSqlRejected is raised

  Scenario: Default CI stays fake
    Given conftest FLEET_BACKEND=fake
    When  build_recommend_tool_catalog() runs with no args
    Then  backend is FakeFleetBackend (seed)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.agents.fleet_tools import (
    FakeFleetBackend,
    FreeFormSqlRejected,
    LiveSqlFleetBackend,
    check_booking_availability,
    retrieve_fleet_assets,
)
from app.agents.tool_factory import build_recommend_tool_catalog
from app.repositories.fleet_repository import FleetRepository
from app.services.pricing.read_resilience import PricingSchemaResolution

PRIMARY = PricingSchemaResolution(schema="primary_snapshot", degraded=False)


def _session_returning(rows: list) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute.return_value = result
    return session


def test_repository_projects_asset_name_as_asset_id() -> None:
    """Scenario: Repository projects Asset.name as asset_id."""
    session = _session_returning(
        [
            (
                12,
                "AST-SL-001",
                "Scissors Lift",
                "GOOD",
                300,
                10.0,
                120.0,
                280.0,
            )
        ]
    )
    repo = FleetRepository()
    assets = repo.list_assets(session, resolution=PRIMARY)
    assert len(assets) == 1
    row = assets[0]
    assert row["id"] == 12
    assert row["name"] == "AST-SL-001"
    assert row["asset_id"] == "AST-SL-001"
    assert row["category"] == "scissor lift"
    assert row["equipment_type"] == "Scissors Lift"
    assert row["condition"] == "GOOD"
    assert row["capacity"] == 300.0
    assert row["platform_height"] == 10.0
    assert row["min_daily_rate"] == 120.0
    assert row["max_daily_rate"] == 280.0
    assert row["category_id"] is None


def test_repository_projects_category_id() -> None:
    session = _session_returning(
        [
            (
                12,
                "AST-SL-001",
                "Scissors Lift",
                "GOOD",
                300,
                10.0,
                120.0,
                280.0,
                2,
                "19ft scissor",
                2022,
                "Tuas",
            )
        ]
    )
    row = FleetRepository().list_assets(session, resolution=PRIMARY)[0]
    assert row["category_id"] == 2
    assert row["platform_height"] == 10.0
    assert row["description"] == "19ft scissor"


def test_repository_skips_unknown_category_and_blank_name() -> None:
    session = _session_returning(
        [
            (1, "", "Scissors Lift", "GOOD", 300, 10.0, 120.0, 280.0),
            (2, "AST-XX-001", "Unknown Rig", "GOOD", 1, None, 10.0, 20.0),
        ]
    )
    assert FleetRepository().list_assets(session, resolution=PRIMARY) == []


def test_empty_mirror_returns_empty_lists() -> None:
    """Scenario: Empty mirror returns empty list."""
    session = _session_returning([])
    backend = LiveSqlFleetBackend(session, resolution=PRIMARY)
    assert retrieve_fleet_assets(backend=backend) == []
    assert backend.list_bookings() == []


def test_live_hold_overlap_marks_unavailable() -> None:
    """Scenario: Overlapping live-hold booking marks unavailable."""
    asset_session = _session_returning(
        [
            (
                9,
                "AST-EX-002",
                "Excavator",
                "FAIR",
                4000,
                None,
                200.0,
                500.0,
            )
        ]
    )
    booking_session = _session_returning(
        [
            (
                "AST-EX-002",
                1,
                date(2026, 9, 1),
                date(2026, 9, 30),
                "CONFIRMED",
            )
        ]
    )
    repo = FleetRepository()
    assets = repo.list_assets(asset_session, resolution=PRIMARY)
    bookings = repo.list_bookings(booking_session, resolution=PRIMARY)
    assert bookings[0]["asset_id"] == "AST-EX-002"
    split = check_booking_availability(
        assets,
        start_date="2026-09-01",
        end_date="2026-09-14",
        bookings=bookings,
    )
    assert {a["asset_id"] for a in split["unavailable"]} == {"AST-EX-002"}
    assert split["available"] == []


def test_cancelled_booking_is_ignored() -> None:
    """Scenario: Cancelled booking is ignored."""
    session = _session_returning(
        [
            (
                "AST-EX-002",
                1,
                date(2026, 9, 1),
                date(2026, 9, 30),
                "CANCELLED",
            )
        ]
    )
    bookings = FleetRepository().list_bookings(session, resolution=PRIMARY)
    assert bookings == []


def test_freeform_sql_rejected_on_live_backend() -> None:
    """Scenario: Free-form SQL still rejected."""
    backend = LiveSqlFleetBackend(MagicMock(), resolution=PRIMARY)
    with pytest.raises(FreeFormSqlRejected):
        retrieve_fleet_assets(backend=backend, sql="SELECT 1")


def test_default_catalog_stays_fake() -> None:
    """Scenario: Default CI stays fake."""
    catalog = build_recommend_tool_catalog()
    assert catalog.backend_kind == "fake"
    assert isinstance(catalog.backend, FakeFleetBackend)


def _session_first(row) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.first.return_value = row
    session.execute.return_value = result
    return session


def test_get_asset_by_numeric_id() -> None:
    """Quote hydration: digits look up assets.id."""
    session = _session_first(
        (12, "Genie GS-1930", "Scissors Lift", "GOOD", 300, 10.0, 120.0, 280.0)
    )
    row = FleetRepository().get_asset(session, "12", resolution=PRIMARY)
    assert row is not None
    assert row["id"] == 12
    assert row["name"] == "Genie GS-1930"
    assert row["asset_id"] == "Genie GS-1930"
    assert row["equipment_type"] == "Scissors Lift"


def test_get_asset_by_name() -> None:
    """Quote hydration: non-digits look up assets.name."""
    session = _session_first((3, "AST-FL-002", "Fork Lift", "EXCELLENT", 3500, None, 100.0, 240.0))
    row = FleetRepository().get_asset(session, "AST-FL-002", resolution=PRIMARY)
    assert row is not None
    assert row["id"] == 3
    assert row["name"] == "AST-FL-002"


def test_get_asset_missing_returns_none() -> None:
    session = _session_first(None)
    assert FleetRepository().get_asset(session, "missing", resolution=PRIMARY) is None


def test_get_asset_blank_key_skips_query() -> None:
    session = MagicMock()
    assert FleetRepository().get_asset(session, "  ", resolution=PRIMARY) is None
    session.execute.assert_not_called()


def test_get_asset_projects_description_and_purchase_year() -> None:
    session = _session_first(
        (
            27,
            "Hyster H4.2FT Forklift",
            "Fork Lift",
            "GOOD",
            4200,
            None,
            100.0,
            240.0,
            "4.2t counterbalance",
            2021,
            "Tuas",
        )
    )
    row = FleetRepository().get_asset(session, "27", resolution=PRIMARY)
    assert row is not None
    assert row["description"] == "4.2t counterbalance"
    assert row["purchase_year"] == 2021
    assert row["location"] == "Tuas"
    assert row["capacity"] == 4200.0


def test_is_asset_available_false_on_live_hold_overlap() -> None:
    session = _session_returning([(date(2026, 8, 1), date(2026, 8, 31))])
    assert (
        FleetRepository().is_asset_available(
            session,
            27,
            start_date=date(2026, 8, 13),
            end_date=date(2026, 8, 20),
            resolution=PRIMARY,
        )
        is False
    )


def test_is_asset_available_true_when_no_holds() -> None:
    session = _session_returning([])
    assert (
        FleetRepository().is_asset_available(
            session, 27, start_date=date(2026, 8, 13), resolution=PRIMARY
        )
        is True
    )
