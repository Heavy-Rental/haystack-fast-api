"""Single import site for predict_price() (FR-020-022).

Production swap done (Phase 2b, docs/dynamic-pricing-execution-plan.md "Day 5
(cont.) -- Phase 2b (lean)"): this module now calls
``app.services.pricing.model.predict_price(...)`` (Phase 2a's productionized,
guardrail-clamped model) directly -- the ``ml-experiments/predict_price.py``
prototype it used to load lazily via ``sys.path`` is no longer referenced
here. ``model.py`` already loads its artifacts eagerly at import time and
does its own db/start_date/end_date-gated live-aggregate + guardrail-clamp
work, so this module is now a thin response-shaping wrapper: currency,
deposit_rate, total_price, and human-readable explanation text around
``PricePrediction``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.services.pricing.model import predict_price


@dataclass(frozen=True)
class PriceResult:
    """Pricing for a specific rental duration window.

    ``daily_rate`` is scoped to the ``duration_days`` used in the prediction
    (duration is a model input). A different window needs a fresh
    ``predict_price()`` call — do not re-scale daily_rate client-side.

    ``total_price`` is estimated total for that window: daily_rate × duration_days.
    """

    daily_rate: float
    total_price: float
    currency: str
    deposit_rate: float
    model_version: str
    explanation: str
    was_clamped: bool = False


def predict_price_for_asset(
    *,
    category: str,
    condition: str,
    duration_days: float,
    capacity: float | None,
    distance_km: float,
    platform_height: float | None,
    min_daily_rate: float,
    max_daily_rate: float,
    db: Session | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> PriceResult:
    """Predict daily rate for this duration, clamped to the asset's real guardrails.

    ``min_daily_rate``/``max_daily_rate`` are required -- the real per-asset
    ``Asset.minDailyRate``/``maxDailyRate`` -- no static fallback anywhere in
    this call chain (Phase 2a decision, carried through here).

    ``db``/``start_date``/``end_date`` are optional (Phase 1e,
    openspec/specs/dynamic-pricing/spec.md §5.2/§5.3.1): when all three are
    given, period_utilization/lead_time_days are computed as live aggregates
    against the real schema. When any is missing, this falls back to static
    defaults inside ``predict_price(...)``, unchanged pre-Phase-1e behavior.
    A cold-start schema failure (§5.3.1 tier 3) is NOT part of that graceful
    fallback: it propagates, per spec's explicit fail-loud requirement, once
    a real ``db`` session was actually provided.
    """
    days = max(1.0, float(duration_days or 1.0))
    prediction = predict_price(
        category=category,
        condition=condition,
        duration_days=days,
        capacity=capacity,
        distance_km=distance_km,
        platform_height=platform_height,
        min_daily_rate=min_daily_rate,
        max_daily_rate=max_daily_rate,
        db=db,
        start_date=start_date,
        end_date=end_date,
    )

    daily = prediction.clamped_price
    model_version = prediction.model_version
    explanation = (
        "From app.services.pricing.model.predict_price() (production model). "
        f"daily_rate is for a {days:g}-day rental window; "
        "request a new prediction for a different duration."
    )
    if prediction.degraded:
        model_version += "-degraded"
        explanation += (
            " (degraded: primary_snapshot unavailable, served from public "
            "(at most one sync cycle stale))"
        )

    return PriceResult(
        daily_rate=daily,
        total_price=round(daily * days, 2),
        currency="SGD",
        deposit_rate=0.30,
        model_version=model_version,
        explanation=explanation,
        was_clamped=prediction.was_clamped,
    )
