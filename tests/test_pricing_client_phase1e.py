"""Phase 1e — pricing_client.py threading db/start_date/end_date (SPEC-dynamic-pricing.md §5.2/§5.3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from unittest.mock import MagicMock

import pytest

import app.services.pricing_client as pc
from app.repositories.pricing_read_resilience import (
    PricingSchemaResolution,
    PricingSchemaUnavailable,
)


@dataclass(frozen=True)
class _FakePrediction:
    clamped_price: float
    was_clamped: bool = False


@pytest.fixture(autouse=True)
def _fake_model_loaded(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}

    def _fake_predict(**kwargs):
        captured.update(kwargs)
        return _FakePrediction(clamped_price=123.45)

    monkeypatch.setattr(pc, "_predict_fn", _fake_predict)
    monkeypatch.setattr(pc, "_load_error", None)
    return captured


def test_no_db_falls_back_to_static_defaults(_fake_model_loaded: dict) -> None:
    """Backward-compatible: no db/start_date/end_date -> no live kwargs passed."""
    result = pc.predict_price_for_asset(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
    )

    assert "period_utilization" not in _fake_model_loaded
    assert "lead_time_days" not in _fake_model_loaded
    assert result.model_version == "experimental-ml_experiments"
    assert "degraded" not in result.explanation


def test_db_and_dates_thread_live_period_utilization(
    monkeypatch: pytest.MonkeyPatch, _fake_model_loaded: dict
) -> None:
    monkeypatch.setattr(
        pc, "resolve_pricing_schema",
        lambda session: PricingSchemaResolution(schema="primary_snapshot", degraded=False),
    )
    monkeypatch.setattr(pc, "compute_period_utilization", lambda *a, **k: 0.42)
    monkeypatch.setattr(pc, "compute_lead_time_days", lambda *a, **k: 9)

    result = pc.predict_price_for_asset(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        db=MagicMock(),
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert _fake_model_loaded["period_utilization"] == 0.42
    assert _fake_model_loaded["lead_time_days"] == 9
    assert result.model_version == "experimental-ml_experiments"
    assert "degraded" not in result.explanation


def test_degraded_schema_marks_result_without_new_field(
    monkeypatch: pytest.MonkeyPatch, _fake_model_loaded: dict
) -> None:
    monkeypatch.setattr(
        pc, "resolve_pricing_schema",
        lambda session: PricingSchemaResolution(schema="public", degraded=True),
    )
    monkeypatch.setattr(pc, "compute_period_utilization", lambda *a, **k: 0.3)
    monkeypatch.setattr(pc, "compute_lead_time_days", lambda *a, **k: 3)

    result = pc.predict_price_for_asset(
        category="forklift",
        condition="GOOD",
        duration_days=7,
        capacity=2000,
        distance_km=15,
        platform_height=None,
        db=MagicMock(),
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert result.model_version == "experimental-ml_experiments-degraded"
    assert "degraded" in result.explanation


def test_cold_start_failure_propagates_not_swallowed(
    monkeypatch: pytest.MonkeyPatch, _fake_model_loaded: dict
) -> None:
    def _raise(session):
        raise PricingSchemaUnavailable("neither schema available")

    monkeypatch.setattr(pc, "resolve_pricing_schema", _raise)

    with pytest.raises(PricingSchemaUnavailable):
        pc.predict_price_for_asset(
            category="forklift",
            condition="GOOD",
            duration_days=7,
            capacity=2000,
            distance_km=15,
            platform_height=None,
            db=MagicMock(),
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
        )


def test_null_capacity_gets_category_midpoint_before_prediction(
    _fake_model_loaded: dict,
) -> None:
    pc.predict_price_for_asset(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=None,
        distance_km=15,
        platform_height=None,
    )

    assert _fake_model_loaded["capacity"] == 15500  # CATEGORY_CAPACITY_KG midpoint
