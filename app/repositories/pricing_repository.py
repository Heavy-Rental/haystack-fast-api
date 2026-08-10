"""Live pricing queries against Spring-Boot-owned data (Phase 1e).

specification/SPEC-dynamic-pricing.md §5.2/§5.3. Pulled forward ahead of the
rest of app/services/pricing/ (Phase 2) so predict_price()'s two real-time
features have a real production source before this package's own PR lands —
Phase 2 relocates, not rebuilds, this module.

Reuses ml-experiments/feature_schema.py's spec_band() and
ml-experiments/pricing_tables.py's bin/fallback constants directly (same
sys.path bridge app/services/pricing_client.py already uses) rather than
duplicating them -- spec_band()'s own docstring calls it out as the single
source of truth for both training-time bucketing and this live query.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.models.booking import Booking
from app.models.booking_item import BookingItem
from app.repositories.pricing_read_resilience import PricingSchemaResolution

_ML_DIR = Path(__file__).resolve().parents[2] / "ml-experiments"
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

import feature_schema as fs  # type: ignore
import pricing_tables as pt  # type: ignore

# period_utilization's live-hold status filter (spec §5.2): equipment is held
# for the customer from PENDING_DEPOSIT onward; COMPLETED (returned) and
# CANCELLED (releases the hold) are excluded.
LIVE_HOLD_STATUSES = ("PENDING_DEPOSIT", "PENDING_CONFIRMED", "CONFIRMED", "MOBILISED")


def resolve_effective_capacity(category: str, capacity: float | None) -> float | None:
    """Asset.capacity null fallback: per-category midpoint, not NaN (spec §5.2).

    A data-entry gap, not a structural absence (unlike platform_height) --
    training data always has capacity populated, so a NaN input would be
    out-of-distribution for the trained model.
    """
    if capacity is not None:
        return capacity
    bounds = pt.CATEGORY_CAPACITY_KG.get(category)
    if bounds is None:
        return None
    return (bounds["min"] + bounds["max"]) / 2


def compute_lead_time_days(start_date: date, *, today: date | None = None) -> int:
    """lead_time_days = start_date - today (spec §5.2), no new persisted column."""
    return (start_date - (today or date.today())).days


def compute_period_utilization(
    session: Session,
    resolution: PricingSchemaResolution,
    *,
    category: str,
    capacity: float | None,
    platform_height: float | None,
    start_date: date,
    end_date: date,
) -> float:
    """Live aggregate: fraction of same-category+spec-band assets with a
    live-hold booking overlapping [start_date, end_date] (spec §5.2).

    Overlap is inclusive on both boundaries, matching
    BookingAvailabilityFilter's existing rule exactly (no same-day turnover).
    """
    effective_capacity = resolve_effective_capacity(category, capacity)
    target_band = fs.spec_band(category, effective_capacity, platform_height)

    rows = session.execute(
        select(Asset.id, Asset.capacity, Asset.platform_height)
        .join(AssetCategory, Asset.category_id == AssetCategory.id)
        .where(AssetCategory.name == category),
        execution_options=resolution.execution_options,
    ).all()

    band_asset_ids: list[int] = []
    for asset_id, raw_capacity, raw_height in rows:
        eff_capacity = resolve_effective_capacity(category, raw_capacity)
        height = float(raw_height) if raw_height is not None else None
        try:
            band = fs.spec_band(category, eff_capacity, height)
        except ValueError:
            # Can't band this asset (e.g. a null platform_height on an aerial
            # row) -- excluded from both numerator and denominator.
            continue
        if band == target_band:
            band_asset_ids.append(asset_id)

    total = len(band_asset_ids)
    if total == 0:
        return float(pt.CATEGORY_UTILIZATION.get(category, 0.0))

    booked_rows = session.execute(
        select(BookingItem.asset_id)
        .join(Booking, BookingItem.booking_id == Booking.id)
        .where(
            BookingItem.asset_id.in_(band_asset_ids),
            Booking.status.in_(LIVE_HOLD_STATUSES),
            Booking.start_date.is_not(None),
            Booking.end_date.is_not(None),
            Booking.start_date <= end_date,
            Booking.end_date >= start_date,
        )
        .distinct(),
        execution_options=resolution.execution_options,
    ).scalars().all()

    booked = len({asset_id for asset_id in booked_rows if asset_id is not None})
    return booked / total
