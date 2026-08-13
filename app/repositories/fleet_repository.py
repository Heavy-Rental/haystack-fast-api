"""Allowlisted fleet reads against Postgres-Haystack (S4 app / Phase 4).

Projects Spring ``assets`` / ``bookings`` / ``booking_items`` into the
recommend fleet DTO. Never executes caller-supplied SQL strings.
``asset_id`` is ``assets.name`` (UNIQUE) — never invented.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.models.booking import Booking
from app.models.booking_item import BookingItem
from app.pipelines.catalog import is_approved_display_type
from app.services.pricing.category_mapping import to_feature_name
from app.services.pricing.repository import LIVE_HOLD_STATUSES
from app.services.pricing.read_resilience import (
    PricingSchemaResolution,
    resolve_pricing_schema,
)

FLEET_TABLE_ALLOWLIST: tuple[str, ...] = (
    "asset_categories",
    "assets",
    "bookings",
    "booking_items",
)


def _f(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _project_asset(
    name: str | None,
    db_category: str | None,
    condition: str | None,
    capacity: Any,
    platform_height: Any,
    min_daily_rate: Any,
    max_daily_rate: Any,
) -> dict[str, Any] | None:
    asset_id = str(name or "").strip()
    display = str(db_category or "").strip()
    if not asset_id or not display:
        return None
    if not is_approved_display_type(display):
        return None
    try:
        category = to_feature_name(display)
    except KeyError:
        return None
    return {
        "asset_id": asset_id,
        "equipment_type": display,
        "category": category,
        "condition": str(condition or "GOOD"),
        "capacity": _f(capacity),
        "platform_height": _f(platform_height),
        "min_daily_rate": _f(min_daily_rate) or 0.0,
        "max_daily_rate": _f(max_daily_rate) or 0.0,
    }


class FleetRepository:
    """Read-only allowlisted queries for Fleet Worker [6]."""

    def list_assets(
        self,
        session: Session,
        *,
        resolution: PricingSchemaResolution | None = None,
    ) -> list[dict[str, Any]]:
        schema = resolution or resolve_pricing_schema(session)
        rows = session.execute(
            select(
                Asset.name,
                AssetCategory.name,
                Asset.condition,
                Asset.capacity,
                Asset.platform_height,
                Asset.min_daily_rate,
                Asset.max_daily_rate,
            ).join(AssetCategory, Asset.category_id == AssetCategory.id),
            execution_options=schema.execution_options,
        ).all()
        out: list[dict[str, Any]] = []
        for row in rows:
            dto = _project_asset(*row)
            if dto is not None:
                out.append(dto)
        return out

    def list_bookings(
        self,
        session: Session,
        *,
        resolution: PricingSchemaResolution | None = None,
    ) -> list[dict[str, Any]]:
        schema = resolution or resolve_pricing_schema(session)
        rows = session.execute(
            select(
                Asset.name,
                Booking.id,
                Booking.start_date,
                Booking.end_date,
                Booking.status,
            )
            .join(BookingItem, BookingItem.booking_id == Booking.id)
            .join(Asset, BookingItem.asset_id == Asset.id)
            .where(Booking.status.in_(LIVE_HOLD_STATUSES)),
            execution_options=schema.execution_options,
        ).all()
        out: list[dict[str, Any]] = []
        live = frozenset(LIVE_HOLD_STATUSES)
        for name, booking_id, start, end, status in rows:
            asset_id = str(name or "").strip()
            if not asset_id or str(status or "") not in live:
                continue
            out.append(
                {
                    "booking_id": str(booking_id) if booking_id is not None else "",
                    "asset_id": asset_id,
                    "start_date": start.isoformat()
                    if isinstance(start, date)
                    else start,
                    "end_date": end.isoformat() if isinstance(end, date) else end,
                    "status": status,
                }
            )
        return out
