"""Feature encoding schema for the dynamic-pricing model (Phase 1b).

Locked feature set per docs/dynamic-pricing-masterplan.md ("Target variable &
features"): one-hot ``category`` (mirrors ``AssetCategory.name``), ordinal
``condition``, plus the numeric features ``duration_days``, ``capacity``,
``distance_km``. Target is ``price_per_day``.

``platform_height`` was added after the Phase 1b baseline SHAP review showed
boom lift/scissor lift fitting dramatically worse than forklift/excavator
(R^2 0.70/0.80 vs 0.95/0.96) -- consistent with pricing_tables.py's note that
platform_height, not capacity, is the primary size driver for aerial lifts.
It's structurally missing (not just noisy) for forklift/excavator, which have
no platform -- left as NaN rather than imputed to a sentinel like 0, so
XGBoost's native missing-value handling (a learned per-split default
direction) can route those categories around it instead of the model being
taught a specific, misleading height value for "no platform."

Deliberately excluded: ``minDailyRate``/``maxDailyRate``/``baseDailyRate``/
``price_clamped`` (guardrail/derivation artifacts of the target -- would leak
it), ``asset_id``/``booking_id`` (identifiers, no signal), and ``purchaseYear``
(evaluated -- condition alone passed its SHAP check cleanly, so not added).

``booking_month`` is NOT locked out -- it's a tentative exclusion, not a
decided one. A per-``booking_month`` MAE/R^2 check found a mild pattern
(January worst) consistent with the model missing seasonality signal, but
small enough that the lean is against adding it for now. See
docs/dynamic-pricing-masterplan.md's open questions; decide explicitly in
Phase 2 before this module gets ported.

This module is intentionally free of CLI/plotting dependencies so it can be
lifted into ``app/services/pricing/feature_schema.py`` largely unchanged once
Phase 2 productionizes the pricing service.
"""

import pandas as pd

CATEGORIES = ["forklift", "scissor lift", "boom lift", "excavator"]

CONDITION_ORDER = {"NEEDS_REPAIR": 0, "FAIR": 1, "GOOD": 2, "EXCELLENT": 3}

NUMERIC_FEATURES = ["duration_days", "capacity", "distance_km"]

# Only populated for scissor lift/boom lift; NaN for forklift/excavator. See
# module docstring for why this is left as a native missing value, not imputed.
NULLABLE_NUMERIC_FEATURES = ["platform_height"]

TARGET_COLUMN = "price_per_day"

FEATURE_COLUMNS = (
    [f"category_{c}" for c in CATEGORIES]
    + ["condition_ordinal"]
    + NUMERIC_FEATURES
    + NULLABLE_NUMERIC_FEATURES
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
    numeric = df[NUMERIC_FEATURES + NULLABLE_NUMERIC_FEATURES]
    X = pd.concat([category_dummies, condition_ordinal, numeric], axis=1)
    return X[FEATURE_COLUMNS]


def get_target(df: pd.DataFrame) -> pd.Series:
    """Return the target column, ``price_per_day``."""
    return df[TARGET_COLUMN]
