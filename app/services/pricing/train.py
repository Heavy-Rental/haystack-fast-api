"""Train the production pricing model (Phase 2a + Phase 3b).

Ported from ``ml-experiments/train.py`` and adapted to this package’s feature
schema and artifact paths. The default CLI/legacy ``retrain()`` helper still
reads ``ml-experiments/data/synthetic_pricing_data.csv``; no HTTP retrain route
exists. Phase 3b additionally lets scheduled-job callers pass an in-memory
real/synthetic dataset and aligned sample weights without changing existing
callers. Serving only needs the committed ``artifacts/model.pkl`` and
``current.json``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

from app.services.pricing import feature_schema as fs

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = (
    PACKAGE_DIR.parents[2] / "ml-experiments" / "data" / "synthetic_pricing_data.csv"
)
DEFAULT_MODEL_PATH = PACKAGE_DIR / "artifacts" / "model.pkl"
DEFAULT_META_PATH = PACKAGE_DIR / "artifacts" / "current.json"

XGB_PARAMS = {
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "reg:squarederror",
}


def train(
    *,
    data: pd.DataFrame | None = None,
    sample_weight: np.ndarray | None = None,
    data_path: Path = DEFAULT_DATA_PATH,
    seed: int = 42,
    test_size: float = 0.2,
    model_out: Path = DEFAULT_MODEL_PATH,
    meta_out: Path = DEFAULT_META_PATH,
) -> dict[str, Any]:
    """Train, evaluate, and persist the model + metadata. Returns the metrics dict."""
    df = data.copy(deep=True) if data is not None else pd.read_csv(data_path)
    X = fs.build_features(df)
    y = fs.get_target(df)

    training_weight: np.ndarray | None = None
    if sample_weight is None:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=seed
        )
    else:
        weights = np.asarray(sample_weight, dtype=float)
        if weights.ndim != 1 or len(weights) != len(df):
            raise ValueError(
                f"sample_weight length must match data rows ({len(df)}); got shape {weights.shape}"
            )
        if not np.isfinite(weights).all() or (weights < 0).any():
            raise ValueError("sample_weight values must be finite and non-negative")
        X_train, X_test, y_train, y_test, training_weight, _ = train_test_split(
            X,
            y,
            weights,
            test_size=test_size,
            random_state=seed,
        )

    model = XGBRegressor(random_state=seed, **XGB_PARAMS)
    if training_weight is None:
        model.fit(X_train, y_train)
    else:
        model.fit(X_train, y_train, sample_weight=training_weight)

    predictions = model.predict(X_test)
    metrics = {
        "mae": float(mean_absolute_error(y_test, predictions)),
        "rmse": float(mean_squared_error(y_test, predictions) ** 0.5),
        "r2": float(r2_score(y_test, predictions)),
    }

    model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_out)

    meta = {
        "trained_at": dt.datetime.now(dt.UTC).isoformat(),
        "feature_columns": fs.FEATURE_COLUMNS,
        "condition_order": fs.CONDITION_ORDER,
        "categories": fs.CATEGORIES,
        "target_column": fs.TARGET_COLUMN,
        "hyperparameters": {**XGB_PARAMS, "random_state": seed},
        "metrics": metrics,
        "row_counts": {"train": len(X_train), "test": len(X_test), "total": len(df)},
        "data_source": "in-memory" if data is not None else str(data_path),
    }
    meta_out.parent.mkdir(parents=True, exist_ok=True)
    meta_out.write_text(json.dumps(meta, indent=2) + "\n")

    return metrics


def retrain() -> dict[str, Any]:
    """Legacy in-process dev helper for default-path retraining.

    No HTTP retrain route exists; scheduled retraining uses ``train()`` with
    explicit candidate paths in Phase 3c.
    """
    metrics = train()
    from app.services.pricing.model import reload_model

    reload_model()
    return metrics


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--meta-out", type=Path, default=DEFAULT_META_PATH)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    metrics = train(
        data_path=args.data,
        seed=args.seed,
        test_size=args.test_size,
        model_out=args.model_out,
        meta_out=args.meta_out,
    )
    print("Holdout metrics:")
    for name, value in metrics.items():
        print(f"  {name.upper()}: {value:.4f}")
    print(f"\nSaved model to {args.model_out}")
    print(f"Saved metadata to {args.meta_out}")


if __name__ == "__main__":
    main()
