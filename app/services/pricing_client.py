"""Single import site for predict_price() (FR-020–022).

Prototype: ml-experiments/predict_price.py (experimental model).
Production swap: change only this module to app.services.pricing.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_ML_DIR = Path(__file__).resolve().parents[2] / "ml-experiments"
_predict_fn: Callable[..., Any] | None = None
_load_error: str | None = None


@dataclass(frozen=True)
class PriceResult:
    daily_rate: float
    weekly_rate: float
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
    capacity: float,
    distance_km: float,
    platform_height: float | None,
) -> PriceResult:
    """Predict daily rate; fallback if experimental model missing."""
    _ensure_loaded()
    if _predict_fn is not None:
        result = _predict_fn(
            category=category,
            condition=condition,
            duration_days=duration_days,
            capacity=capacity,
            distance_km=distance_km,
            platform_height=platform_height,
        )
        daily = float(result.clamped_price)
        return PriceResult(
            daily_rate=daily,
            weekly_rate=round(daily * 7, 2),
            currency="SGD",
            deposit_rate=0.30,
            model_version="experimental-ml_experiments",
            explanation="From ml-experiments.predict_price() (experimental model).",
            was_clamped=bool(getattr(result, "was_clamped", False)),
        )

    # Fallback: mid of seed min/max not available here — use simple table
    daily = _fallback_daily_rate(category, condition)
    return PriceResult(
        daily_rate=daily,
        weekly_rate=round(daily * 7, 2),
        currency="SGD",
        deposit_rate=0.30,
        model_version="fallback-category-table",
        explanation=(
            f"Fallback pricing (ml-experiments model unavailable: {_load_error})."
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
