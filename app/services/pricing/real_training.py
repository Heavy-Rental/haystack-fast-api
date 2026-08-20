"""Read realized booking prices into the dynamic-pricing feature schema."""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.models.booking import Booking
from app.models.booking_item import BookingItem
from app.services.pricing import category_mapping
from app.services.pricing.read_resilience import PricingSchemaResolution
from app.services.pricing.training_sampling import sample_distance_km

REALIZED_PRICE_STATUSES = frozenset({"CONFIRMED", "MOBILISED", "COMPLETED"})
REAL_TRAINING_DISTANCE_SEED = 42
REAL_TRAINING_COLUMNS = [
    "category",
    "condition",
    "capacity",
    "platform_height",
    "duration_days",
    "distance_km",
    "period_utilization",
    "lead_time_days",
    "price_per_day",
]


def fetch_real_training_rows(
    db: Session,
    resolution: PricingSchemaResolution,
    *,
    statuses: set[str] | frozenset[str] = REALIZED_PRICE_STATUSES,
) -> pd.DataFrame:
    """Extract usable realized booking prices as model-training rows.

    The query is read-only and uses the already-resolved pricing schema for
    every read. ``distance_km`` remains a deterministic distribution-matched
    imputation until real geocoding data is available.
    """
    normalized_statuses = tuple(sorted(status.upper() for status in statuses))
    statement = (
        select(
            BookingItem.id.label("booking_item_id"),
            AssetCategory.name.label("db_category"),
            Asset.condition.label("condition"),
            Asset.capacity.label("capacity"),
            Asset.platform_height.label("platform_height"),
            Booking.start_date.label("start_date"),
            Booking.end_date.label("end_date"),
            Booking.created_at.label("created_at"),
            BookingItem.daily_rate.label("daily_rate"),
        )
        .select_from(BookingItem)
        .join(Booking, BookingItem.booking_id == Booking.id)
        .join(Asset, BookingItem.asset_id == Asset.id)
        .join(AssetCategory, Asset.category_id == AssetCategory.id)
        .where(
            Booking.status.in_(normalized_statuses),
            BookingItem.daily_rate.is_not(None),
            BookingItem.daily_rate > 0,
            Booking.start_date.is_not(None),
            Booking.end_date.is_not(None),
        )
        .order_by(BookingItem.id)
    )
    result = db.execute(statement, execution_options=resolution.execution_options)
    source_rows = [dict(row) for row in result.mappings().all()]
    if not source_rows:
        return pd.DataFrame(columns=REAL_TRAINING_COLUMNS)

    distances = sample_distance_km(
        np.random.default_rng(REAL_TRAINING_DISTANCE_SEED),
        len(source_rows),
    )
    records: list[dict[str, object]] = []
    for source, distance_km in zip(source_rows, distances, strict=True):
        category = category_mapping.to_feature_name(str(source["db_category"]))
        capacity = float(source["capacity"]) if source["capacity"] is not None else None
        platform_height = (
            float(source["platform_height"]) if source["platform_height"] is not None else None
        )
        start_date = source["start_date"]
        end_date = source["end_date"]
        created_at = source["created_at"]
        if not isinstance(start_date, date) or not isinstance(end_date, date):
            raise TypeError("real training rows require date-valued start_date and end_date")

        # Local import avoids a module cycle while keeping repository.py as
        # the public home for both pricing-read functions.
        from app.services.pricing import repository

        period_utilization = repository.compute_period_utilization(
            db,
            resolution,
            category=category,
            capacity=capacity,
            platform_height=platform_height,
            start_date=start_date,
            end_date=end_date,
        )
        lead_time_days = (
            (start_date - created_at.date()).days if isinstance(created_at, datetime) else 0
        )
        records.append(
            {
                "category": category,
                "condition": source["condition"],
                "capacity": capacity,
                "platform_height": platform_height,
                "duration_days": max(1, (end_date - start_date).days + 1),
                "distance_km": int(distance_km),
                "period_utilization": float(period_utilization),
                "lead_time_days": lead_time_days,
                "price_per_day": float(source["daily_rate"]),
            }
        )

    return pd.DataFrame.from_records(records, columns=REAL_TRAINING_COLUMNS)
