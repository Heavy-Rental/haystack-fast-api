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

All four sweep checks tolerate a small fraction of adjacent-step violations
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
        help="Exit non-zero if any of the duration/condition/capacity/distance monotonicity checks fail.",
    )
    return parser.parse_args()


def representative_row(X: pd.DataFrame) -> pd.Series:
    """A single feature row at the dataset's typical values, used as the
    "hold everything else fixed" baseline for the duration/condition sweeps.
    """
    row = X.median(numeric_only=True)

    category_cols = [c for c in X.columns if c.startswith("category_")]
    mode_category = X[category_cols].sum().idxmax()
    for col in category_cols:
        row[col] = 1 if col == mode_category else 0

    row["condition_ordinal"] = int(round(row["condition_ordinal"]))

    if "platform_height" in row.index:
        # X.median(numeric_only=True) above skips NaNs dataset-wide, which would
        # otherwise hand a forklift/excavator baseline an aerial-lift height it
        # never has in training data. Recompute conditioned on the frozen
        # category so non-aerial baselines correctly stay NaN.
        row["platform_height"] = X.loc[X[mode_category] == 1, "platform_height"].median()

    return row


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

    print("[1/5] SHAP summary plot")
    explainer = shap.TreeExplainer(model)
    plot_summary(explainer, X, args.plots_dir / "shap_summary.png")

    base_row = representative_row(X)

    print("[2/5] Duration check (holding category/condition/capacity/distance_km fixed)")
    durations = np.linspace(df["duration_days"].min(), df["duration_days"].max(), 30).round().astype(int)
    duration_passed = run_sweep_check(
        model, base_row, "duration_days", durations, durations, "decreasing",
        "duration_days", "Predicted price vs duration", args.plots_dir / "shap_duration_check.png",
    )

    print("[3/5] Condition check (holding category/duration_days/capacity/distance_km fixed)")
    condition_levels = np.array(sorted(fs.CONDITION_ORDER.values()))
    condition_labels = [k for k, v in sorted(fs.CONDITION_ORDER.items(), key=lambda kv: kv[1])]
    condition_passed = run_sweep_check(
        model, base_row, "condition_ordinal", condition_levels, condition_labels, "increasing",
        "condition", "Predicted price vs condition", args.plots_dir / "shap_condition_check.png",
    )

    print("[4/5] Capacity check (holding category/condition/duration_days/distance_km fixed)")
    category_capacity = df.loc[df["category"] == active_category(base_row), "capacity"]
    capacities = np.linspace(category_capacity.min(), category_capacity.max(), 30)
    capacity_passed = run_sweep_check(
        model, base_row, "capacity", capacities, capacities, "increasing",
        "capacity (kg)", "Predicted price vs capacity", args.plots_dir / "shap_capacity_check.png",
    )

    print("[5/5] Distance check (holding category/condition/duration_days/capacity fixed)")
    distances = np.linspace(df["distance_km"].min(), df["distance_km"].max(), 30)
    distance_passed = run_sweep_check(
        model, base_row, "distance_km", distances, distances, "increasing",
        "distance_km (km)", "Predicted price vs distance", args.plots_dir / "shap_distance_check.png",
    )

    print(f"\nPlots saved to {args.plots_dir}")

    if args.strict and not (duration_passed and condition_passed and capacity_passed and distance_passed):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
