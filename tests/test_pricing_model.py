"""app/services/pricing/model.py (openspec/specs/dynamic-pricing/spec.md).

Covers spec.md's Verification list: guardrail clamping (below-min, above-max,
in-range), prediction output shape/type, one prediction per category
(mirroring ml-experiments/shap_review.py's per-category sweep pattern), plus
the category-validation gap found during Phase 2a (an unrecognized category
would otherwise silently one-hot-encode to an all-zero row and predict from
garbage input with no error at all -- confirmed empirically before this
check was added).

The smoke/shape tests below call the real loaded model (module-level
artifacts, same ones ml-experiments/shap_review.py already validated) with
wide-open guardrail bounds so clamping never fires -- they're about output
shape, not specific values. The clamping tests replace ``_model`` with a
fixture returning a fixed raw price, so the boundary math is deterministic
and doesn't depend on the trained model's actual output for any given input.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

import app.services.pricing.model as pricing_model
from app.services.pricing import pricing_tables as pt
from app.services.pricing.feature_schema import CATEGORIES
from app.services.pricing.model import PricePrediction, predict_price

_WIDE_OPEN = {"min_daily_rate": 1.0, "max_daily_rate": 100_000.0}


def test_predict_price_one_per_category_smoke() -> None:
    for category in CATEGORIES:
        is_aerial = category in pt.AERIAL_CATEGORIES
        result = predict_price(
            category=category,
            condition="GOOD",
            duration_days=7,
            capacity=300 if is_aerial else 2000,
            distance_km=15,
            platform_height=10 if is_aerial else None,
            **_WIDE_OPEN,
        )
        assert isinstance(result, PricePrediction)
        assert result.raw_price > 0
        assert result.was_clamped is False  # bounds wide open


def test_predict_price_output_shape_and_types() -> None:
    result = predict_price(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        **_WIDE_OPEN,
    )
    assert isinstance(result.raw_price, float)
    assert isinstance(result.clamped_price, float)
    assert isinstance(result.was_clamped, bool)
    assert isinstance(result.min_daily_rate, float)
    assert isinstance(result.max_daily_rate, float)
    assert isinstance(result.duration_days, float)
    assert isinstance(result.period_utilization, float)
    assert isinstance(result.lead_time_days, float)
    assert isinstance(result.degraded, bool)
    assert result.model_version.startswith("prod-")


def test_platform_height_nan_for_non_aerial_prediction_succeeds() -> None:
    result = predict_price(
        category="forklift",
        condition="GOOD",
        duration_days=7,
        capacity=2000,
        distance_km=15,
        platform_height=None,
        **_WIDE_OPEN,
    )
    assert result.raw_price > 0  # didn't crash on NaN platform_height


def test_unrecognized_category_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unrecognized category"):
        predict_price(
            category="bulldozer",
            condition="GOOD",
            duration_days=7,
            capacity=5000,
            distance_km=15,
            platform_height=None,
            **_WIDE_OPEN,
        )


def test_db_style_category_name_fails_loud_with_a_helpful_hint() -> None:
    # A raw AssetCategory.name value, not converted first -- must fail loud,
    # not silently one-hot-encode to an all-zero row (the exact gap this
    # check closes; confirmed empirically during Phase 2a).
    with pytest.raises(ValueError, match="category_mapping.to_feature_name"):
        predict_price(
            category="Excavator",
            condition="GOOD",
            duration_days=7,
            capacity=5000,
            distance_km=15,
            platform_height=None,
            **_WIDE_OPEN,
        )


def test_null_condition_falls_back_to_good(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    real_build_features = pricing_model.fs.build_features

    def _capture(row):
        captured["condition"] = row.iloc[0]["condition"]
        return real_build_features(row)

    monkeypatch.setattr(pricing_model.fs, "build_features", _capture)

    predict_price(
        category="excavator",
        condition=None,
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        **_WIDE_OPEN,
    )

    assert captured["condition"] == "GOOD"


def test_guardrail_clamps_below_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = [50.0]
    monkeypatch.setattr(pricing_model, "_model", fake_model)

    result = predict_price(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        min_daily_rate=100.0,
        max_daily_rate=200.0,
    )

    assert result.raw_price == 50.0
    assert result.clamped_price == 100.0
    assert result.was_clamped is True


def test_guardrail_clamps_above_maximum(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = [500.0]
    monkeypatch.setattr(pricing_model, "_model", fake_model)

    result = predict_price(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        min_daily_rate=100.0,
        max_daily_rate=200.0,
    )

    assert result.raw_price == 500.0
    assert result.clamped_price == 200.0
    assert result.was_clamped is True


def test_guardrail_does_not_clamp_in_range(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = [150.0]
    monkeypatch.setattr(pricing_model, "_model", fake_model)

    result = predict_price(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        min_daily_rate=100.0,
        max_daily_rate=200.0,
    )

    assert result.raw_price == 150.0
    assert result.clamped_price == 150.0
    assert result.was_clamped is False


def test_no_db_falls_back_to_static_period_utilization(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = [150.0]
    monkeypatch.setattr(pricing_model, "_model", fake_model)

    result = predict_price(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        **_WIDE_OPEN,
    )

    assert result.period_utilization == pt.CATEGORY_UTILIZATION["excavator"]
    assert result.lead_time_days == 0.0
    assert result.degraded is False


def test_db_and_dates_thread_live_period_utilization(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = [150.0]
    monkeypatch.setattr(pricing_model, "_model", fake_model)
    monkeypatch.setattr(
        pricing_model,
        "resolve_pricing_schema",
        lambda session: MagicMock(degraded=False, execution_options={}),
    )
    monkeypatch.setattr(pricing_model, "compute_period_utilization", lambda *a, **k: 0.42)
    monkeypatch.setattr(pricing_model, "compute_lead_time_days", lambda *a, **k: 9)

    result = predict_price(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
        min_daily_rate=100.0,
        max_daily_rate=200.0,
        db=MagicMock(),
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert result.period_utilization == 0.42
    assert result.lead_time_days == 9.0


def test_degraded_schema_marked_on_result(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = [150.0]
    monkeypatch.setattr(pricing_model, "_model", fake_model)
    monkeypatch.setattr(
        pricing_model,
        "resolve_pricing_schema",
        lambda session: MagicMock(degraded=True, execution_options={}),
    )
    monkeypatch.setattr(pricing_model, "compute_period_utilization", lambda *a, **k: 0.3)
    monkeypatch.setattr(pricing_model, "compute_lead_time_days", lambda *a, **k: 3)

    result = predict_price(
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

    assert result.degraded is True


def test_reload_model_reloads_from_disk() -> None:
    original = pricing_model._model
    pricing_model.reload_model()

    assert pricing_model._model is not original  # a fresh object, not a no-op
    assert pricing_model._model_version.startswith("prod-")
