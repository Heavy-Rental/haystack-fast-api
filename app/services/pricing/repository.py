"""Live pricing queries against Spring-Boot-owned data.

Relocated from ``app/repositories/pricing_repository.py`` (Phase 1e) into
this package (Phase 2a, 2026-08-11) per
openspec/specs/dynamic-pricing/spec.md's implementation task -- relocated,
not rebuilt, except for one real fix folded into this move (see below).

Uses this package's own ``feature_schema.spec_band()`` and
``pricing_tables.py`` bin/fallback constants (no more ml-experiments
sys.path bridge -- Phase 2a is the last consumer that needed it).

**Category-name mapping fix (2026-08-11):** ``compute_period_utilization()``
previously filtered ``AssetCategory.name == category`` using ``category`` as
given by its caller, which is always in ``feature_schema.CATEGORIES``
convention (e.g. ``"excavator"``) -- but the real DB column holds Spring-Boot
canonical names (e.g. ``"Excavator"``). That join never matched a real row,
so this function always silently fell back to the static
``pricing_tables.CATEGORY_UTILIZATION`` constant, with no error and no
degraded flag -- confirmed live against ``heavy_rental`` during Phase 2 prep.
Fixed here via ``category_mapping.to_db_name()`` on the join's right-hand
side; every other use of ``category`` in this file stays in
``feature_schema`` convention, unchanged. See
openspec/specs/dynamic-pricing/design.md "Category name mapping" for the
full incident writeup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.models.booking import Booking
from app.models.booking_item import BookingItem
from app.services.pricing import category_mapping
from app.services.pricing import feature_schema as fs
from app.services.pricing import pricing_tables as pt
from app.services.pricing.read_resilience import PricingSchemaResolution
from app.services.pricing.real_training import (
    REAL_TRAINING_COLUMNS,
    REALIZED_PRICE_STATUSES,
    fetch_real_training_rows,
    sample_distance_km,
)

__all__ = [
    "REALIZED_PRICE_STATUSES",
    "REAL_TRAINING_COLUMNS",
    "fetch_real_training_rows",
    "sample_distance_km",
]

# period_utilization's live-hold status filter: equipment is held for the
# customer from PENDING_DEPOSIT onward; COMPLETED (returned) and CANCELLED
# (releases the hold) are excluded.
LIVE_HOLD_STATUSES = ("PENDING_DEPOSIT", "PENDING_CONFIRMED", "CONFIRMED", "MOBILISED")


def resolve_effective_capacity(category: str, capacity: float | None) -> float | None:
    """Asset.capacity null fallback: per-category midpoint, not NaN.

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


@dataclass(frozen=True)
class AssetPricingRow:
    """Real per-asset attributes needed to call ``model.predict_price(...)``.

    ``category`` is already converted to ``feature_schema`` convention (via
    ``category_mapping.to_feature_name()``) -- callers must not convert it
    again. Used by the internal quote endpoint (Phase 2c) to resolve
    category/condition/capacity/platform_height and the real guardrail
    bounds from an ``asset_id`` alone -- see
    openspec/specs/dynamic-pricing/design.md "Internal quote API".
    """

    id: int
    category: str
    condition: str | None
    capacity: float | None
    platform_height: float | None
    min_daily_rate: float
    max_daily_rate: float


def get_asset_for_pricing(
    session: Session,
    resolution: PricingSchemaResolution,
    asset_id: int,
) -> AssetPricingRow | None:
    """Resolve one asset's pricing attributes server-side, by primary key.

    Returns ``None`` when no such asset exists -- the caller (the internal
    quote endpoint) turns that into a per-item error rather than raising,
    per spec.md US-4 Scenario "unresolvable asset_id". Goes through the same
    tiered ``resolution`` as every other pricing read in this package (no
    second fallback implementation for the guardrail-bound read).

    Raises:
        KeyError: ``AssetCategory.name`` isn't a recognized DB category name
            (``category_mapping.to_feature_name()``) -- a genuinely new
            category the mapping doesn't know about yet. Left to the caller
            to turn into a per-item error, same treatment as "not found".
    """
    row = session.execute(
        select(Asset, AssetCategory.name)
        .join(AssetCategory, Asset.category_id == AssetCategory.id)
        .where(Asset.id == asset_id),
        execution_options=resolution.execution_options,
    ).first()
    if row is None:
        return None
    asset, db_category_name = row
    return AssetPricingRow(
        id=asset.id,
        category=category_mapping.to_feature_name(db_category_name),
        condition=asset.condition,
        capacity=(float(asset.capacity) if asset.capacity is not None else None),
        platform_height=(
            float(asset.platform_height) if asset.platform_height is not None else None
        ),
        min_daily_rate=float(asset.min_daily_rate),
        max_daily_rate=float(asset.max_daily_rate),
    )


def compute_lead_time_days(start_date: date, *, today: date | None = None) -> int:
    """lead_time_days = start_date - today, no new persisted column."""
    return (start_date - (today or datetime.now(UTC).date())).days


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
    live-hold booking overlapping [start_date, end_date].

    Overlap is inclusive on both boundaries, matching
    BookingAvailabilityFilter's existing rule exactly (no same-day turnover).

    ``category`` is always in ``feature_schema.CATEGORIES`` convention (the
    caller's contract, same as every other pricing function) -- converted to
    the real DB name only for the ``AssetCategory.name`` filter below.
    """
    effective_capacity = resolve_effective_capacity(category, capacity)
    target_band = fs.spec_band(category, effective_capacity, platform_height)
    db_category_name = category_mapping.to_db_name(category)

    rows = session.execute(
        select(Asset.id, Asset.capacity, Asset.platform_height)
        .join(AssetCategory, Asset.category_id == AssetCategory.id)
        .where(AssetCategory.name == db_category_name),
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

    booked_rows = (
        session.execute(
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
        )
        .scalars()
        .all()
    )

    booked = len({asset_id for asset_id in booked_rows if asset_id is not None})
    return booked / total
