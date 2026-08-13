"""Read-only mapping onto Spring-Boot-owned ``assets`` (primary_snapshot).

Only the columns pricing actually reads (openspec/specs/dynamic-pricing/spec.md
§5.3): category join, ``period_utilization`` spec-banding inputs
(``capacity``/``platform_height``), the model feature ``condition``, and the
guardrail bounds ``min_daily_rate``/``max_daily_rate`` (read by Phase 2a, not
Phase 1e, but declared here now since this is the first-ever model for this
table). Not a full domain model.
"""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Asset(Base):
    __tablename__ = "assets"
    __table_args__: ClassVar[dict] = {"schema": "primary_snapshot"}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    category_id: Mapped[int] = mapped_column(
        ForeignKey("primary_snapshot.asset_categories.id")
    )
    capacity: Mapped[int | None] = mapped_column()
    platform_height: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    condition: Mapped[str | None] = mapped_column()
    min_daily_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_daily_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    description: Mapped[str | None] = mapped_column()
    purchase_year: Mapped[int | None] = mapped_column()
    # Optional Spring column; omitted from SELECT when the mirror lacks it.
    location: Mapped[str | None] = mapped_column()
