"""Read-only mapping onto Spring-Boot-owned ``booking_items`` (primary_snapshot).

``Booking`` has no ``asset_id`` column in the Spring schema, so utilization
joins through ``booking_items.asset_id`` and ``booking_id``. Phase 3b also reads
nullable ``daily_rate`` and ``subtotal`` as the realized-price source. See
openspec/specs/spring-entity-repository/spec.md §§5.7–5.8 and §7.
"""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BookingItem(Base):
    __tablename__ = "booking_items"
    __table_args__: ClassVar[dict] = {"schema": "primary_snapshot"}

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("primary_snapshot.bookings.id"))
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("primary_snapshot.assets.id"))
    daily_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
