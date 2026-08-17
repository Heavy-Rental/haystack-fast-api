"""Allowlisted fleet reads against Postgres-Haystack (S4 app / Phase 4).

Projects Spring ``assets`` / ``bookings`` / ``booking_items`` into the
recommend fleet DTO. Never executes caller-supplied SQL strings.
``asset_id`` is ``assets.name`` (UNIQUE) — never invented.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from psycopg.errors import UndefinedColumn, UndefinedTable
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.models.booking import Booking
from app.models.booking_item import BookingItem
from app.pipelines.catalog import is_approved_display_type
from app.services.pricing.category_mapping import to_feature_name
from app.services.pricing.read_resilience import (
    PricingSchemaResolution,
    resolve_pricing_schema,
)
from app.services.pricing.repository import LIVE_HOLD_STATUSES

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


def _i(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_undefined_column(exc: BaseException) -> bool:
    if isinstance(exc, UndefinedColumn):
        return True
    return isinstance(getattr(exc, "orig", None), UndefinedColumn)


def _is_undefined_table(exc: BaseException) -> bool:
    if isinstance(exc, UndefinedTable):
        return True
    return isinstance(getattr(exc, "orig", None), UndefinedTable)


def _ranges_overlap(
    a_start: date, a_end: date, b_start: date, b_end: date
) -> bool:
    return a_start <= b_end and b_start <= a_end


def _asset_select(*, include_location: bool = True):
    """Allowlisted columns for fleet DTOs (no caller-supplied SQL)."""
    cols: list[Any] = [
        Asset.id,
        Asset.name,
        AssetCategory.name,
        Asset.condition,
        Asset.capacity,
        Asset.platform_height,
        Asset.min_daily_rate,
        Asset.max_daily_rate,
        Asset.category_id,
        Asset.description,
        Asset.purchase_year,
    ]
    if include_location:
        cols.append(Asset.location)
    return select(*cols).join(AssetCategory, Asset.category_id == AssetCategory.id)


def _project_asset(*row: Any) -> dict[str, Any] | None:
    if len(row) < 8:
        return None
    (
        asset_pk,
        name,
        db_category,
        condition,
        capacity,
        platform_height,
        min_daily_rate,
        max_daily_rate,
        *rest,
    ) = row
    extra = list(rest)
    category_id: int | None = None
    if extra and (
        extra[0] is None
        or isinstance(extra[0], int)
        or (isinstance(extra[0], str) and str(extra[0]).strip().isdigit())
    ):
        category_id = _i(extra[0])
        extra = extra[1:]
    description = extra[0] if len(extra) > 0 else None
    purchase_year = extra[1] if len(extra) > 1 else None
    location = extra[2] if len(extra) > 2 else None
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
    pk: int | None
    try:
        pk = int(asset_pk) if asset_pk is not None else None
    except (TypeError, ValueError):
        pk = None
    loc = str(location).strip() if location is not None else ""
    desc = str(description).strip() if description is not None else ""
    return {
        "id": pk,
        "asset_id": asset_id,
        "name": asset_id,
        "equipment_type": display,
        "category": category,
        "condition": str(condition or "GOOD"),
        "capacity": _f(capacity),
        "platform_height": _f(platform_height),
        "min_daily_rate": _f(min_daily_rate) or 0.0,
        "max_daily_rate": _f(max_daily_rate) or 0.0,
        "description": desc or None,
        "purchase_year": _i(purchase_year),
        "location": loc or None,
        "category_id": category_id,
    }


def _execute_asset_select(
    session: Session,
    schema: PricingSchemaResolution,
    *,
    key: str | None = None,
):
    """Run the allowlisted asset select; drop ``location`` if the column is absent."""
    options = schema.execution_options
    stmt = _asset_select(include_location=True)
    if key is not None:
        if key.isdigit():
            stmt = stmt.where(Asset.id == int(key))
        else:
            stmt = stmt.where(Asset.name == key)
    try:
        result = session.execute(stmt, execution_options=options)
        return result.first() if key is not None else result.all()
    except Exception as exc:
        if not _is_undefined_column(exc):
            raise
        session.rollback()
        stmt = _asset_select(include_location=False)
        if key is not None:
            if key.isdigit():
                stmt = stmt.where(Asset.id == int(key))
            else:
                stmt = stmt.where(Asset.name == key)
        result = session.execute(stmt, execution_options=options)
        return result.first() if key is not None else result.all()


class FleetRepository:
    """Read-only allowlisted queries for Fleet Worker [6]."""

    def list_assets(
        self,
        session: Session,
        *,
        resolution: PricingSchemaResolution | None = None,
    ) -> list[dict[str, Any]]:
        schema = resolution or resolve_pricing_schema(session)
        rows = _execute_asset_select(session, schema)
        out: list[dict[str, Any]] = []
        for row in rows or []:
            dto = _project_asset(*row)
            if dto is not None:
                out.append(dto)
        return out

    def get_asset(
        self,
        session: Session,
        key: str | int | None,
        *,
        resolution: PricingSchemaResolution | None = None,
    ) -> dict[str, Any] | None:
        """Resolve one asset by ``assets.id`` (digits) or ``assets.name``.

        Used to hydrate Call 2 ``equipment.id`` / name from the assets table.
        Missing or unapproved rows → ``None`` (never invent).
        """
        text = str(key or "").strip()
        if not text:
            return None
        schema = resolution or resolve_pricing_schema(session)
        row = _execute_asset_select(session, schema, key=text)
        if row is None:
            return None
        return _project_asset(*row)

    def is_asset_available(
        self,
        session: Session,
        asset_pk: int | None,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        resolution: PricingSchemaResolution | None = None,
    ) -> bool | None:
        """True when no live-hold booking overlaps the window.

        Missing dates use today..today (is it free now?). Query failure → None
        (caller must not invent True).
        """
        if asset_pk is None:
            return None
        start = start_date or datetime.now(UTC).date()
        end = end_date or start
        schema = resolution or resolve_pricing_schema(session)
        try:
            rows = session.execute(
                select(Booking.start_date, Booking.end_date)
                .join(BookingItem, BookingItem.booking_id == Booking.id)
                .where(
                    BookingItem.asset_id == int(asset_pk),
                    Booking.status.in_(LIVE_HOLD_STATUSES),
                ),
                execution_options=schema.execution_options,
            ).all()
        except Exception as exc:
            if _is_undefined_table(exc) or _is_undefined_column(exc):
                session.rollback()
                return None
            raise
        for raw_start, raw_end in rows:
            b_start = raw_start if isinstance(raw_start, date) else None
            b_end = raw_end if isinstance(raw_end, date) else None
            if b_start is None or b_end is None:
                continue
            if _ranges_overlap(start, end, b_start, b_end):
                return False
        return True

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


def load_live_fleet(
    session: Session | None = None,
    *,
    resolution: PricingSchemaResolution | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read assets + bookings from the allowlisted mirror.

    Opens ``SessionLocal`` when ``session`` is omitted. Empty / missing
    schema surfaces as ``[]`` from the repository — never seed fallback.
    """
    owned = False
    db = session
    if db is None:
        from app.core.db import SessionLocal

        db = SessionLocal()
        owned = True
    try:
        repo = FleetRepository()
        return (
            repo.list_assets(db, resolution=resolution),
            repo.list_bookings(db, resolution=resolution),
        )
    finally:
        if owned:
            db.close()
