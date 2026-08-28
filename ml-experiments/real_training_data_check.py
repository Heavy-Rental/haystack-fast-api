"""Inspect whether live booking prices are usable as model-training signal.

This Phase 3a probe is read-only.  It joins Spring-owned booking line items to
their booking, asset, and category, then reports ``daily_rate`` and
``subtotal`` null/zero rates by booking status and by ML category.

Run from the repository root::

    uv run python ml-experiments/real_training_data_check.py

The process exits non-zero when any pricing category has no positive realized
``daily_rate`` or ``subtotal`` rows, or when realized prices are negative.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy import BigInteger, Column, MetaData, Numeric, String, Table, select
from sqlalchemy.orm import Session

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.db import SessionLocal
from app.services.pricing import feature_schema as fs
from app.services.pricing.category_mapping import to_feature_name
from app.services.pricing.read_resilience import (
    PRIMARY_SCHEMA,
    PricingSchemaResolution,
    resolve_pricing_schema,
)

REALIZED_PRICE_STATUSES = frozenset({"CONFIRMED", "MOBILISED", "COMPLETED"})
QUALITY_COLUMNS = ("daily_rate", "subtotal")

_metadata = MetaData()
_booking_items = Table(
    "booking_items",
    _metadata,
    Column("id", BigInteger),
    Column("booking_id", BigInteger),
    Column("asset_id", BigInteger),
    Column("daily_rate", Numeric),
    Column("subtotal", Numeric),
    schema=PRIMARY_SCHEMA,
)
_bookings = Table(
    "bookings",
    _metadata,
    Column("id", BigInteger),
    Column("status", String),
    schema=PRIMARY_SCHEMA,
)
_assets = Table(
    "assets",
    _metadata,
    Column("id", BigInteger),
    Column("category_id", BigInteger),
    schema=PRIMARY_SCHEMA,
)
_asset_categories = Table(
    "asset_categories",
    _metadata,
    Column("id", BigInteger),
    Column("name", String),
    schema=PRIMARY_SCHEMA,
)


@dataclass(frozen=True)
class DataQualityDecision:
    passed: bool
    checks: dict[str, bool]
    details: tuple[str, ...]


def build_quality_statement():
    """Build the four-table, read-only source query used by the live probe."""
    return (
        select(
            _booking_items.c.id.label("booking_item_id"),
            _bookings.c.status.label("status"),
            _asset_categories.c.name.label("db_category"),
            _booking_items.c.daily_rate.label("daily_rate"),
            _booking_items.c.subtotal.label("subtotal"),
        )
        .select_from(
            _booking_items.join(_bookings, _booking_items.c.booking_id == _bookings.c.id)
            .join(_assets, _booking_items.c.asset_id == _assets.c.id)
            .join(
                _asset_categories,
                _assets.c.category_id == _asset_categories.c.id,
            )
        )
        .order_by(_bookings.c.status, _asset_categories.c.name, _booking_items.c.id)
    )


def load_quality_rows(
    session: Session,
    resolution: PricingSchemaResolution,
) -> pd.DataFrame:
    """Load raw line-item prices without changing Spring-owned data."""
    result = session.execute(
        build_quality_statement(),
        execution_options=resolution.execution_options,
    )
    rows = [dict(row) for row in result.mappings().all()]
    if not rows:
        return pd.DataFrame(columns=["booking_item_id", "status", "category", *QUALITY_COLUMNS])

    frame = pd.DataFrame.from_records(rows)
    frame["status"] = frame["status"].astype("string").str.upper()
    frame["category"] = frame.pop("db_category").map(to_feature_name)
    for column in QUALITY_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def summarize_quality(rows: pd.DataFrame, *, group_by: str) -> pd.DataFrame:
    """Report counts and percentages for one grouping dimension."""
    if group_by not in {"status", "category"}:
        raise ValueError("group_by must be 'status' or 'category'")

    columns = [
        group_by,
        "rows",
        "daily_rate_null",
        "daily_rate_null_%",
        "daily_rate_zero",
        "daily_rate_zero_%",
        "daily_rate_negative",
        "subtotal_null",
        "subtotal_null_%",
        "subtotal_zero",
        "subtotal_zero_%",
        "subtotal_negative",
    ]
    if rows.empty:
        return pd.DataFrame(columns=columns)

    working = rows.copy()
    aggregations: dict[str, tuple[str, str]] = {}
    for column in QUALITY_COLUMNS:
        working[f"{column}_null"] = working[column].isna()
        working[f"{column}_zero"] = working[column].eq(0)
        working[f"{column}_negative"] = working[column].lt(0)
        aggregations[f"{column}_null"] = (f"{column}_null", "sum")
        aggregations[f"{column}_zero"] = (f"{column}_zero", "sum")
        aggregations[f"{column}_negative"] = (f"{column}_negative", "sum")

    summary = (
        working.groupby(group_by, dropna=False, sort=True)
        .agg(rows=("booking_item_id", "size"), **aggregations)
        .reset_index()
    )
    for column in QUALITY_COLUMNS:
        summary[f"{column}_null_%"] = summary[f"{column}_null"] / summary["rows"] * 100
        summary[f"{column}_zero_%"] = summary[f"{column}_zero"] / summary["rows"] * 100
    return summary[columns]


def assess_real_training_data(
    rows: pd.DataFrame,
    *,
    realized_statuses: Sequence[str] = tuple(sorted(REALIZED_PRICE_STATUSES)),
) -> DataQualityDecision:
    """Require usable realized-price signal in every production category."""
    normalized_statuses = {status.upper() for status in realized_statuses}
    realized = rows[rows["status"].isin(normalized_statuses)].copy()
    checks: dict[str, bool] = {"realized_rows_present": not realized.empty}
    details = [f"realized booking-item rows: {len(realized)}"]

    for column in QUALITY_COLUMNS:
        negative_count = int(realized[column].lt(0).sum())
        checks[f"{column}_non_negative"] = negative_count == 0
        details.append(f"realized {column} negative rows: {negative_count}")

        positive_categories = set(realized.loc[realized[column].gt(0), "category"])
        missing = sorted(set(fs.CATEGORIES) - positive_categories)
        checks[f"{column}_all_categories_positive"] = not missing
        details.append(f"{column} categories with no positive realized rows: {missing or 'none'}")

    return DataQualityDecision(
        passed=all(checks.values()),
        checks=checks,
        details=tuple(details),
    )


def _print_summary(
    *,
    resolution: PricingSchemaResolution,
    rows: pd.DataFrame,
    decision: DataQualityDecision,
) -> None:
    print(
        f"Pricing schema: {resolution.schema} (degraded={resolution.degraded}); "
        f"booking items measured: {len(rows)}"
    )
    print("\nPrice completeness by booking status:")
    print(summarize_quality(rows, group_by="status").round(2).to_string(index=False))
    print("\nPrice completeness by category:")
    print(summarize_quality(rows, group_by="category").round(2).to_string(index=False))
    print("\nPhase 3b real-data readiness checks:")
    for name, passed in decision.checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    for detail in decision.details:
        print(f"  {detail}")
    print(f"\nPHASE 3A DATA QUALITY GATE: {'PASS' if decision.passed else 'FAIL'}")


def main() -> None:
    with SessionLocal() as session:
        resolution = resolve_pricing_schema(session)
        rows = load_quality_rows(session, resolution)

    decision = assess_real_training_data(rows)
    _print_summary(resolution=resolution, rows=rows, decision=decision)
    if not decision.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
