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

Both checks tolerate a small fraction of adjacent-step violations (XGBoost
trees aren't constrained to be monotonic) rather than requiring a perfectly
monotonic sweep.
"""

import argparse
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
        help="Exit non-zero if the duration or condition monotonicity checks fail.",
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
    return row


def sweep(model, base_row: pd.Series, feature: str, values) -> np.ndarray:
    rows = pd.DataFrame([base_row] * len(values)).reset_index(drop=True)
    rows[feature] = values
    return model.predict(rows[fs.FEATURE_COLUMNS])


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


def plot_sweep(x_values, y_values, xlabel: str, title: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(x_values, y_values, marker="o")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Predicted price_per_day")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    args.plots_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.data)
    X = fs.build_features(df)
    model = joblib.load(args.model)

    print("[1/3] SHAP summary plot")
    explainer = shap.TreeExplainer(model)
    plot_summary(explainer, X, args.plots_dir / "shap_summary.png")

    print("[2/3] Duration check (holding category/condition/capacity/distance_km fixed)")
    base_row = representative_row(X)
    durations = np.linspace(df["duration_days"].min(), df["duration_days"].max(), 30).round().astype(int)
    duration_predictions = sweep(model, base_row, "duration_days", durations)
    duration_passed, duration_violation_frac = check_monotonic(duration_predictions, "decreasing")
    plot_sweep(
        durations,
        duration_predictions,
        "duration_days",
        f"Predicted price vs duration ({'PASS' if duration_passed else 'FAIL'}, "
        f"{duration_violation_frac:.1%} adjacent-step violations)",
        args.plots_dir / "shap_duration_check.png",
    )
    print(
        f"  {'PASS' if duration_passed else 'FAIL'} -- "
        f"{duration_violation_frac:.1%} adjacent-step violations (tolerance {VIOLATION_TOLERANCE:.0%})"
    )

    print("[3/3] Condition check (holding category/duration_days/capacity/distance_km fixed)")
    condition_levels = np.array(sorted(fs.CONDITION_ORDER.values()))
    condition_predictions = sweep(model, base_row, "condition_ordinal", condition_levels)
    condition_passed, condition_violation_frac = check_monotonic(condition_predictions, "increasing")
    condition_labels = [k for k, v in sorted(fs.CONDITION_ORDER.items(), key=lambda kv: kv[1])]
    plot_sweep(
        condition_labels,
        condition_predictions,
        "condition",
        f"Predicted price vs condition ({'PASS' if condition_passed else 'FAIL'}, "
        f"{condition_violation_frac:.1%} adjacent-step violations)",
        args.plots_dir / "shap_condition_check.png",
    )
    print(
        f"  {'PASS' if condition_passed else 'FAIL'} -- "
        f"{condition_violation_frac:.1%} adjacent-step violations (tolerance {VIOLATION_TOLERANCE:.0%})"
    )

    print(f"\nPlots saved to {args.plots_dir}")

    if args.strict and not (duration_passed and condition_passed):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
