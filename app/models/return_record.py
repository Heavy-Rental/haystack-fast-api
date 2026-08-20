"""Read-only mapping onto Spring-Boot-owned ``return_records``.

ORM stays on ``primary_snapshot``; live ``PRICING_SCHEMA=public`` remaps to
``heavy_rental.public.return_records`` via ``schema_translate_map``.
See ``openspec/specs/spring-entity-repository/spec.md`` §5.11.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReturnRecord(Base):
    __tablename__ = "return_records"
    __table_args__: ClassVar[dict] = {"schema": "primary_snapshot"}

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("primary_snapshot.bookings.id"))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime())
