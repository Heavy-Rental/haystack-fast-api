"""Feature encoding schema for the dynamic-pricing model (Phase 1b).

Locked feature set per docs/dynamic-pricing-masterplan.md ("Target variable &
features"): one-hot ``category`` (mirrors ``AssetCategory.name``), ordinal
``condition``, plus the numeric features ``duration_days``, ``capacity``,
``distance_km``. Target is ``price_per_day``.

Deliberately excluded: ``minDailyRate``/``maxDailyRate``/``baseDailyRate``/
``price_clamped`` (guardrail/derivation artifacts of the target -- would leak
it), and ``platform_height``/``purchaseYear``/``booking_month``/``asset_id``/
``booking_id`` (outside the locked Day 2-3 feature list).

This module is intentionally free of CLI/plotting dependencies so it can be
lifted into ``app/services/pricing/feature_schema.py`` largely unchanged once
Phase 2 productionizes the pricing service.
"""

import pandas as pd

CATEGORIES = ["forklift", "scissor lift", "boom lift", "excavator"]

CONDITION_ORDER = {"NEEDS_REPAIR": 0, "FAIR": 1, "GOOD": 2, "EXCELLENT": 3}

NUMERIC_FEATURES = ["duration_days", "capacity", "distance_km"]

TARGET_COLUMN = "price_per_day"

FEATURE_COLUMNS = (
    [f"category_{c}" for c in CATEGORIES] + ["condition_ordinal"] + NUMERIC_FEATURES
)


def encode_condition(series: pd.Series) -> pd.Series:
    """Map ``condition`` strings to their locked ordinal scale (0-3)."""
    return series.map(CONDITION_ORDER).astype(int)


def encode_category(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot encode ``category`` with a fixed, stable column set.

    Uses ``pd.Categorical`` with an explicit ``categories=CATEGORIES`` so the
    output always has exactly ``len(CATEGORIES)`` columns in a fixed order,
    even if a slice of ``df`` is missing one of the categories.
    """
    categorical = pd.Categorical(df["category"], categories=CATEGORIES)
    dummies = pd.get_dummies(categorical, prefix="category")
    dummies.index = df.index
    return dummies


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the model-ready feature matrix ``X`` from a raw dataframe."""
    category_dummies = encode_category(df)
    condition_ordinal = encode_condition(df["condition"]).rename("condition_ordinal")
    numeric = df[NUMERIC_FEATURES]
    X = pd.concat([category_dummies, condition_ordinal, numeric], axis=1)
    return X[FEATURE_COLUMNS]


def get_target(df: pd.DataFrame) -> pd.Series:
    """Return the target column, ``price_per_day``."""
    return df[TARGET_COLUMN]
