"""Production predict_price() -- Phase 2a (openspec/specs/dynamic-pricing/spec.md).

Supersedes ``ml-experiments/predict_price.py``'s prototype contract. Two real
differences from that prototype, both required by spec:

1. **Real per-asset guardrail clamping.** ``min_daily_rate``/``max_daily_rate``
   are required caller-supplied parameters (read from the real
   ``Asset.minDailyRate``/``maxDailyRate`` wherever the caller sourced the
   asset), clamped against directly -- never the ml-experiments prototype's
   static per-category ``pricing_tables.CATEGORY_BASE_RATE`` stand-in.
2. **Category-name validation.** The prototype's only protection against an
   unrecognized ``category`` was an incidental ``KeyError`` from its
   category-table guardrail lookup -- gone now that guardrails are explicit
   parameters. Without a replacement, an unrecognized category would
   silently one-hot-encode to an all-zero row (confirmed empirically during
   Phase 2a) and predict from garbage input with no error at all. This
   module raises ``ValueError`` explicitly instead.

Loads ``artifacts/model.pkl`` + ``artifacts/current.json`` once at import
time (module-level, not per-request) -- see ``reload_model()`` for the
manual-retrain hot-swap path (Phase 2b).

period_utilization/lead_time_days: when ``db``/``start_date``/``end_date``
are all given, computed as live aggregates via ``repository.py`` (this
package's relocated Phase 1e logic, category-mapping bug fixed). When any is
missing, falls back to ``pricing_tables.CATEGORY_UTILIZATION``/``0.0`` --
the same graceful-fallback shape ``ml-experiments/predict_price.py`` and
``pricing_client.py`` already established, kept for callers that don't have
a DB session available.

No further input validation beyond the category check above: an
unrecognized ``condition`` raises pandas' ``IntCastingNaNError`` (unfriendly
but real -- see ``feature_schema.encode_condition()``). Callers that accept
free-form input (e.g. an LLM-driven agent) should validate against
``feature_schema.CATEGORIES``/``CONDITION_ORDER`` before calling, same
guidance as the prototype's docstring.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy.orm import Session

from app.services.pricing import feature_schema as fs
from app.services.pricing import pricing_tables as pt
from app.services.pricing.read_resilience import resolve_pricing_schema
from app.services.pricing.repository import (
    compute_lead_time_days,
    compute_period_utilization,
    resolve_effective_capacity,
)

logger = logging.getLogger(__name__)

_ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
_MODEL_PATH = _ARTIFACTS_DIR / "model.pkl"
_META_PATH = _ARTIFACTS_DIR / "current.json"

_model = None
_model_version = "unloaded"


def _load() -> None:
    global _model, _model_version
    _model = joblib.load(_MODEL_PATH)
    meta = json.loads(_META_PATH.read_text())
    trained_at = str(meta.get("trained_at") or "")
    _model_version = f"prod-{trained_at[:10]}" if trained_at else "prod-unknown"


_load()


def reload_model() -> None:
    """Hot-swap the in-process model after a retrain, without an app restart.

    Called by the manual "retrain now" path (Phase 2b) after ``train.py``
    overwrites ``artifacts/model.pkl``/``current.json``.
    """
    _load()
    logger.info("Reloaded pricing model artifacts (model_version=%s)", _model_version)


@dataclass(frozen=True)
class PricePrediction:
    """Guardrail-clamped prediction for a specific rental window.

    ``clamped_price`` is scoped to the ``duration_days`` used in the
    prediction (duration is a model input) -- a different window needs a
    fresh ``predict_price()`` call, do not re-scale client-side.

    App-layer response shaping (currency, deposit_rate, ``total_price =
    clamped_price * duration_days``, human-readable explanation text) is
    deliberately not this dataclass's job -- callers (``pricing_client.py``,
    the future internal quote endpoint) build their own response shape from
    these fields.
    """

    raw_price: float
    clamped_price: float
    was_clamped: bool
    min_daily_rate: float
    max_daily_rate: float
    duration_days: float
    period_utilization: float
    lead_time_days: float
    degraded: bool
    model_version: str


def predict_price(
    *,
    category: str,
    condition: str | None,
    duration_days: float,
    capacity: float | None,
    distance_km: float,
    platform_height: float | None,
    min_daily_rate: float,
    max_daily_rate: float,
    db: Session | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> PricePrediction:
    """Predict price_per_day and clamp it to the asset's real guardrail bounds.

    Args:
        category: One of feature_schema.CATEGORIES, exactly -- "forklift",
            "scissor lift", "boom lift", "excavator". A raw
            ``AssetCategory.name`` value (e.g. "Fork Lift") must be
            converted first via ``category_mapping.to_feature_name()``.
        condition: One of feature_schema.CONDITION_ORDER's keys. Falls back
            to "GOOD" when ``None`` (``Asset.condition`` is nullable in the
            real schema) -- a data gap, not a structural absence.
        duration_days: Rental length, in days.
        capacity: Load capacity, category-specific units matching training
            data. Falls back to the category midpoint when ``None`` (a data
            gap, not structural -- unlike platform_height).
        distance_km: Delivery distance, in kilometers.
        platform_height: Platform height in metres for "scissor lift"/
            "boom lift"; must be ``None`` for "forklift"/"excavator",
            matching how the model was trained (native NaN, not a
            sentinel). Do not substitute 0 for the excluded categories.
        min_daily_rate: Real per-asset ``Asset.minDailyRate``. Required --
            no static fallback in this module.
        max_daily_rate: Real per-asset ``Asset.maxDailyRate``. Required --
            no static fallback in this module.
        db: Optional SQLAlchemy session. When given together with
            ``start_date``/``end_date``, ``period_utilization``/
            ``lead_time_days`` are computed as live aggregates against
            ``primary_snapshot`` (tiered read-resilience applies -- see
            ``read_resilience.py``; a cold-start failure propagates rather
            than being swallowed). When omitted, both fall back to static
            defaults.
        start_date: Proposed rental start date. Required (with ``db``/
            ``end_date``) for the live aggregate path.
        end_date: Proposed rental end date. Required (with ``db``/
            ``start_date``) for the live aggregate path.

    Raises:
        ValueError: ``category`` is not one of ``feature_schema.CATEGORIES``.
        PricingSchemaUnavailable: neither ``primary_snapshot`` nor ``public``
            has the pricing schema (cold start) -- only when a real ``db``
            session was given.
    """
    if category not in fs.CATEGORIES:
        raise ValueError(
            f"Unrecognized category {category!r}; must be one of "
            f"{fs.CATEGORIES} (feature_schema convention). A raw "
            "AssetCategory.name value must be converted first via "
            "category_mapping.to_feature_name()."
        )

    condition = condition or "GOOD"
    days = max(1.0, float(duration_days or 1.0))
    effective_capacity = resolve_effective_capacity(category, capacity)

    period_utilization: float | None = None
    lead_time_days = 0.0
    degraded = False
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
        degraded = resolution.degraded
    if period_utilization is None:
        period_utilization = float(pt.CATEGORY_UTILIZATION.get(category, 0.0))

    row = pd.DataFrame(
        [
            {
                "category": category,
                "condition": condition,
                "duration_days": days,
                "capacity": effective_capacity,
                "distance_km": distance_km,
                "platform_height": (
                    float("nan") if platform_height is None else float(platform_height)
                ),
                "period_utilization": period_utilization,
                "lead_time_days": lead_time_days,
            }
        ]
    )
    features = fs.build_features(row)
    raw_price = float(_model.predict(features)[0])

    min_rate = float(min_daily_rate)
    max_rate = float(max_daily_rate)
    clamped_price = min(max(raw_price, min_rate), max_rate)

    return PricePrediction(
        raw_price=round(raw_price, 2),
        clamped_price=round(clamped_price, 2),
        was_clamped=clamped_price != raw_price,
        min_daily_rate=min_rate,
        max_daily_rate=max_rate,
        duration_days=days,
        period_utilization=period_utilization,
        lead_time_days=lead_time_days,
        degraded=degraded,
        model_version=_model_version,
    )
