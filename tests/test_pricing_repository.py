"""app/services/pricing/repository.py (openspec/specs/dynamic-pricing/spec.md).

Relocated from app/repositories/pricing_repository.py (Phase 1e) into
app/services/pricing/ (Phase 2a, 2026-08-11); see that module's docstring
for the category-name mapping fix folded into this move.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.services.pricing.read_resilience import PricingSchemaResolution
from app.services.pricing.repository import (
    compute_lead_time_days,
    compute_period_utilization,
    resolve_effective_capacity,
)

PRIMARY = PricingSchemaResolution(schema="primary_snapshot", degraded=False)
DEGRADED = PricingSchemaResolution(schema="public", degraded=True)


def test_compute_lead_time_days() -> None:
    assert compute_lead_time_days(date(2026, 8, 24), today=date(2026, 8, 10)) == 14


def test_resolve_effective_capacity_passthrough_when_present() -> None:
    assert resolve_effective_capacity("excavator", 5000) == 5000


def test_resolve_effective_capacity_falls_back_to_category_midpoint() -> None:
    # CATEGORY_CAPACITY_KG["excavator"] = {"min": 1000, "max": 30000, ...}
    assert resolve_effective_capacity("excavator", None) == 15500


def _session_returning(asset_rows: list[tuple], booked_asset_ids: list[int]) -> MagicMock:
    session = MagicMock()
    asset_result = MagicMock()
    asset_result.all.return_value = asset_rows
    booking_result = MagicMock()
    booking_result.scalars.return_value.all.return_value = booked_asset_ids
    session.execute.side_effect = [asset_result, booking_result]
    return session


def test_compute_period_utilization_bands_and_divides() -> None:
    # excavator CAPACITY_BINS: [(0,3000),(3000,7000),(7000,15000),(15000,None)]
    # asset 1,2 -> band (3000,7000] (matches target); asset 3 -> (15000, None];
    # asset 4 -> capacity null, falls back to midpoint 15500 -> also (15000, None].
    rows = [
        (1, 5000, None),
        (2, 6000, None),
        (3, 20000, None),
        (4, None, None),
    ]
    session = _session_returning(rows, booked_asset_ids=[1])

    utilization = compute_period_utilization(
        session,
        PRIMARY,
        category="excavator",
        capacity=5000,
        platform_height=None,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert utilization == 0.5  # 1 of 2 assets in the (3000,7000] band booked


def test_compute_period_utilization_no_assets_in_band_falls_back_to_static() -> None:
    session = _session_returning(asset_rows=[], booked_asset_ids=[])

    utilization = compute_period_utilization(
        session,
        PRIMARY,
        category="excavator",
        capacity=5000,
        platform_height=None,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert utilization == 0.585  # CATEGORY_UTILIZATION["excavator"]


def test_compute_period_utilization_excludes_unbandable_asset() -> None:
    # scissor lift assets bucket on platform_height; a null height can't be
    # banded and must be excluded from both numerator and denominator, not
    # crash the whole query.
    rows = [
        (1, 300, 7.0),  # bands into (0,8]
        (2, 300, None),  # unbandable -- excluded
    ]
    session = _session_returning(rows, booked_asset_ids=[1])

    utilization = compute_period_utilization(
        session,
        PRIMARY,
        category="scissor lift",
        capacity=300,
        platform_height=7.0,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert utilization == 1.0  # only asset 1 counted, and it's booked


def test_compute_period_utilization_uses_resolution_execution_options_for_both_reads() -> None:
    session = _session_returning(asset_rows=[(1, 5000, None)], booked_asset_ids=[])

    compute_period_utilization(
        session,
        DEGRADED,
        category="excavator",
        capacity=5000,
        platform_height=None,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert session.execute.call_count == 2
    for call in session.execute.call_args_list:
        assert call.kwargs["execution_options"] == DEGRADED.execution_options


def test_compute_period_utilization_filters_by_real_db_category_name() -> None:
    """Category-name mapping fix (2026-08-11), CI-safe per spec.md Verification.

    Regression test for the bug found live against heavy_rental: the
    AssetCategory.name filter must use the real DB-style name
    ("Excavator"), never the feature_schema-style name ("excavator") the
    caller passes in -- that mismatch is exactly why the join always
    returned zero rows before this fix. No live DB needed: compile the
    actual generated SQL and inspect the bound literal, which a fully
    mocked session.execute (as every other test in this file uses) cannot
    catch, since it never touches the real WHERE clause.
    """
    session = _session_returning(asset_rows=[], booked_asset_ids=[])

    compute_period_utilization(
        session,
        PRIMARY,
        category="excavator",  # feature_schema convention, the caller's contract
        capacity=5000,
        platform_height=None,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    asset_query = session.execute.call_args_list[0].args[0]
    compiled = asset_query.compile(compile_kwargs={"literal_binds": True})
    compiled_sql = str(compiled)

    assert "asset_categories.name = 'Excavator'" in compiled_sql
    assert "asset_categories.name = 'excavator'" not in compiled_sql


def test_compute_period_utilization_queries_real_asset_and_category_models() -> None:
    """The relocated query still targets the real ORM models, not stand-ins."""
    session = _session_returning(asset_rows=[], booked_asset_ids=[])

    compute_period_utilization(
        session,
        PRIMARY,
        category="scissor lift",
        capacity=None,
        platform_height=7.0,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    asset_query = session.execute.call_args_list[0].args[0]
    compiled_sql = str(asset_query.compile(compile_kwargs={"literal_binds": True}))
    assert "FROM primary_snapshot.assets" in compiled_sql
    assert "JOIN primary_snapshot.asset_categories" in compiled_sql
    assert "asset_categories.name = 'Scissors Lift'" in compiled_sql
