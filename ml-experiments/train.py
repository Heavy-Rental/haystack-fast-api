"""Train the baseline/final XGBoost pricing model (Phase 1b, dynamic-pricing feature).

Scratch/offline script -- lives outside the app's SDD structure per
docs/dynamic-pricing-masterplan.md, same convention as generate_synthetic_data.py.

Run twice per the execution plan's Day 2-3 workflow:
1. Once to produce the baseline model that shap_review.py inspects.
2. Again after feature_schema.py is finalized based on the SHAP findings, to
   produce the final model + artifacts.
"""

import argparse
import datetime as dt
import json
from pathlib import Path

import feature_schema as fs
import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

SCRIPT_DIR = Path(__file__).resolve().parent

XGB_PARAMS = {
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "reg:squarederror",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=SCRIPT_DIR / "data" / "synthetic_pricing_data.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--model-out", type=Path, default=SCRIPT_DIR / "artifacts" / "model.pkl")
    parser.add_argument("--meta-out", type=Path, default=SCRIPT_DIR / "artifacts" / "current.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.data)
    X = fs.build_features(df)
    y = fs.get_target(df)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.seed
    )

    model = XGBRegressor(random_state=args.seed, **XGB_PARAMS)
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    metrics = {
        "mae": float(mean_absolute_error(y_test, predictions)),
        "rmse": float(mean_squared_error(y_test, predictions) ** 0.5),
        "r2": float(r2_score(y_test, predictions)),
    }

    print("Holdout metrics:")
    for name, value in metrics.items():
        print(f"  {name.upper()}: {value:.4f}")

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.model_out)

    meta = {
        "trained_at": dt.datetime.now(dt.UTC).isoformat(),
        "feature_columns": fs.FEATURE_COLUMNS,
        "condition_order": fs.CONDITION_ORDER,
        "categories": fs.CATEGORIES,
        "target_column": fs.TARGET_COLUMN,
        "hyperparameters": {**XGB_PARAMS, "random_state": args.seed},
        "metrics": metrics,
        "row_counts": {"train": len(X_train), "test": len(X_test), "total": len(df)},
        "data_source": str(args.data.relative_to(SCRIPT_DIR)),
    }
    args.meta_out.parent.mkdir(parents=True, exist_ok=True)
    args.meta_out.write_text(json.dumps(meta, indent=2) + "\n")

    print(f"\nSaved model to {args.model_out}")
    print(f"Saved metadata to {args.meta_out}")


if __name__ == "__main__":
    main()
