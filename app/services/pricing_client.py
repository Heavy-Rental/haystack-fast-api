"""Single import site for predict_price() (FR-020–022).

Prototype: ml-experiments/predict_price.py (experimental model).
Production swap: change only this module to app.services.pricing.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.repositories.pricing_read_resilience import resolve_pricing_schema
from app.repositories.pricing_repository import (
    compute_lead_time_days,
    compute_period_utilization,
    resolve_effective_capacity,
)

logger = logging.getLogger(__name__)

_ML_DIR = Path(__file__).resolve().parents[2] / "ml-experiments"
_predict_fn: Callable[..., Any] | None = None
_load_error: str | None = None


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


def _ensure_loaded() -> None:
    global _predict_fn, _load_error
    if _predict_fn is not None or _load_error is not None:
        return
    try:
        ml_path = str(_ML_DIR)
        if ml_path not in sys.path:
            sys.path.insert(0, ml_path)
        import predict_price as pp  # type: ignore  # noqa: PLC0415

        _predict_fn = pp.predict_price
        logger.info(
            "Loaded experimental predict_price from ml-experiments (FR-021)"
        )
    except Exception as exc:  # noqa: BLE001 — prototype load may miss model.pkl
        _load_error = str(exc)
        logger.warning(
            "ml-experiments predict_price unavailable (%s); using category fallback",
            exc,
        )


def predict_price_for_asset(
    *,
    category: str,
    condition: str,
    duration_days: float,
    capacity: float | None,
    distance_km: float,
    platform_height: float | None,
    db: Session | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> PriceResult:
    """Predict daily rate for this duration; fallback if experimental model missing.

    ``db``/``start_date``/``end_date`` are optional (Phase 1e,
    specification/SPEC-dynamic-pricing.md §5.2/§5.3.1): when all three are
    given, period_utilization/lead_time_days are computed as live aggregates
    against the real schema. When any is missing -- no caller-provided DB
    session yet, e.g. today's only caller -- this falls back to the
    ml-experiments prototype's own static defaults, unchanged from
    pre-Phase-1e behavior. A cold-start schema failure (§5.3.1 tier 3) is
    NOT part of that graceful fallback: it propagates, per spec's explicit
    fail-loud requirement, once a real ``db`` session was actually provided.
    """
    days = max(1.0, float(duration_days or 1.0))
    effective_capacity = resolve_effective_capacity(category, capacity)

    period_utilization: float | None = None
    lead_time_days = 0.0
    degraded_note: str | None = None
    if db is not None and start_date is not None and end_date is not None:
        resolution = resolve_pricing_schema(db)
        period_utilization = compute_period_utilization(
            db,
            resolution,
            category=category,
            capacity=capacity,
            platform_height=platform_height,
            start_date=start_date,
            end_date=end_date,
        )
        lead_time_days = float(compute_lead_time_days(start_date))
        if resolution.degraded:
            degraded_note = (
                "degraded: primary_snapshot unavailable, served from public "
                "(at most one sync cycle stale)"
            )

    _ensure_loaded()
    if _predict_fn is not None:
        predict_kwargs: dict[str, Any] = {
            "category": category,
            "condition": condition,
            "duration_days": days,
            "capacity": effective_capacity,
            "distance_km": distance_km,
            "platform_height": platform_height,
        }
        if period_utilization is not None:
            predict_kwargs["period_utilization"] = period_utilization
            predict_kwargs["lead_time_days"] = lead_time_days
        result = _predict_fn(**predict_kwargs)
        daily = float(result.clamped_price)
        model_version = "experimental-ml_experiments"
        explanation = (
            "From ml-experiments.predict_price() (experimental model). "
            f"daily_rate is for a {days:g}-day rental window; "
            "request a new prediction for a different duration."
        )
        if degraded_note:
            model_version += "-degraded"
            explanation += f" ({degraded_note})"
        return PriceResult(
            daily_rate=daily,
            total_price=round(daily * days, 2),
            currency="SGD",
            deposit_rate=0.30,
            model_version=model_version,
            explanation=explanation,
            was_clamped=bool(getattr(result, "was_clamped", False)),
        )

    # Fallback: mid of seed min/max not available here — use simple table
    daily = _fallback_daily_rate(category, condition)
    return PriceResult(
        daily_rate=daily,
        total_price=round(daily * days, 2),
        currency="SGD",
        deposit_rate=0.30,
        model_version="fallback-category-table",
        explanation=(
            f"Fallback pricing (ml-experiments model unavailable: {_load_error}). "
            f"daily_rate is for a {days:g}-day rental window; "
            "request a new prediction for a different duration."
        ),
        was_clamped=False,
    )


def _fallback_daily_rate(category: str, condition: str) -> float:
    base = {
        "boom lift": 280.0,
        "scissor lift": 180.0,
        "forklift": 120.0,
        "excavator": 350.0,
    }.get(category, 150.0)
    cond_mult = {
        "NEEDS_REPAIR": 0.7,
        "FAIR": 0.85,
        "GOOD": 1.0,
        "EXCELLENT": 1.15,
    }.get(condition, 1.0)
    return round(base * cond_mult, 2)
