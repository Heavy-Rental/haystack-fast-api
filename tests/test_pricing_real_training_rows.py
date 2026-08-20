from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from app.models.booking import Booking
from app.models.booking_item import BookingItem
from app.services.pricing import repository
from app.services.pricing.read_resilience import PricingSchemaResolution

PRIMARY = PricingSchemaResolution(schema="primary_snapshot", degraded=False)
DEGRADED = PricingSchemaResolution(schema="public", degraded=True)


def _session_with_rows(rows: list[dict[str, object]]) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session.execute.return_value = result
    return session


def test_phase3b_models_expose_real_price_and_booking_metadata_columns() -> None:
    assert BookingItem.__table__.c.daily_rate.nullable is True
    assert BookingItem.__table__.c.subtotal.nullable is True
    assert Booking.__table__.c.created_at.nullable is True
    assert Booking.__table__.c.total_amount.nullable is True


def test_fetch_real_training_rows_maps_features_and_historical_values(
    monkeypatch,
) -> None:
    rows = [
        {
            "booking_item_id": 11,
            "db_category": "Fork Lift",
            "condition": "GOOD",
            "capacity": 2500,
            "platform_height": None,
            "start_date": date(2026, 9, 10),
            "end_date": date(2026, 9, 17),
            "created_at": datetime(2026, 9, 1, 12, 30, tzinfo=UTC),
            "daily_rate": Decimal("125.50"),
        },
        {
            "booking_item_id": 12,
            "db_category": "Scissors Lift",
            "condition": "EXCELLENT",
            "capacity": 350,
            "platform_height": Decimal("10.50"),
            "start_date": date(2026, 10, 1),
            "end_date": date(2026, 10, 15),
            "created_at": None,
            "daily_rate": Decimal("210.00"),
        },
    ]
    session = _session_with_rows(rows)
    utilization_calls: list[dict[str, object]] = []

    def fake_utilization(*args, **kwargs) -> float:
        utilization_calls.append(kwargs)
        return 0.25 if kwargs["category"] == "forklift" else 0.75

    monkeypatch.setattr(repository, "compute_period_utilization", fake_utilization)

    actual = repository.fetch_real_training_rows(session, DEGRADED)

    assert list(actual.columns) == repository.REAL_TRAINING_COLUMNS
    assert actual["category"].tolist() == ["forklift", "scissor lift"]
    assert actual["duration_days"].tolist() == [8, 15]
    assert actual["lead_time_days"].tolist() == [9, 0]
    assert actual["price_per_day"].tolist() == [125.5, 210.0]
    assert actual["period_utilization"].tolist() == [0.25, 0.75]
    assert actual.loc[0, "capacity"] == 2500.0
    assert pd.isna(actual.loc[0, "platform_height"])
    assert actual.loc[1, "platform_height"] == 10.5
    assert np.array_equal(
        actual["distance_km"].to_numpy(),
        repository.sample_distance_km(np.random.default_rng(42), 2),
    )
    assert [call["start_date"] for call in utilization_calls] == [
        date(2026, 9, 10),
        date(2026, 10, 1),
    ]
    assert session.execute.call_args.kwargs["execution_options"] == DEGRADED.execution_options


def test_fetch_real_training_rows_floors_same_day_duration_at_one(monkeypatch) -> None:
    rows = [
        {
            "booking_item_id": 21,
            "db_category": "Fork Lift",
            "condition": "GOOD",
            "capacity": 2500,
            "platform_height": None,
            "start_date": date(2026, 9, 10),
            "end_date": date(2026, 9, 10),
            "created_at": datetime(2026, 9, 1, 12, 30, tzinfo=UTC),
            "daily_rate": Decimal("125.50"),
        },
    ]
    session = _session_with_rows(rows)
    monkeypatch.setattr(
        repository, "compute_period_utilization", lambda *args, **kwargs: 0.25
    )

    actual = repository.fetch_real_training_rows(session, DEGRADED)

    assert actual["duration_days"].tolist() == [1]


def test_fetch_real_training_rows_empty_result_has_stable_schema(monkeypatch) -> None:
    session = _session_with_rows([])
    monkeypatch.setattr(
        repository,
        "compute_period_utilization",
        MagicMock(side_effect=AssertionError("must not be called")),
    )

    actual = repository.fetch_real_training_rows(session, PRIMARY)

    assert actual.empty
    assert list(actual.columns) == repository.REAL_TRAINING_COLUMNS


def test_real_training_query_filters_realized_positive_prices_and_uses_real_tables() -> None:
    session = _session_with_rows([])

    repository.fetch_real_training_rows(
        session,
        PRIMARY,
        statuses={"COMPLETED", "CONFIRMED"},
    )

    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "FROM primary_snapshot.booking_items" in compiled
    assert "JOIN primary_snapshot.bookings" in compiled
    assert "JOIN primary_snapshot.assets" in compiled
    assert "JOIN primary_snapshot.asset_categories" in compiled
    assert "bookings.status IN ('COMPLETED', 'CONFIRMED')" in compiled
    assert "booking_items.daily_rate IS NOT NULL" in compiled
    assert "booking_items.daily_rate > 0" in compiled
    assert "bookings.start_date IS NOT NULL" in compiled
    assert "bookings.end_date IS NOT NULL" in compiled
