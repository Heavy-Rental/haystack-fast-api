"""Read-only mapping onto Spring-Boot-owned ``bookings`` (primary_snapshot).

Pricing reads the rental window and status for utilization, plus ``created_at``
and ``total_amount`` for Phase 3 real-price training schema parity. The asset
link remains on ``BookingItem`` (see app/models/booking_item.py), per
openspec/specs/spring-entity-repository/spec.md §7’s relationship map.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar

from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__: ClassVar[dict] = {"schema": "primary_snapshot"}

    id: Mapped[int] = mapped_column(primary_key=True)
    start_date: Mapped[date | None] = mapped_column()
    end_date: Mapped[date | None] = mapped_column()
    status: Mapped[str | None] = mapped_column()
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime | None] = mapped_column(DateTime())
