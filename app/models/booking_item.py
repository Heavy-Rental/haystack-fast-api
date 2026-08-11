"""Read-only mapping onto Spring-Boot-owned ``booking_items`` (primary_snapshot).

Not in specification/SPEC-dynamic-pricing.md §5.3's original model list --
added here because ``Booking`` has no ``asset_id`` column in the real schema
(specification/SPEC-spring-entity-repository.md §5.7/§7): the booking-to-asset
link only exists via this line-item table (``booking_items.asset_id`` +
``booking_items.booking_id -> bookings.id``). ``period_utilization``'s overlap
query (§5.2) needs this join to find which assets a given booking actually
holds. See docs/dynamic-pricing-masterplan.md's Phase 1e change-log entry for
this correction.
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BookingItem(Base):
    __tablename__ = "booking_items"
    __table_args__: ClassVar[dict] = {"schema": "primary_snapshot"}

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("primary_snapshot.bookings.id")
    )
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("primary_snapshot.assets.id")
    )
