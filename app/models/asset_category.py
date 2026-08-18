"""Read-only mapping onto Spring-Boot-owned ``asset_categories`` (primary_snapshot).

See openspec/specs/dynamic-pricing/spec.md §5.3 — pricing reads this schema
only for the category join (never encodes the raw ``category_id`` FK).
"""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AssetCategory(Base):
    __tablename__ = "asset_categories"
    __table_args__: ClassVar[dict] = {"schema": "primary_snapshot"}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
