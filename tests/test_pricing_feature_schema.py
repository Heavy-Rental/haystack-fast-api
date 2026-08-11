"""app/services/pricing/feature_schema.py (openspec/specs/dynamic-pricing/spec.md).

Ported near-verbatim from ml-experiments/feature_schema.py (Phase 2a,
2026-08-11) -- no ml-experiments tests/ existed for this module (scratch
code convention), so this is the first coverage of the transforms
themselves, per spec.md's Verification: "feature schema transforms (one-hot
columns, ordinal mapping, NaN passthrough for non-aerial platform_height)".
"""

from __future__ import annotations

import math

import pandas as pd

from app.services.pricing import category_mapping
from app.services.pricing.feature_schema import (
    CATEGORIES,
    CONDITION_ORDER,
    FEATURE_COLUMNS,
    build_features,
    encode_category,
    encode_condition,
    spec_band,
)


def _row(**overrides) -> pd.DataFrame:
    base = {
        "category": "excavator",
        "condition": "GOOD",
        "duration_days": 7,
        "capacity": 5000,
        "distance_km": 15,
        "platform_height": float("nan"),
        "period_utilization": 0.6,
        "lead_time_days": 10,
    }
    base.update(overrides)
    return pd.DataFrame([base])


def test_encode_category_one_hot_fixed_column_set() -> None:
    df = _row(category="forklift")
    dummies = encode_category(df)

    assert list(dummies.columns) == [f"category_{c}" for c in CATEGORIES]
    assert dummies.iloc[0]["category_forklift"]
    assert not dummies.iloc[0]["category_excavator"]


def test_encode_condition_ordinal_scale() -> None:
    series = pd.Series(["NEEDS_REPAIR", "FAIR", "GOOD", "EXCELLENT"])
    encoded = encode_condition(series)

    assert list(encoded) == [0, 1, 2, 3]
    assert encoded.dtype == int


def test_build_features_returns_locked_column_order() -> None:
    X = build_features(_row())
    assert list(X.columns) == FEATURE_COLUMNS


def test_build_features_nan_passthrough_for_non_aerial_platform_height() -> None:
    X = build_features(_row(category="excavator", platform_height=float("nan")))
    assert math.isnan(X.iloc[0]["platform_height"])


def test_build_features_real_platform_height_for_aerial() -> None:
    X = build_features(_row(category="boom lift", platform_height=18.5))
    assert X.iloc[0]["platform_height"] == 18.5


def test_spec_band_capacity_dimension_for_excavator() -> None:
    assert spec_band("excavator", 5000, None) == "excavator:3000-7000"
    assert spec_band("excavator", 500, None) == "excavator:0-3000"
    assert spec_band("excavator", 20000, None) == "excavator:15000+"


def test_spec_band_height_dimension_for_aerial() -> None:
    assert spec_band("scissor lift", None, 7.0) == "scissor lift:0-8"
    assert spec_band("boom lift", None, 25.0) == "boom lift:24-31"


def test_category_mapping_round_trips_all_four_categories() -> None:
    for db_name, feature_name in category_mapping.DB_NAME_TO_FEATURE_NAME.items():
        assert feature_name in CATEGORIES
        assert category_mapping.to_feature_name(db_name) == feature_name
        assert category_mapping.to_db_name(feature_name) == db_name


def test_category_mapping_covers_every_condition_order_key_too() -> None:
    # Sanity check the two locked vocabularies stay in sync with what the
    # model was actually trained on -- not a mapping test, a drift guard.
    assert set(CONDITION_ORDER) == {"NEEDS_REPAIR", "FAIR", "GOOD", "EXCELLENT"}
