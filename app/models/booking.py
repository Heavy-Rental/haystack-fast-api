"""Read-only mapping onto Spring-Boot-owned ``bookings`` (primary_snapshot).

Only the columns ``period_utilization``'s overlap query needs
(specification/SPEC-dynamic-pricing.md §5.2/§5.3): the rental window and
``status`` (drives the live-hold status filter). No asset link here — that's
on ``BookingItem`` (see app/models/booking_item.py), not ``Booking`` itself,
per specification/SPEC-spring-entity-repository.md §7's relationship map.
"""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__: ClassVar[dict] = {"schema": "primary_snapshot"}

    id: Mapped[int] = mapped_column(primary_key=True)
    start_date: Mapped[date | None] = mapped_column()
    end_date: Mapped[date | None] = mapped_column()
    status: Mapped[str | None] = mapped_column()
