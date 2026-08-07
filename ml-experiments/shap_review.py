"""SHAP review of the pricing model (Phase 1b, dynamic-pricing feature).

Scratch/offline script -- lives outside the app's SDD structure per
docs/dynamic-pricing-masterplan.md, same convention as generate_synthetic_data.py.

Produces:
- outputs/shap_summary.png -- global feature-importance bar plot.
- outputs/shap_duration_check.png -- predicted price vs duration_days, all
  other features held fixed at representative values. Expected: non-increasing
  (longer rentals get progressively larger daily-rate discounts).
- outputs/shap_condition_check.png -- predicted price vs condition, all other
  features (including duration_days) held fixed. Expected: non-decreasing as
  condition improves NEEDS_REPAIR -> FAIR -> GOOD -> EXCELLENT.
- outputs/shap_capacity_check.png -- predicted price vs capacity, swept within
  the frozen row's own category range (capacity scales differ wildly across
  categories -- e.g. excavator 1000-30000kg vs boom lift 200-450kg). Expected:
  non-decreasing (bigger equipment costs more within a category).
- outputs/shap_distance_check.png -- predicted price vs distance_km, all other
  features held fixed. Expected: non-decreasing (per the masterplan's locked
  "small, monotonic" delivery-distance premium).
- outputs/shap_period_utilization_check.png -- predicted price vs
  period_utilization, all other features held fixed. Expected: non-decreasing
  (higher utilization -> firmer prices, per generate_synthetic_data.py's
  firmness_premium()). Phase 1d.
- outputs/shap_lead_time_check.png -- predicted price vs lead_time_days, all
  other features (including period_utilization) held fixed. Expected:
  non-increasing (longer notice -> softer prices; this is the *independent*
  lead_time_urgency_multiplier effect, not the period_utilization-mediated
  one, since utilization is frozen for this sweep). Phase 1d. Correlated with
  period_utilization by construction (see feature_schema.py) -- the SHAP
  summary plot (below) is where a human compares which of the two the model
  actually leans on; this sweep only checks that lead_time_days still carries
  its own standalone direction, not their relative importance.
- outputs/shap_platform_height_check.png -- predicted price vs platform_height,
  swept within the frozen row's own aerial-category range. Frozen category is
  forced to the more common of scissor lift/boom lift, not the dataset-wide
  mode category (forklift/excavator have no platform_height, so a sweep frozen
  to either would be meaningless). Expected: non-decreasing (taller platform
  costs more within a category).
- outputs/shap_category_ranking.png -- predicted price for each category at
  its own representative row (own typical capacity/platform_height, shared
  condition/duration_days/distance_km). No monotonicity expectation -- purely
  descriptive, not part of --strict.

All seven sweep checks tolerate a small fraction of adjacent-step violations
(XGBoost trees aren't constrained to be monotonic) rather than requiring a
perfectly monotonic sweep.
"""

import argparse
import textwrap
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap

import feature_schema as fs

SCRIPT_DIR = Path(__file__).resolve().parent
VIOLATION_TOLERANCE = 0.1
# A step only counts as a violation once it moves against the expected
# direction by more than this fraction of the previous value -- filters out
# small XGBoost step-noise on an already-flat plateau (e.g. the discount
# curve after ~15 days) without masking genuine reversals.
STEP_NOISE_TOLERANCE = 0.03


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=SCRIPT_DIR / "data" / "synthetic_pricing_data.csv")
    parser.add_argument("--model", type=Path, default=SCRIPT_DIR / "artifacts" / "model.pkl")
    parser.add_argument("--plots-dir", type=Path, default=SCRIPT_DIR / "outputs")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any of the duration/condition/capacity/distance/platform_height "
        "monotonicity checks fail.",
    )
    return parser.parse_args()


def representative_row(X: pd.DataFrame, category: str | None = None) -> pd.Series:
    """A single feature row at the dataset's typical values, used as the
    "hold everything else fixed" baseline for a sweep check.

    By default the frozen category is the dataset-wide mode. Pass ``category``
    to force a specific one instead (e.g. the platform_height sweep needs an
    aerial category, since forklift/excavator never have a platform_height).
    """
    row = X.median(numeric_only=True)

    category_cols = [c for c in X.columns if c.startswith("category_")]
    target_category_col = f"category_{category}" if category is not None else X[category_cols].sum().idxmax()
    for col in category_cols:
        row[col] = 1 if col == target_category_col else 0

    row["condition_ordinal"] = int(round(row["condition_ordinal"]))

    # X.median(numeric_only=True) above is a dataset-wide median, which can be
    # out of range for the frozen category -- capacity in particular varies
    # wildly by category (e.g. scissor lift tops out at 450kg, well under the
    # dataset-wide median). Recompute both conditioned on the frozen category;
    # for platform_height this also fixes non-aerial baselines incorrectly
    # inheriting a real aerial height instead of staying NaN.
    category_rows = X[X[target_category_col] == 1]
    row["capacity"] = category_rows["capacity"].median()
    if "platform_height" in row.index:
        row["platform_height"] = category_rows["platform_height"].median()

    return row


def mode_aerial_category(X: pd.DataFrame) -> str:
    """The more common of the categories that actually have a platform_height
    (i.e. scissor lift/boom lift), for use as the platform_height sweep's
    frozen category."""
    category_cols = [c for c in X.columns if c.startswith("category_")]
    aerial_rows = X[X["platform_height"].notna()]
    mode_col = aerial_rows[category_cols].sum().idxmax()
    return mode_col.removeprefix("category_")


def sweep(model, base_row: pd.Series, feature: str, values) -> np.ndarray:
    rows = pd.DataFrame([base_row] * len(values)).reset_index(drop=True)
    rows[feature] = values
    return model.predict(rows[fs.FEATURE_COLUMNS])


def active_category(base_row: pd.Series) -> str:
    category_cols = [c for c in base_row.index if c.startswith("category_")]
    return next(c for c in category_cols if base_row[c] == 1).removeprefix("category_")


def describe_frozen_row(base_row: pd.Series, varying_feature: str) -> str:
    """Human-readable summary of the representative row's fixed values,
    excluding whichever feature the sweep is varying."""
    condition_labels = {v: k for k, v in fs.CONDITION_ORDER.items()}

    fields = {
        "category": f"category={active_category(base_row)}",
        "condition_ordinal": f"condition={condition_labels[int(base_row['condition_ordinal'])]}",
        "duration_days": f"duration_days={base_row['duration_days']:g}",
        "capacity": f"capacity={base_row['capacity']:g}kg",
        "distance_km": f"distance_km={base_row['distance_km']:g}km",
        "period_utilization": f"period_utilization={base_row['period_utilization']:.2f}",
        "lead_time_days": f"lead_time_days={base_row['lead_time_days']:g}",
    }
    if "platform_height" in base_row.index:
        height = base_row["platform_height"]
        fields["platform_height"] = (
            f"platform_height={height:g}m" if pd.notna(height) else "platform_height=n/a"
        )
    fields.pop(varying_feature, None)
    return "frozen: " + ", ".join(fields.values())


def check_monotonic(values: np.ndarray, direction: str, tolerance: float = VIOLATION_TOLERANCE):
    diffs = np.diff(values)
    step_threshold = STEP_NOISE_TOLERANCE * np.abs(values[:-1])
    if direction == "decreasing":
        violations = int(np.sum(diffs > step_threshold))
    else:
        violations = int(np.sum(diffs < -step_threshold))
    violation_frac = violations / len(diffs) if len(diffs) else 0.0
    return violation_frac <= tolerance, violation_frac


def plot_summary(explainer, X: pd.DataFrame, out_path: Path) -> None:
    shap_values = explainer(X)
    shap.summary_plot(shap_values, X, plot_type="bar", show=False)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_sweep(
    x_values, y_values, xlabel: str, title: str, frozen_description: str, out_path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.8))
    ax.plot(x_values, y_values, marker="o")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Predicted price_per_day")
    fig.suptitle(title, fontsize=12)
    wrapped_frozen = "\n".join(textwrap.wrap(frozen_description, width=55))
    ax.set_title(wrapped_frozen, fontsize=9, color="gray")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def category_ranking(model, X: pd.DataFrame) -> pd.DataFrame:
    """Predicted price for each category's own representative row: shared
    condition/duration_days/distance_km, but each category's own typical
    capacity/platform_height (those vary too wildly by category -- see
    representative_row -- to hold at one fixed value across all of them)."""
    rows = []
    for category in fs.CATEGORIES:
        row = representative_row(X, category=category)
        pred = model.predict(pd.DataFrame([row])[fs.FEATURE_COLUMNS])[0]
        rows.append({"category": category, "predicted_price": pred})
    return pd.DataFrame(rows).sort_values("predicted_price", ascending=False).reset_index(drop=True)


def plot_category_ranking(ranking: pd.DataFrame, frozen_description: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.8))
    bars = ax.bar(ranking["category"], ranking["predicted_price"], color="#1f77b4")
    ax.set_xlabel("category")
    ax.set_ylabel("Predicted price_per_day")
    for bar, price in zip(bars, ranking["predicted_price"]):
        ax.annotate(
            f"{price:.0f}",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            ha="center", va="bottom", fontsize=9,
        )
    fig.suptitle("Predicted price by category (ranked)", fontsize=12)
    wrapped_frozen = "\n".join(textwrap.wrap(frozen_description, width=55))
    ax.set_title(wrapped_frozen, fontsize=9, color="gray")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def run_sweep_check(
    model,
    base_row: pd.Series,
    feature: str,
    values,
    x_labels,
    direction: str,
    xlabel: str,
    plot_title: str,
    out_path: Path,
) -> bool:
    frozen = describe_frozen_row(base_row, feature)
    print(f"  {frozen}")
    predictions = sweep(model, base_row, feature, values)
    passed, violation_frac = check_monotonic(predictions, direction)
    plot_sweep(
        x_labels,
        predictions,
        xlabel,
        f"{plot_title} ({'PASS' if passed else 'FAIL'}, {violation_frac:.1%} adjacent-step violations)",
        frozen,
        out_path,
    )
    print(
        f"  {'PASS' if passed else 'FAIL'} -- "
        f"{violation_frac:.1%} adjacent-step violations (tolerance {VIOLATION_TOLERANCE:.0%})"
    )
    return passed


def main() -> None:
    args = parse_args()
    args.plots_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.data)
    X = fs.build_features(df)
    model = joblib.load(args.model)

    print("[1/9] SHAP summary plot")
    explainer = shap.TreeExplainer(model)
    plot_summary(explainer, X, args.plots_dir / "shap_summary.png")

    base_row = representative_row(X)

    print("[2/9] Duration check (holding category/condition/capacity/distance_km/period_utilization/lead_time_days fixed)")
    durations = np.linspace(df["duration_days"].min(), df["duration_days"].max(), 30).round().astype(int)
    duration_passed = run_sweep_check(
        model, base_row, "duration_days", durations, durations, "decreasing",
        "duration_days", "Predicted price vs duration", args.plots_dir / "shap_duration_check.png",
    )

    print("[3/9] Condition check (holding category/duration_days/capacity/distance_km/period_utilization/lead_time_days fixed)")
    condition_levels = np.array(sorted(fs.CONDITION_ORDER.values()))
    condition_labels = [k for k, v in sorted(fs.CONDITION_ORDER.items(), key=lambda kv: kv[1])]
    condition_passed = run_sweep_check(
        model, base_row, "condition_ordinal", condition_levels, condition_labels, "increasing",
        "condition", "Predicted price vs condition", args.plots_dir / "shap_condition_check.png",
    )

    print("[4/9] Capacity check (holding category/condition/duration_days/distance_km/period_utilization/lead_time_days fixed)")
    category_capacity = df.loc[df["category"] == active_category(base_row), "capacity"]
    capacities = np.linspace(category_capacity.min(), category_capacity.max(), 30)
    capacity_passed = run_sweep_check(
        model, base_row, "capacity", capacities, capacities, "increasing",
        "capacity (kg)", "Predicted price vs capacity", args.plots_dir / "shap_capacity_check.png",
    )

    print("[5/9] Distance check (holding category/condition/duration_days/capacity/period_utilization/lead_time_days fixed)")
    distances = np.linspace(df["distance_km"].min(), df["distance_km"].max(), 30)
    distance_passed = run_sweep_check(
        model, base_row, "distance_km", distances, distances, "increasing",
        "distance_km (km)", "Predicted price vs distance", args.plots_dir / "shap_distance_check.png",
    )

    print("[6/9] Period utilization check (holding category/condition/duration_days/capacity/distance_km/lead_time_days fixed)")
    utilizations = np.linspace(0, 1, 30)
    utilization_passed = run_sweep_check(
        model, base_row, "period_utilization", utilizations, utilizations, "increasing",
        "period_utilization", "Predicted price vs period utilization",
        args.plots_dir / "shap_period_utilization_check.png",
    )

    print("[7/9] Lead time check (holding category/condition/duration_days/capacity/distance_km/period_utilization fixed)")
    lead_times = np.linspace(df["lead_time_days"].min(), df["lead_time_days"].max(), 30)
    lead_time_passed = run_sweep_check(
        model, base_row, "lead_time_days", lead_times, lead_times, "decreasing",
        "lead_time_days (days)", "Predicted price vs lead time",
        args.plots_dir / "shap_lead_time_check.png",
    )

    print("[8/9] Platform height check (holding category/condition/duration_days/capacity/distance_km/period_utilization/lead_time_days fixed)")
    aerial_category = mode_aerial_category(X)
    platform_base_row = representative_row(X, category=aerial_category)
    category_platform_height = df.loc[df["category"] == aerial_category, "platform_height"]
    platform_heights = np.linspace(category_platform_height.min(), category_platform_height.max(), 30)
    platform_height_passed = run_sweep_check(
        model, platform_base_row, "platform_height", platform_heights, platform_heights, "increasing",
        "platform_height (m)", "Predicted price vs platform height",
        args.plots_dir / "shap_platform_height_check.png",
    )

    print("[9/9] Category ranking (shared condition/duration_days/distance_km, each category's own capacity/platform_height)")
    ranking = category_ranking(model, X)
    print(ranking.to_string(index=False))
    condition_name_by_ordinal = {v: k for k, v in fs.CONDITION_ORDER.items()}
    ranking_frozen = (
        f"frozen: condition={condition_name_by_ordinal[int(base_row['condition_ordinal'])]}, "
        f"duration_days={base_row['duration_days']:g}, distance_km={base_row['distance_km']:g}km "
        "(capacity/platform_height at each category's own typical value)"
    )
    plot_category_ranking(ranking, ranking_frozen, args.plots_dir / "shap_category_ranking.png")

    print(f"\nPlots saved to {args.plots_dir}")

    all_passed = (
        duration_passed
        and condition_passed
        and capacity_passed
        and distance_passed
        and utilization_passed
        and lead_time_passed
        and platform_height_passed
    )
    if args.strict and not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
