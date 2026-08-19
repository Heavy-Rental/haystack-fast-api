from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from app.services.pricing.read_resilience import PricingSchemaResolution

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ml-experiments" / "real_training_data_check.py"
SPEC = importlib.util.spec_from_file_location("real_training_data_check", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
quality = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = quality
SPEC.loader.exec_module(quality)

PRIMARY = PricingSchemaResolution(schema="primary_snapshot", degraded=False)
DEGRADED = PricingSchemaResolution(schema="public", degraded=True)


def _quality_rows() -> pd.DataFrame:
    categories = ["excavator", "scissor lift", "boom lift", "forklift"]
    return pd.DataFrame.from_records(
        [
            {
                "booking_item_id": index,
                "status": "COMPLETED",
                "category": category,
                "daily_rate": 100.0 + index,
                "subtotal": 700.0 + index,
            }
            for index, category in enumerate(categories, start=1)
        ]
        + [
            {
                "booking_item_id": 5,
                "status": "CANCELLED",
                "category": "excavator",
                "daily_rate": None,
                "subtotal": 0.0,
            }
        ]
    )


def test_quality_summary_reports_null_and_zero_rates_by_dimension() -> None:
    rows = _quality_rows()

    by_status = quality.summarize_quality(rows, group_by="status").set_index("status")
    by_category = quality.summarize_quality(rows, group_by="category").set_index("category")

    assert by_status.loc["CANCELLED", "daily_rate_null_%"] == 100.0
    assert by_status.loc["CANCELLED", "subtotal_zero_%"] == 100.0
    assert by_category.loc["excavator", "rows"] == 2
    assert by_category.loc["excavator", "daily_rate_null_%"] == 50.0


def test_quality_gate_requires_positive_realized_prices_for_every_category() -> None:
    passed = quality.assess_real_training_data(_quality_rows())
    missing_category = _quality_rows().query("category != 'forklift'")
    failed = quality.assess_real_training_data(missing_category)

    assert passed.passed is True
    assert failed.passed is False
    assert failed.checks["daily_rate_all_categories_positive"] is False
    assert any("forklift" in detail for detail in failed.details)


def test_quality_query_uses_four_tables_and_schema_resolution() -> None:
    statement = quality.build_quality_statement()
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "primary_snapshot.booking_items" in compiled
    assert "JOIN primary_snapshot.bookings" in compiled
    assert "JOIN primary_snapshot.assets" in compiled
    assert "JOIN primary_snapshot.asset_categories" in compiled

    session = MagicMock()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {
            "booking_item_id": 1,
            "status": "completed",
            "db_category": "Fork Lift",
            "daily_rate": Decimal("120.00"),
            "subtotal": Decimal("840.00"),
        }
    ]
    session.execute.return_value = result

    rows = quality.load_quality_rows(session, DEGRADED)

    assert rows.loc[0, "status"] == "COMPLETED"
    assert rows.loc[0, "category"] == "forklift"
    assert rows.loc[0, "daily_rate"] == 120.0
    assert session.execute.call_args.kwargs["execution_options"] == {
        "schema_translate_map": {"primary_snapshot": "public"}
    }
