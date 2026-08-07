"""Generate synthetic equipment-rental pricing data (Phase 1a, dynamic-pricing feature).

Scratch/offline script -- lives outside the app's SDD structure per
docs/dynamic-pricing-masterplan.md ("Phase 1 -- offline experimentation in
ml-experiments/, scratch, outside SDD, no spec needed"). Feeds the Phase 1b
XGBoost + SHAP review.

References
----------
- Pollisum Equipment Rental (Singapore) -- published rate-card ranges for
  forklifts, aerial lifts, and excavators; illustrative benchmark for the
  SGD/day base-rate anchors in pricing_tables.py.
- Ben's Rental (Singapore) -- equipment rental rate guide, used similarly.
- NEA (National Environment Agency) Singapore -- Northeast Monsoon advisory
  (typically Dec-Mar, wettest Dec-Jan) -- basis for the monsoon seasonality
  dip, strongest for earthmoving/outdoor equipment (excavator).
- BCA (Building and Construction Authority) Singapore -- quarterly
  construction-demand / contracts-awarded data -- basis for the Q4 uplift
  (public housing / institutional contract-award pipeline).
- Fleet-KPI utilization benchmarks (general industry rental-fleet KPI
  references) -- aerial ~72-80%, blended/general ~65-72%, earthmoving
  ~55-62%, generators up to 80%+ in peak periods (generators are not one of
  our 4 categories -- reference point only, not used).
- Equipment-rental industry excavator weight classes (mini <3t, compact/midi
  3-7t, standard 7-15t, large 15t+) -- a common categorization used across
  major rental catalogs -- basis for pricing_tables.CAPACITY_BINS["excavator"]
  (Phase 1d).
- Counterbalance forklift capacity classes (roughly 1.5-2t / 2.5-3.5t /
  3.5-5t within our fleet's 1-5t range) -- standard rental/warehouse forklift
  capacity tiers -- basis for pricing_tables.CAPACITY_BINS["forklift"]
  (Phase 1d).
- Aerial-lift rental catalog height tiers -- scissor lifts commonly grouped
  around ~19/26/32/40ft platform heights, boom lifts around ~40/60/80/100ft+
  -- converted to meters to match Asset.platform_height's units -- basis for
  pricing_tables.HEIGHT_BINS (Phase 1d).

All figures below are defensible illustrative approximations derived from the
above, not verbatim quotes -- see pricing_tables.py for the exact numbers and
per-table rationale.
"""

import argparse
import datetime as dt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from faker import Faker

import feature_schema as fs
import pricing_tables as pt

SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reference-year", type=int, default=dt.date.today().year)
    parser.add_argument(
        "--output", type=Path, default=SCRIPT_DIR / "data" / "synthetic_pricing_data.csv"
    )
    parser.add_argument("--plots-dir", type=Path, default=SCRIPT_DIR / "outputs")
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if the discount-anchor or condition-ordering checks fail.",
    )
    return parser.parse_args()


def _round_to_step(value: float, step: int, lo: int, hi: int) -> int:
    stepped = round(value / step) * step
    return int(min(max(stepped, lo), hi))


def _round_to_nearest_scalar(value: float, nearest: int) -> float:
    return round(value / nearest) * nearest


def _round_to_nearest_array(values: np.ndarray, nearest: int) -> np.ndarray:
    return np.round(values / nearest) * nearest


def sample_category(rng: np.random.Generator, n: int) -> np.ndarray:
    """Equal weights across the 4 categories -- simplifying assumption, easy to
    change via a weights argument if a non-uniform fleet mix is ever needed."""
    return rng.choice(pt.CATEGORIES, size=n)


def sample_capacity_kg(rng: np.random.Generator, categories: np.ndarray) -> np.ndarray:
    capacities = np.empty(len(categories))
    for i, category in enumerate(categories):
        p = pt.CATEGORY_CAPACITY_KG[category]
        raw = rng.uniform(p["min"], p["max"])
        capacities[i] = _round_to_step(raw, p["step"], p["min"], p["max"])
    return capacities


def sample_platform_height_m(rng: np.random.Generator, categories: np.ndarray) -> np.ndarray:
    """Aerial-only. NaN for forklift/excavator -- not a physically meaningful
    dimension for those categories."""
    heights = np.full(len(categories), np.nan)
    for i, category in enumerate(categories):
        if category in pt.AERIAL_CATEGORIES:
            p = pt.CATEGORY_PLATFORM_HEIGHT_M[category]
            raw = rng.uniform(p["min"], p["max"])
            heights[i] = _round_to_step(raw, p["step"], p["min"], p["max"])
    return heights


def compute_base_daily_rate(
    categories: np.ndarray, capacity_kg: np.ndarray, platform_height_m: np.ndarray
) -> np.ndarray:
    """Elasticity-interpolated base rate from each category's primary size
    driver (capacity for forklift/excavator, platform_height for aerial
    lifts), with a small secondary capacity effect layered on for aerial
    categories (see pricing_tables.SECONDARY_CAPACITY_SLOPE)."""
    rates = np.empty(len(categories))
    for i, category in enumerate(categories):
        driver = pt.CATEGORY_PRICE_DRIVER[category]
        if driver == "capacity":
            value = capacity_kg[i]
            d_min, d_max = pt.CATEGORY_CAPACITY_KG[category]["min"], pt.CATEGORY_CAPACITY_KG[category]["max"]
        else:
            value = platform_height_m[i]
            d_min, d_max = (
                pt.CATEGORY_PLATFORM_HEIGHT_M[category]["min"],
                pt.CATEGORY_PLATFORM_HEIGHT_M[category]["max"],
            )
        frac = np.clip((value - d_min) / (d_max - d_min), 0, 1)
        scaled = frac**pt.CAPACITY_ELASTICITY_EXPONENT
        rate_min = pt.CATEGORY_BASE_RATE[category]["rate_at_min"]
        rate_max = pt.CATEGORY_BASE_RATE[category]["rate_at_max"]
        rate = rate_min + (rate_max - rate_min) * scaled

        if category in pt.AERIAL_CATEGORIES:
            cap_min = pt.CATEGORY_CAPACITY_KG[category]["min"]
            cap_max = pt.CATEGORY_CAPACITY_KG[category]["max"]
            cap_frac = np.clip((capacity_kg[i] - cap_min) / (cap_max - cap_min), 0, 1)
            secondary_mult = 1 + pt.SECONDARY_CAPACITY_SLOPE * (cap_frac - 0.5)
            rate *= secondary_mult

        rates[i] = _round_to_nearest_scalar(rate, 5)
    return rates


def sample_purchase_year_and_condition(
    rng: np.random.Generator, n: int, reference_year: int
) -> tuple[np.ndarray, np.ndarray]:
    """purchaseYear feeds a stochastic (not deterministic) condition draw --
    older assets skew toward worse condition, but condition is the only field
    that drives price (see compute_price_per_day) to avoid double-counting the
    same underlying age signal through two channels."""
    purchase_years = rng.integers(reference_year - 12, reference_year + 1, size=n)
    age = reference_year - purchase_years
    score = 3 - (age / 12) * 3 + rng.normal(0, 0.9, size=n)
    score = np.clip(np.round(score), 0, 3).astype(int)
    idx_to_condition = dict(enumerate(pt.CONDITIONS))
    conditions = np.array([idx_to_condition[s] for s in score])
    return purchase_years, conditions


def compute_guardrails(
    rng: np.random.Generator, base_rates: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    n = len(base_rates)
    min_ratio = rng.uniform(*pt.GUARDRAIL_MIN_RATIO_RANGE, size=n)
    max_ratio = rng.uniform(*pt.GUARDRAIL_MAX_RATIO_RANGE, size=n)
    min_rates = _round_to_nearest_array(base_rates * min_ratio, 5)
    max_rates = _round_to_nearest_array(base_rates * max_ratio, 5)
    # Safety clamp: guarantee strict ordering after rounding.
    min_rates = np.minimum(min_rates, base_rates - 5)
    max_rates = np.maximum(max_rates, base_rates + 5)
    return min_rates, max_rates


def sample_duration_days(rng: np.random.Generator, n: int) -> np.ndarray:
    """Right-skewed: many short jobs, few long ones. Mean ~9 days."""
    raw = rng.gamma(shape=1.6, scale=5, size=n) + 1
    return np.clip(np.round(raw), 1, 120).astype(int)


def sample_distance_km(rng: np.random.Generator, n: int) -> np.ndarray:
    """Delivery distance from the equipment yard (Tuas, postal 629462) to the
    job site. Right-skewed, same sampling approach as duration_days -- NOT
    derived from real postal codes or coordinates (see pricing_tables.py and
    docs/dynamic-pricing-masterplan.md; real geocoding is a later phase)."""
    raw = rng.gamma(shape=pt.DISTANCE_KM_GAMMA_SHAPE, scale=pt.DISTANCE_KM_GAMMA_SCALE, size=n) + 1
    return np.clip(np.round(raw), pt.DISTANCE_KM_MIN, pt.DISTANCE_KM_MAX).astype(int)


def sample_booking_month(rng: np.random.Generator, n: int) -> np.ndarray:
    """Uniform sampling -- the seasonality *signal* comes from the multiplier
    applied per row, not from biasing which months get sampled, so the
    sanity-check plots get even coverage across all 12 months."""
    return rng.integers(1, 13, size=n)


def sample_lead_time_days(rng: np.random.Generator, n: int) -> np.ndarray:
    """Days between "today" (request time) and the booking's startDate
    (Phase 1d). Right-skewed, same sampling approach as
    duration_days/distance_km -- not derived from any real booking history."""
    raw = rng.gamma(shape=pt.LEAD_TIME_GAMMA_SHAPE, scale=pt.LEAD_TIME_GAMMA_SCALE, size=n)
    return np.clip(np.round(raw), pt.LEAD_TIME_MIN_DAYS, pt.LEAD_TIME_MAX_DAYS).astype(int)


def compute_spec_bands(
    categories: np.ndarray, capacity_kg: np.ndarray, platform_height_m: np.ndarray
) -> np.ndarray:
    """Category + spec-band label per row (Phase 1d), via the same
    feature_schema.spec_band() the live production query will use later --
    diagnostic/grouping column only, never fed to the model (see
    feature_schema.py)."""
    return np.array(
        [
            fs.spec_band(c, cap, height if not np.isnan(height) else None)
            for c, cap, height in zip(categories, capacity_kg, platform_height_m)
        ]
    )


def sample_period_utilization(
    rng: np.random.Generator, categories: np.ndarray, lead_time_days: np.ndarray
) -> np.ndarray:
    """Live per-row utilization signal (Phase 1d), replacing the static
    pricing_tables.CATEGORY_UTILIZATION as firmness_premium()'s input.

    Modeled at the category level (not per spec-band) for the synthetic
    generator: spec-band grouping is what the live production query (Phase
    1e) uses to compute a real value against actual inventory; the model
    itself never sees the spec_band label (see feature_schema.py), only the
    resulting period_utilization number, so a category-level baseline is
    sufficient to teach it the right price response. Baseline is
    pricing_tables.CATEGORY_UTILIZATION, adjusted by lead_time_days (a longer
    lead time means fewer bookings have accumulated against that far-off
    window yet -- lower utilization; see pricing_tables.py) plus per-row
    noise, clipped to [0, 1].
    """
    baseline = np.array([pt.CATEGORY_UTILIZATION[c] for c in categories])
    adjustment = -pt.LEAD_TIME_UTILIZATION_SLOPE * (lead_time_days - pt.LEAD_TIME_UTILIZATION_PIVOT_DAYS)
    noise = rng.normal(0, pt.PERIOD_UTILIZATION_NOISE_STD, size=len(categories))
    return np.clip(baseline + adjustment + noise, 0.0, 1.0)


def duration_discount_multiplier(duration_days: np.ndarray) -> np.ndarray:
    return pt.DISCOUNT_FLOOR + (1 - pt.DISCOUNT_FLOOR) * np.exp(
        -pt.DISCOUNT_RATE * (duration_days - 1)
    )


def seasonality_multiplier(categories: np.ndarray, months: np.ndarray) -> np.ndarray:
    return np.array([pt.SEASONALITY[c][m] for c, m in zip(categories, months)])


def condition_multiplier(conditions: np.ndarray) -> np.ndarray:
    return np.array([pt.CONDITION_MULTIPLIER[c] for c in conditions])


def firmness_premium(period_utilization: np.ndarray) -> np.ndarray:
    """Higher utilization -> firmer (higher) prices. As of Phase 1d, takes
    the live per-row period_utilization directly rather than a static
    per-category lookup -- same formula, live input."""
    return 1 + pt.FIRMNESS_SLOPE * (period_utilization - pt.FIRMNESS_PIVOT)


def distance_price_multiplier(distance_km: np.ndarray) -> np.ndarray:
    return 1 + pt.DISTANCE_PRICE_SLOPE * (distance_km - pt.DISTANCE_PIVOT_KM)


def lead_time_urgency_multiplier(lead_time_days: np.ndarray) -> np.ndarray:
    """Small, independent last-minute-urgency premium (Phase 1d) -- see
    pricing_tables.LEAD_TIME_URGENCY_SLOPE for why this exists separately
    from the (larger) period_utilization-mediated effect. Short notice ->
    small premium; long notice -> small discount."""
    return 1 - pt.LEAD_TIME_URGENCY_SLOPE * (lead_time_days - pt.LEAD_TIME_URGENCY_PIVOT_DAYS)


def noise_std_frac(categories: np.ndarray) -> np.ndarray:
    """Uses the static per-category CATEGORY_UTILIZATION (not the live
    per-row period_utilization) -- this is about how much scatter a
    category's fleet-wide long-run utilization level implies, a distinct use
    from firmness_premium()'s live per-booking signal."""
    utilization = np.array([pt.CATEGORY_UTILIZATION[c] for c in categories])
    return pt.NOISE_SCALE * (pt.NOISE_PIVOT - utilization)


def compute_price_per_day(
    rng: np.random.Generator,
    base_rates: np.ndarray,
    min_rates: np.ndarray,
    max_rates: np.ndarray,
    duration_days: np.ndarray,
    months: np.ndarray,
    categories: np.ndarray,
    conditions: np.ndarray,
    distance_km: np.ndarray,
    period_utilization: np.ndarray,
    lead_time_days: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    discount = duration_discount_multiplier(duration_days)
    season = seasonality_multiplier(categories, months)
    cond_mult = condition_multiplier(conditions)
    firmness = firmness_premium(period_utilization)
    distance_mult = distance_price_multiplier(distance_km)
    urgency = lead_time_urgency_multiplier(lead_time_days)
    noise = rng.normal(0, noise_std_frac(categories))

    raw_price = (
        base_rates * discount * season * cond_mult * firmness * distance_mult * urgency * (1 + noise)
    )
    price_clamped = (raw_price < min_rates) | (raw_price > max_rates)
    price_per_day = np.round(np.clip(raw_price, min_rates, max_rates), 2)
    return price_per_day, price_clamped


def generate_ids(n: int, fake: Faker) -> tuple[list[str], list[str]]:
    asset_ids = [fake.unique.bothify("AST-#####") for _ in range(n)]
    booking_ids = [fake.unique.bothify("BKG-######") for _ in range(n)]
    return asset_ids, booking_ids


def assemble_dataframe(
    asset_ids,
    booking_ids,
    categories,
    capacity_kg,
    platform_height_m,
    conditions,
    purchase_years,
    booking_months,
    duration_days,
    distance_km,
    spec_bands,
    period_utilization,
    lead_time_days,
    base_rates,
    min_rates,
    max_rates,
    price_per_day,
    price_clamped,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": asset_ids,
            "booking_id": booking_ids,
            "category": categories,
            "capacity": capacity_kg,
            "platform_height": platform_height_m,
            "condition": conditions,
            "purchaseYear": purchase_years,
            "booking_month": booking_months,
            "duration_days": duration_days,
            "distance_km": distance_km,
            "spec_band": spec_bands,
            "period_utilization": period_utilization,
            "lead_time_days": lead_time_days,
            "baseDailyRate": base_rates,
            "minDailyRate": min_rates,
            "maxDailyRate": max_rates,
            "price_per_day": price_per_day,
            "price_clamped": price_clamped,
        }
    )


def run_sanity_checks(df: pd.DataFrame, plots_dir: Path, strict: bool) -> None:
    print("\n=== Sanity checks ===")
    ok = True

    print(f"\nRows: {len(df)}")
    print(df["category"].value_counts())

    print("\nprice_per_day by category:")
    print(df.groupby("category")["price_per_day"].describe())

    print("\n[Check] Duration discount anchors (mean price_per_day / baseDailyRate):")
    anchors = {
        "d=1": (df["duration_days"] == 1, (0.95, 1.05)),
        "d=6-8 (weekly)": (df["duration_days"].between(6, 8), (0.43, 0.57)),
        "d=28-32 (monthly)": (df["duration_days"].between(28, 32), (0.33, 0.40)),
    }
    for label, (mask, (lo, hi)) in anchors.items():
        subset = df.loc[mask]
        if subset.empty:
            print(f"  [WARN] {label}: no rows in this duration bucket")
            continue
        ratio = (subset["price_per_day"] / subset["baseDailyRate"]).mean()
        status = "OK" if lo <= ratio <= hi else "WARN"
        ok = ok and status == "OK"
        print(f"  [{status}] {label}: mean ratio={ratio:.3f} (target [{lo}, {hi}])")

    print("\n[Check] Condition ordering (mean price_per_day by condition, within category):")
    cond_means = df.groupby(["category", "condition"])["price_per_day"].mean().unstack()
    cond_means = cond_means[pt.CONDITIONS]
    for category, row in cond_means.iterrows():
        monotonic = row.is_monotonic_increasing
        status = "OK" if monotonic else "WARN"
        ok = ok and monotonic
        print(f"  [{status}] {category}: {row.round(2).to_dict()}")

    print("\n[Check] Seasonality (mean price_per_day by month, per category):")
    season_means = df.groupby(["category", "booking_month"])["price_per_day"].mean().unstack()
    print(season_means.round(2))

    print("\n[Check] Primary size-driver correlation with price_per_day:")
    for category in pt.CATEGORIES:
        subset = df[df["category"] == category]
        driver_col = "capacity" if pt.CATEGORY_PRICE_DRIVER[category] == "capacity" else "platform_height"
        corr = subset[driver_col].corr(subset["price_per_day"])
        status = "OK" if corr > 0.3 else "WARN"
        ok = ok and status == "OK"
        print(f"  [{status}] {category}: corr(price, {driver_col})={corr:.3f}")
        if category in pt.AERIAL_CATEGORIES:
            secondary_corr = subset["capacity"].corr(subset["price_per_day"])
            print(f"       (secondary) corr(price, capacity)={secondary_corr:.3f}")

    print("\n[Check] Distance price effect (mean price_per_day / baseDailyRate by distance bucket):")
    near = df["distance_km"] <= 5
    far = df["distance_km"] >= 35
    if near.any() and far.any():
        near_ratio = (df.loc[near, "price_per_day"] / df.loc[near, "baseDailyRate"]).mean()
        far_ratio = (df.loc[far, "price_per_day"] / df.loc[far, "baseDailyRate"]).mean()
        status = "OK" if far_ratio > near_ratio else "WARN"
        ok = ok and status == "OK"
        print(f"  [{status}] near(<=5km) ratio={near_ratio:.3f}, far(>=35km) ratio={far_ratio:.3f}")
    else:
        print("  [WARN] not enough rows in the near/far distance buckets to check")

    print("\n[Check] period_utilization effect (mean price_per_day / baseDailyRate by utilization tercile):")
    print(f"  range: [{df['period_utilization'].min():.3f}, {df['period_utilization'].max():.3f}]")
    terciles = pd.qcut(df["period_utilization"], 3, labels=["low", "mid", "high"])
    tercile_ratio = (df["price_per_day"] / df["baseDailyRate"]).groupby(terciles, observed=True).mean()
    utilization_monotonic = tercile_ratio["low"] < tercile_ratio["mid"] < tercile_ratio["high"]
    status = "OK" if utilization_monotonic else "WARN"
    ok = ok and utilization_monotonic
    print(f"  [{status}] {tercile_ratio.round(3).to_dict()} (expect low < mid < high)")

    print("\n[Check] lead_time_days effect (mean price_per_day / baseDailyRate, near vs far lead time):")
    near_lead = df["lead_time_days"] <= 5
    far_lead = df["lead_time_days"] >= 40
    if near_lead.any() and far_lead.any():
        near_lead_ratio = (df.loc[near_lead, "price_per_day"] / df.loc[near_lead, "baseDailyRate"]).mean()
        far_lead_ratio = (df.loc[far_lead, "price_per_day"] / df.loc[far_lead, "baseDailyRate"]).mean()
        status = "OK" if near_lead_ratio > far_lead_ratio else "WARN"
        ok = ok and status == "OK"
        print(f"  [{status}] near(<=5d) ratio={near_lead_ratio:.3f}, far(>=40d) ratio={far_lead_ratio:.3f} (expect near > far)")
    else:
        print("  [WARN] not enough rows in the near/far lead-time buckets to check")

    print("\n[Check] Guardrail clamping:")
    clamp_rate_overall = df["price_clamped"].mean()
    print(f"  Overall: {clamp_rate_overall:.1%}")
    for category, rate in df.groupby("category")["price_clamped"].mean().items():
        status = "WARN" if rate > 0.20 else "OK"
        print(f"  [{status}] {category}: {rate:.1%}")

    print("\npurchaseYear vs condition cross-tab:")
    print(pd.crosstab(df["purchaseYear"], df["condition"])[pt.CONDITIONS])

    plots_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid")

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=df, x="category", y="price_per_day", ax=ax)
    ax.set_title("price_per_day by category")
    fig.tight_layout()
    fig.savefig(plots_dir / "price_hist_by_category.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    by_duration = df.groupby("duration_days").apply(
        lambda g: (g["price_per_day"] / g["baseDailyRate"]).mean(), include_groups=False
    )
    ax.plot(by_duration.index, by_duration.values, marker=".", linestyle="none", alpha=0.4)
    ax.axhline(0.43, color="gray", linestyle="--", linewidth=1)
    ax.axhline(0.57, color="gray", linestyle="--", linewidth=1)
    ax.axhline(0.33, color="gray", linestyle=":", linewidth=1)
    ax.axhline(0.40, color="gray", linestyle=":", linewidth=1)
    ax.set_xlabel("duration_days")
    ax.set_ylabel("price_per_day / baseDailyRate")
    ax.set_title("Duration discount curve check (dashed=weekly target, dotted=monthly target)")
    fig.tight_layout()
    fig.savefig(plots_dir / "discount_curve_check.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.boxplot(data=df, x="category", y="price_per_day", hue="condition", hue_order=pt.CONDITIONS, ax=ax)
    ax.set_title("price_per_day by condition, per category")
    fig.tight_layout()
    fig.savefig(plots_dir / "price_by_condition.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    for category in pt.CATEGORIES:
        series = season_means.loc[category]
        ax.plot(series.index, series.values, marker="o", label=category)
    ax.set_xlabel("booking_month")
    ax.set_ylabel("mean price_per_day")
    ax.set_title("Seasonality by month, per category")
    ax.legend()
    fig.tight_layout()
    fig.savefig(plots_dir / "seasonality_by_month.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    aerial = df[df["category"].isin(pt.AERIAL_CATEGORIES)]
    non_aerial = df[~df["category"].isin(pt.AERIAL_CATEGORIES)]
    sns.scatterplot(data=aerial, x="platform_height", y="price_per_day", hue="category", alpha=0.4, ax=axes[0])
    axes[0].set_title("Aerial: platform_height (primary) vs price")
    sns.scatterplot(data=non_aerial, x="capacity", y="price_per_day", hue="category", alpha=0.4, ax=axes[1])
    axes[1].set_title("Forklift/excavator: capacity (primary) vs price")
    fig.tight_layout()
    fig.savefig(plots_dir / "size_driver_check.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    by_distance = df.groupby("distance_km").apply(
        lambda g: (g["price_per_day"] / g["baseDailyRate"]).mean(), include_groups=False
    )
    ax.plot(by_distance.index, by_distance.values, marker=".", linestyle="none", alpha=0.6)
    ax.set_xlabel("distance_km")
    ax.set_ylabel("price_per_day / baseDailyRate")
    ax.set_title("Distance price effect (mean ratio by distance_km, expect mild upward trend)")
    fig.tight_layout()
    fig.savefig(plots_dir / "distance_effect_check.png")
    plt.close(fig)

    # Ratio (price_per_day / baseDailyRate), not raw price_per_day -- same
    # reason as distance_effect_check.png above: period_utilization/
    # lead_time_days are secondary effects (FIRMNESS_SLOPE/
    # LEAD_TIME_URGENCY_SLOPE, both deliberately small relative to
    # category/capacity/duration -- see pricing_tables.py), so a raw-price
    # scatter is dominated by those bigger drivers and the trend this plot
    # exists to show gets buried in noise.
    #
    # Quantile bins (equal row count per bin), not equal-width -- both
    # features are right-/left-skewed with a sparse tail (e.g. only ~20 of
    # 5000 rows have lead_time_days >= 70), so equal-width bins leave the
    # tail with 1-2 rows per bin -- not wrong data, just too few samples per
    # bin to average out each row's individual noise term, which reads as
    # meaningless scatter rather than the real trend. Quantile bins widen
    # automatically in sparse regions to keep a stable sample size per bin.
    fig, ax = plt.subplots(figsize=(8, 5))
    utilization_bins = pd.qcut(df["period_utilization"], 20, duplicates="drop")
    by_utilization = (df["price_per_day"] / df["baseDailyRate"]).groupby(utilization_bins, observed=True).mean()
    bin_midpoints = [interval.mid for interval in by_utilization.index]
    ax.plot(bin_midpoints, by_utilization.values, marker=".", linestyle="none", alpha=0.8)
    ax.set_xlabel("period_utilization")
    ax.set_ylabel("price_per_day / baseDailyRate")
    ax.set_title("period_utilization price effect (mean ratio by quantile bin, expect upward trend)")
    fig.tight_layout()
    fig.savefig(plots_dir / "period_utilization_effect_check.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    lead_time_bins = pd.qcut(df["lead_time_days"], 20, duplicates="drop")
    by_lead_time = (df["price_per_day"] / df["baseDailyRate"]).groupby(lead_time_bins, observed=True).mean()
    bin_midpoints = [interval.mid for interval in by_lead_time.index]
    ax.plot(bin_midpoints, by_lead_time.values, marker=".", linestyle="none", alpha=0.8)
    ax.set_xlabel("lead_time_days")
    ax.set_ylabel("price_per_day / baseDailyRate")
    ax.set_title("lead_time_days price effect (mean ratio by quantile bin, expect mild downward trend)")
    fig.tight_layout()
    fig.savefig(plots_dir / "lead_time_effect_check.png")
    plt.close(fig)

    print(f"\nPlots written to {plots_dir}")
    print(f"\nOverall: {'[OK] all checks passed' if ok else '[WARN] one or more checks out of target range'}")

    if strict and not ok:
        raise SystemExit(1)


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    Faker.seed(args.seed)
    fake = Faker()

    categories = sample_category(rng, args.rows)
    capacity_kg = sample_capacity_kg(rng, categories)
    platform_height_m = sample_platform_height_m(rng, categories)
    base_rates = compute_base_daily_rate(categories, capacity_kg, platform_height_m)
    purchase_years, conditions = sample_purchase_year_and_condition(
        rng, args.rows, args.reference_year
    )
    min_rates, max_rates = compute_guardrails(rng, base_rates)
    duration_days = sample_duration_days(rng, args.rows)
    booking_months = sample_booking_month(rng, args.rows)
    distance_km = sample_distance_km(rng, args.rows)
    lead_time_days = sample_lead_time_days(rng, args.rows)
    spec_bands = compute_spec_bands(categories, capacity_kg, platform_height_m)
    period_utilization = sample_period_utilization(rng, categories, lead_time_days)
    price_per_day, price_clamped = compute_price_per_day(
        rng,
        base_rates,
        min_rates,
        max_rates,
        duration_days,
        booking_months,
        categories,
        conditions,
        distance_km,
        period_utilization,
        lead_time_days,
    )
    asset_ids, booking_ids = generate_ids(args.rows, fake)

    df = assemble_dataframe(
        asset_ids,
        booking_ids,
        categories,
        capacity_kg,
        platform_height_m,
        conditions,
        purchase_years,
        booking_months,
        duration_days,
        distance_km,
        spec_bands,
        period_utilization,
        lead_time_days,
        base_rates,
        min_rates,
        max_rates,
        price_per_day,
        price_clamped,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} rows to {args.output}")

    if not args.no_plots:
        run_sanity_checks(df, args.plots_dir, args.strict)


if __name__ == "__main__":
    main()
