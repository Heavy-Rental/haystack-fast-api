"""Phase 1c prototype: in-process predict_price() (dynamic-pricing feature).

Scratch/offline script -- lives outside the app's SDD structure per
docs/dynamic-pricing-masterplan.md, same convention as generate_synthetic_data.py
and shap_review.py. Not the production implementation: the real
predict_price() is speced for Phase 2a in openspec/specs/dynamic-pricing/spec.md,
at app/services/pricing/model.py, clamped against the real per-asset
Asset.minDailyRate/maxDailyRate read from the database.

This prototype exists so the in-development agent prototype can fetch
experimental ML pricing before Phase 2 lands. It reuses the Phase 1b/1d
model.pkl and feature_schema.py, but since it has no database access, its
guardrail bounds come from pricing_tables.CATEGORY_BASE_RATE (static,
per-category) instead of a real asset's min/maxDailyRate. Phase 2 supersedes
this entirely -- see docs/dynamic-pricing-masterplan.md's "Locked decisions"
for why the bound source differs.

period_utilization/lead_time_days (Phase 1d) are optional kwargs with
fallback defaults here -- Phase 1e wires a real live-query value through
separately; see predict_price()'s own docstring.
"""

from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

import feature_schema as fs
import pricing_tables as pt

_MODEL_PATH = Path(__file__).parent / "artifacts" / "model.pkl"
_model = joblib.load(_MODEL_PATH)


@dataclass(frozen=True)
class PricePrediction:
    raw_price: float
    clamped_price: float
    was_clamped: bool
    min_daily_rate: float
    max_daily_rate: float


def _guardrail_bounds(category: str) -> tuple[float, float]:
    """Stand-in guardrail bounds: static per-category rate_at_min/rate_at_max
    from pricing_tables.py, not a real asset's minDailyRate/maxDailyRate."""
    rates = pt.CATEGORY_BASE_RATE[category]
    return float(rates["rate_at_min"]), float(rates["rate_at_max"])


def predict_price(
    category: str,
    condition: str,
    duration_days: float,
    capacity: float,
    distance_km: float,
    platform_height: float | None,
    period_utilization: float | None = None,
    lead_time_days: float = 0.0,
) -> PricePrediction:
    """Predict price_per_day and clamp it to the category's guardrail bounds.

    period_utilization/lead_time_days (Phase 1d) are optional, not required,
    with fallback defaults -- so this prototype's existing callers (e.g.
    pricing_client.py) keep working unmodified after Phase 1d merges, ahead
    of Phase 1e wiring real live-query values through. period_utilization
    defaults to the static per-category pricing_tables.CATEGORY_UTILIZATION
    when not supplied; lead_time_days defaults to 0.0 (no lead-time signal
    available).

    No input validation is performed -- both failure modes raise, but as
    unfriendly, easy-to-misdiagnose exceptions rather than a clear message:
    an unrecognized category raises a raw KeyError (pricing_tables.
    CATEGORY_BASE_RATE lookup), and an unrecognized condition raises
    pandas' IntCastingNaNError (feature_schema.encode_condition() maps it
    to NaN via CONDITION_ORDER.map(), then .astype(int) rejects the NaN --
    it does not silently pass through). Callers that accept free-form
    input (e.g. an LLM-driven agent) should validate against the enums
    below before calling, rather than rely on either exception to surface
    usefully.

    Args:
        category: One of feature_schema.CATEGORIES, exactly --
            "forklift", "scissor lift", "boom lift", "excavator".
        condition: One of feature_schema.CONDITION_ORDER's keys, exactly --
            "NEEDS_REPAIR", "FAIR", "GOOD", "EXCELLENT".
        duration_days: Rental length, in days.
        capacity: Load capacity. Units are category-specific, matching
            training data (pricing_tables.py) -- not independently checked.
        distance_km: Delivery distance, in kilometers.
        platform_height: Platform height in metres for "scissor lift"/
            "boom lift"; must be None for "forklift"/"excavator", matching
            how the model was trained (native NaN, not a sentinel -- see
            feature_schema.py). Do not substitute 0 or another sentinel for
            the excluded categories.
        period_utilization: Fraction (0-1) of same-category/spec-band
            assets already booked over the requested window. Optional --
            omit rather than guess a value; falls back to the category's
            static pricing_tables.CATEGORY_UTILIZATION when not supplied.
        lead_time_days: Days between today and the rental start date.
            Optional -- omit rather than guess a value; defaults to 0.0
            (no lead-time signal available).
    """
    if period_utilization is None:
        period_utilization = pt.CATEGORY_UTILIZATION[category]

    row = pd.DataFrame([{
        "category": category,
        "condition": condition,
        "duration_days": duration_days,
        "capacity": capacity,
        "distance_km": distance_km,
        "platform_height": float("nan") if platform_height is None else platform_height,
        "period_utilization": period_utilization,
        "lead_time_days": lead_time_days,
    }])
    features = fs.build_features(row)
    raw_price = float(_model.predict(features)[0])

    min_rate, max_rate = _guardrail_bounds(category)
    clamped_price = min(max(raw_price, min_rate), max_rate)

    return PricePrediction(
        raw_price=round(raw_price, 2),
        clamped_price=round(clamped_price, 2),
        was_clamped=clamped_price != raw_price,
        min_daily_rate=min_rate,
        max_daily_rate=max_rate,
    )


if __name__ == "__main__":
    print(f"Loaded model from {_MODEL_PATH}")
    print(f"{'category':<14} {'condition':<12} {'raw':>8} {'clamped':>8} {'clamped?':>9}")
    for category in fs.CATEGORIES:
        is_aerial = category in pt.AERIAL_CATEGORIES
        result = predict_price(
            category=category,
            condition="GOOD",
            duration_days=7,
            capacity=(300 if is_aerial else 2000),
            distance_km=15,
            platform_height=10 if is_aerial else None,
            period_utilization=0.7,
            lead_time_days=14,
        )
        print(
            f"{category:<14} {'GOOD':<12} {result.raw_price:>8.2f} "
            f"{result.clamped_price:>8.2f} {str(result.was_clamped):>9}"
        )

    # One call relying on the period_utilization/lead_time_days fallback
    # defaults, to exercise the pre-Phase-1e call path pricing_client.py
    # still uses.
    fallback_result = predict_price(
        category="excavator",
        condition="GOOD",
        duration_days=7,
        capacity=5000,
        distance_km=15,
        platform_height=None,
    )
    print(
        f"\n{'excavator':<14} {'GOOD':<12} {fallback_result.raw_price:>8.2f} "
        f"{fallback_result.clamped_price:>8.2f} {str(fallback_result.was_clamped):>9}  (defaults)"
    )
