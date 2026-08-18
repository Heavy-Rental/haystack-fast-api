"""pricing_client.py's thin wrapper around app.services.pricing.model.predict_price()
(Phase 2b, docs/dynamic-pricing-execution-plan.md "Day 5 (cont.) -- Phase 2b (lean)").

Only the response-shaping wrapper is this module's job -- period_utilization/
lead_time_days live-aggregate behavior, guardrail clamping, and cold-start
propagation are already covered by Phase 2a's own tests
(test_pricing_model.py) against app.services.pricing.model.predict_price
directly; not re-tested here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from unittest.mock import MagicMock

import pytest

import app.services.pricing_client as pc


@dataclass(frozen=True)
class _FakePrediction:
    clamped_price: float
    was_clamped: bool = False
    degraded: bool = False
    model_version: str = "prod-2026-08-11"


@pytest.fixture
def _fake_predict_price(monkeypatch: pytest.MonkeyPatch):
    captured: dict = {}
    result_holder: dict = {"value": _FakePrediction(clamped_price=123.45)}

    def _fake(**kwargs):
        captured.update(kwargs)
        return result_holder["value"]

    monkeypatch.setattr(pc, "predict_price", _fake)
    return captured, result_holder


def test_delegates_to_production_predict_price_with_all_args(_fake_predict_price) -> None:
    captured, _ = _fake_predict_price

    result = pc.predict_price_for_asset(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        min_daily_rate=250.0,
        max_daily_rate=600.0,
    )

    assert captured["category"] == "excavator"
    assert captured["condition"] == "GOOD"
    assert captured["duration_days"] == 7.0
    assert captured["capacity"] == 5000
    assert captured["distance_km"] == 15
    assert captured["platform_height"] is None
    assert captured["min_daily_rate"] == 250.0
    assert captured["max_daily_rate"] == 600.0
    assert captured["db"] is None
    assert result.daily_rate == 123.45
    assert result.total_price == round(123.45 * 7, 2)
    assert result.model_version == "prod-2026-08-11"
    assert "degraded" not in result.explanation


def test_threads_db_and_dates_through(monkeypatch: pytest.MonkeyPatch, _fake_predict_price) -> None:
    captured, _ = _fake_predict_price
    fake_db = MagicMock()

    pc.predict_price_for_asset(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        min_daily_rate=250.0,
        max_daily_rate=600.0,
        db=fake_db,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert captured["db"] is fake_db
    assert captured["start_date"] == date(2026, 9, 1)
    assert captured["end_date"] == date(2026, 9, 7)


def test_degraded_prediction_marks_result_without_new_field(_fake_predict_price) -> None:
    _captured, result_holder = _fake_predict_price
    result_holder["value"] = _FakePrediction(clamped_price=99.0, degraded=True)

    result = pc.predict_price_for_asset(
        category="forklift",
        condition="GOOD",
        duration_days=7,
        capacity=2000,
        distance_km=15,
        platform_height=None,
        min_daily_rate=80.0,
        max_daily_rate=200.0,
        db=MagicMock(),
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert result.model_version == "prod-2026-08-11-degraded"
    assert "degraded" in result.explanation


def test_was_clamped_passed_through(_fake_predict_price) -> None:
    _, result_holder = _fake_predict_price
    result_holder["value"] = _FakePrediction(clamped_price=200.0, was_clamped=True)

    result = pc.predict_price_for_asset(
        category="forklift",
        condition="GOOD",
        duration_days=1,
        capacity=2000,
        distance_km=15,
        platform_height=None,
        min_daily_rate=80.0,
        max_daily_rate=200.0,
    )

    assert result.was_clamped is True
