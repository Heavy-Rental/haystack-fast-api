"""Feature encoding schema for the dynamic-pricing model (Phase 1b + 1d).

Locked feature set per docs/dynamic-pricing-masterplan.md ("Target variable &
features"): one-hot ``category`` (mirrors ``AssetCategory.name``), ordinal
``condition``, plus the numeric features ``duration_days``, ``capacity``,
``distance_km``, ``period_utilization``, ``lead_time_days``. Target is
``price_per_day``.

``platform_height`` was added after the Phase 1b baseline SHAP review showed
boom lift/scissor lift fitting dramatically worse than forklift/excavator
(R^2 0.70/0.80 vs 0.95/0.96) -- consistent with pricing_tables.py's note that
platform_height, not capacity, is the primary size driver for aerial lifts.
It's structurally missing (not just noisy) for forklift/excavator, which have
no platform -- left as NaN rather than imputed to a sentinel like 0, so
XGBoost's native missing-value handling (a learned per-split default
direction) can route those categories around it instead of the model being
taught a specific, misleading height value for "no platform."

``period_utilization`` and ``lead_time_days`` (Phase 1d) are the model's first
real-time (not static-attribute) signals. ``period_utilization`` is a live
aggregate -- fraction of assets in the same category + spec-band (see
``spec_band()`` below) already booked over the requested window -- computed
at prediction time, not a forecast; ``lead_time_days`` is simply
``Booking.startDate - today``. Both are always populated (unlike
``platform_height``), so they belong in ``NUMERIC_FEATURES``, not
``NULLABLE_NUMERIC_FEATURES``. Kept as two separate features despite being
correlated by construction (a longer lead time tends to mean lower
utilization -- see generate_synthetic_data.py) so a SHAP review can show
which one the model actually relies on, rather than assuming and dropping one
upfront. An early booking into a not-yet-claimed window legitimately gets a
lower ``period_utilization`` and often a lower price -- intentional scarcity
pricing (same mechanism as airline/hotel pricing), not a bug.

Deliberately excluded: ``minDailyRate``/``maxDailyRate``/``baseDailyRate``/
``price_clamped`` (guardrail/derivation artifacts of the target -- would leak
it), ``asset_id``/``booking_id`` (identifiers, no signal), ``purchaseYear``
(evaluated -- condition alone passed its SHAP check cleanly, so not added),
``booking_month``/seasonality (evaluated in Phase 1d -- ``period_utilization``
already captures realized seasonal demand, e.g. a monsoon-season dip shows up
directly as lower utilization, so a calendar feature would be largely
redundant -- resolved not added, see docs/dynamic-pricing-masterplan.md), and
fuel price (considered and rejected in Phase 1d -- indirect/lagged signal, a
new external API dependency that doesn't fit this project's in-process/
no-outbound-calls architecture, and untrainable noise on synthetic data
without fabricating a correlation).

Ported near-verbatim from ``ml-experiments/feature_schema.py`` (Phase 2a,
2026-08-11) -- same ``CATEGORIES``, ``CONDITION_ORDER``, ``FEATURE_COLUMNS``,
``build_features()``/``get_target()``/``spec_band()`` logic, only the
``pricing_tables`` import changed from the ml-experiments sys.path bridge to
a local package import. No feature-set changes -- see the ml-experiments
copy for full Phase 1b/1d authoring history.
"""

import pandas as pd

from app.services.pricing import pricing_tables as pt

CATEGORIES = ["forklift", "scissor lift", "boom lift", "excavator"]

CONDITION_ORDER = {"NEEDS_REPAIR": 0, "FAIR": 1, "GOOD": 2, "EXCELLENT": 3}

NUMERIC_FEATURES = [
    "duration_days",
    "capacity",
    "distance_km",
    "period_utilization",
    "lead_time_days",
]

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


def spec_band(category: str, capacity: float | None, platform_height: float | None) -> str:
    """Category + spec-band label for ``period_utilization`` grouping (Phase 1d).

    Grouping by raw ``category`` alone would be misleading for
    ``period_utilization`` -- a fully-booked small-excavator fleet shouldn't
    make a large excavator look scarce (see
    docs/dynamic-pricing-masterplan.md). Excavator/forklift bucket on
    ``capacity``, scissor lift/boom lift bucket on ``platform_height``, via
    the fixed-constant bins in ``pricing_tables.CAPACITY_BINS``/``HEIGHT_BINS``.

    This is a grouping key only -- never fed to the model as a feature (not
    in ``FEATURE_COLUMNS``). It's the single source of truth for both
    training-time bucketing (generate_synthetic_data.py) and, later, the live
    production query (Phase 1e), so the two can't drift apart.
    """
    if category in pt.CAPACITY_BINS:
        bins = pt.CAPACITY_BINS[category]
        value = capacity
    elif category in pt.HEIGHT_BINS:
        bins = pt.HEIGHT_BINS[category]
        value = platform_height
    else:
        raise ValueError(f"No spec-band bins defined for category {category!r}")

    if value is None:
        raise ValueError(f"spec_band requires a numeric value for category {category!r}")

    # Bins are contiguous, non-overlapping, and increasing, so the first bin
    # whose upper bound the value doesn't exceed is necessarily the correct
    # one -- no need to also check the lower bound.
    for lo, hi in bins:
        if hi is None or value <= hi:
            label = f"{lo}-{hi}" if hi is not None else f"{lo}+"
            return f"{category}:{label}"
    raise AssertionError(f"unreachable: {value} did not match any band for {category!r}")
