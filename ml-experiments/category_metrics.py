"""Per-category MAE/R^2 breakdown of the pricing model (Phase 1b, dynamic-pricing feature).

Scratch/offline script -- lives outside the app's SDD structure per
docs/dynamic-pricing-masterplan.md, same convention as generate_synthetic_data.py.

Motivated by the Phase 1b baseline SHAP review: overall holdout metrics looked
fine, but per-category breakdown revealed boom lift/scissor lift fitting far
worse than forklift/excavator (missing platform_height signal, since fixed --
see feature_schema.py's docstring). Kept as a standing check so a future
feature/data change that regresses one category doesn't hide behind a healthy
overall average.

Uses the same train/test split parameters as train.py (--seed/--test-size) so
the reported metrics reflect the same holdout set the saved model was
evaluated against, not train-set performance.
"""

import argparse
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

import feature_schema as fs

SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=SCRIPT_DIR / "data" / "synthetic_pricing_data.csv")
    parser.add_argument("--model", type=Path, default=SCRIPT_DIR / "artifacts" / "model.pkl")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--out", type=Path, default=SCRIPT_DIR / "outputs" / "category_metrics.png")
    return parser.parse_args()


def compute_per_category_metrics(df: pd.DataFrame, model, seed: int, test_size: float) -> pd.DataFrame:
    X = fs.build_features(df)
    y = fs.get_target(df)
    _, X_test, _, y_test, _, df_test = train_test_split(
        X, y, df, test_size=test_size, random_state=seed
    )

    predictions = model.predict(X_test)
    results = df_test.assign(actual=y_test.values, pred=predictions)

    def summarize(group: pd.DataFrame) -> pd.Series:
        mae = mean_absolute_error(group["actual"], group["pred"])
        return pd.Series(
            {
                "n": len(group),
                "mae": mae,
                "r2": r2_score(group["actual"], group["pred"]),
                "mean_actual": group["actual"].mean(),
                "mae_pct_of_mean": mae / group["actual"].mean() * 100,
            }
        )

    per_category = results.groupby("category", sort=False).apply(summarize, include_groups=False)
    overall = summarize(results).rename("ALL (overall)")
    return pd.concat([per_category, overall.to_frame().T])


def render_table_png(summary: pd.DataFrame, out_path: Path) -> None:
    display = summary.reset_index().rename(columns={"index": "category"})
    display.columns = [
        {"n": "n", "mae": "MAE", "r2": "R2", "mean_actual": "mean price", "mae_pct_of_mean": "MAE % of mean"}.get(
            c, c
        )
        for c in display.columns
    ]

    cell_text = []
    for row in display.itertuples(index=False):
        cell_text.append(
            [
                row[0],
                f"{int(row[1])}",
                f"{row[2]:.2f}",
                f"{row[3]:.3f}",
                f"{row[4]:.2f}",
                f"{row[5]:.1f}%",
            ]
        )

    fig, ax = plt.subplots(figsize=(8, 0.45 * (len(display) + 1)))
    ax.axis("off")
    table = ax.table(
        cellText=cell_text,
        colLabels=list(display.columns),
        cellLoc="center",
        bbox=[0, 0, 1, 1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)

    # Bold the overall-summary row so it reads distinctly from per-category rows.
    overall_row_idx = len(display)
    for col in range(len(display.columns)):
        table[overall_row_idx, col].set_text_props(fontweight="bold")

    ax.set_title("Per-category holdout metrics", fontsize=12, pad=10)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.data)
    model = joblib.load(args.model)

    summary = compute_per_category_metrics(df, model, args.seed, args.test_size)
    print(summary.round(3))

    render_table_png(summary, args.out)
    print(f"\nSaved table to {args.out}")


if __name__ == "__main__":
    main()
