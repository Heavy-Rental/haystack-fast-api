"""Reusable validation gate for dynamic-pricing model promotion.

The gate compares a candidate with the currently serving model on identical
live-asset rows and on a common deterministic holdout.  It is deliberately
free of artifact promotion and serving-model reload concerns so both the
historical Phase 2d validation script and the scheduled retrain job can use it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.services.pricing import feature_schema as fs
from app.services.pricing import pricing_tables as pt
from app.services.pricing.category_mapping import to_feature_name
from app.services.pricing.read_resilience import PricingSchemaResolution
from app.services.pricing.repository import resolve_effective_capacity

DURATIONS = (1, 7, 14, 30)
REALISTIC_DURATIONS = (7, 14)
DEFAULT_DISTANCE_KM = 20.0

MIN_CLAMP_REDUCTION = 0.20
MAX_CANDIDATE_CLAMP_RATE = 0.50
MAX_MAE_REGRESSION = 0.05
MAX_R2_REGRESSION = 0.01


class PredictModel(Protocol):
    def predict(self, features: pd.DataFrame) -> Any:
        """Return model predictions for the feature frame."""


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    checks: Mapping[str, bool]
    details: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifact_contract(metadata: Mapping[str, Any], *, label: str) -> None:
    expected = {
        "feature_columns": fs.FEATURE_COLUMNS,
        "condition_order": fs.CONDITION_ORDER,
        "categories": fs.CATEGORIES,
        "target_column": fs.TARGET_COLUMN,
    }
    mismatches = [
        key for key, expected_value in expected.items() if metadata.get(key) != expected_value
    ]
    if mismatches:
        raise ValueError(f"{label} metadata is incompatible with production schema: {mismatches}")


def validate_model_features(model: PredictModel, *, label: str) -> None:
    names = getattr(model, "feature_names_in_", None)
    if names is not None and list(names) != fs.FEATURE_COLUMNS:
        raise ValueError(f"{label} model feature names do not match production feature schema")


def load_live_assets(session: Session, resolution: PricingSchemaResolution) -> pd.DataFrame:
    """Read the pricing attributes for every live Spring-owned asset."""
    statement = (
        select(
            Asset.id,
            Asset.name,
            AssetCategory.name,
            Asset.condition,
            Asset.capacity,
            Asset.platform_height,
            Asset.min_daily_rate,
            Asset.max_daily_rate,
        )
        .join(AssetCategory, Asset.category_id == AssetCategory.id)
        .order_by(AssetCategory.name, Asset.id)
    )
    rows = session.execute(statement, execution_options=resolution.execution_options).all()
    records = [
        {
            "asset_id": int(asset_id),
            "asset_name": asset_name,
            "category": to_feature_name(db_category),
            "condition": condition,
            "capacity": float(capacity) if capacity is not None else None,
            "platform_height": float(platform_height) if platform_height is not None else None,
            "min_daily_rate": float(min_daily_rate),
            "max_daily_rate": float(max_daily_rate),
        }
        for (
            asset_id,
            asset_name,
            db_category,
            condition,
            capacity,
            platform_height,
            min_daily_rate,
            max_daily_rate,
        ) in rows
    ]
    if not records:
        raise RuntimeError(f"No assets found in pricing schema {resolution.schema!r}")
    return pd.DataFrame.from_records(records)


def build_validation_rows(
    assets: pd.DataFrame,
    *,
    durations: Sequence[int] = DURATIONS,
    distance_km: float = DEFAULT_DISTANCE_KM,
) -> pd.DataFrame:
    """Cross live assets with durations using production fallback semantics."""
    records: list[dict[str, Any]] = []
    for asset in assets.to_dict(orient="records"):
        category = str(asset["category"])
        if category not in fs.CATEGORIES:
            raise ValueError(f"Unrecognized feature category {category!r}")
        min_rate = float(asset["min_daily_rate"])
        max_rate = float(asset["max_daily_rate"])
        if not np.isfinite([min_rate, max_rate]).all() or min_rate > max_rate:
            raise ValueError(f"Asset {asset['asset_id']} has invalid daily-rate guardrails")

        raw_capacity = asset.get("capacity")
        capacity = resolve_effective_capacity(
            category, None if pd.isna(raw_capacity) else float(raw_capacity)
        )
        platform_height = asset.get("platform_height")
        condition = asset.get("condition")
        for duration in durations:
            records.append(
                {
                    **asset,
                    "condition": "GOOD" if pd.isna(condition) else condition,
                    "duration_days": max(1.0, float(duration)),
                    "capacity": capacity,
                    "distance_km": float(distance_km),
                    "platform_height": (
                        np.nan if platform_height is None else float(platform_height)
                    ),
                    "period_utilization": float(pt.CATEGORY_UTILIZATION.get(category, 0.0)),
                    "lead_time_days": 0.0,
                }
            )
    if not records:
        raise ValueError("At least one live asset is required")
    return pd.DataFrame.from_records(records)


def evaluate_model(label: str, model: PredictModel, rows: pd.DataFrame) -> pd.DataFrame:
    """Predict and apply the exact production guardrail clamp formula."""
    features = fs.build_features(rows)
    raw = np.asarray(model.predict(features), dtype=float)
    if not np.isfinite(raw).all():
        raise ValueError(f"{label} returned non-finite predictions")
    if raw.shape != (len(rows),):
        raise ValueError(f"{label} returned prediction shape {raw.shape}; expected {(len(rows),)}")

    minimum = rows["min_daily_rate"].to_numpy(dtype=float)
    maximum = rows["max_daily_rate"].to_numpy(dtype=float)
    clamped = np.minimum(np.maximum(raw, minimum), maximum)

    result = rows[
        ["asset_id", "asset_name", "category", "duration_days", "min_daily_rate", "max_daily_rate"]
    ].copy()
    result["model"] = label
    result["raw_price"] = raw
    result["clamped_price"] = clamped
    result["clamp_direction"] = np.select(
        [raw < minimum, raw > maximum], ["below_min", "above_max"], default="none"
    )
    result["was_clamped"] = clamped != raw
    return result


def summarize_predictions(predictions: pd.DataFrame) -> pd.DataFrame:
    summary = (
        predictions.assign(
            below_min=predictions["clamp_direction"].eq("below_min"),
            above_max=predictions["clamp_direction"].eq("above_max"),
        )
        .groupby(["model", "duration_days"], sort=False)
        .agg(
            assets=("asset_id", "size"),
            clamped=("was_clamped", "sum"),
            below_min=("below_min", "sum"),
            above_max=("above_max", "sum"),
        )
        .reset_index()
    )
    summary["clamp_rate"] = summary["clamped"] / summary["assets"]
    return summary


def evaluate_common_holdout(
    models: Mapping[str, PredictModel],
    data_path: Path,
    *,
    seed: int = 42,
    test_size: float = 0.2,
) -> pd.DataFrame:
    """Score every model on the same deterministic training-data holdout."""
    if not data_path.is_file():
        raise FileNotFoundError(
            f"Candidate dataset not found: {data_path}. Regenerate it with: "
            "uv run python ml-experiments/generate_synthetic_data.py "
            "--output ml-experiments/data/phase2d/synthetic_pricing_data_v2.csv "
            "--plots-dir ml-experiments/outputs/phase2d --strict"
        )
    data = pd.read_csv(data_path)
    features = fs.build_features(data)
    target = fs.get_target(data)
    _, x_test, _, y_test = train_test_split(
        features, target, test_size=test_size, random_state=seed
    )

    rows: list[dict[str, float | str]] = []
    for label, model in models.items():
        predicted = np.asarray(model.predict(x_test), dtype=float)
        rows.append(
            {
                "model": label,
                "mae": float(mean_absolute_error(y_test, predicted)),
                "rmse": float(mean_squared_error(y_test, predicted) ** 0.5),
                "r2": float(r2_score(y_test, predicted)),
            }
        )
    result = pd.DataFrame.from_records(rows)
    result.attrs["total_rows"] = len(data)
    result.attrs["test_rows"] = len(y_test)
    result.attrs["data_sha256"] = _sha256(data_path)
    return result


def assess_gate(
    summary: pd.DataFrame,
    accuracy: pd.DataFrame,
    *,
    actual_asset_count: int,
    expected_asset_count: int | None = None,
    min_asset_count: int = 1,
) -> GateDecision:
    """Assess promotion using exact fleet-size or recurring-job floor mode."""
    if min_asset_count < 1:
        raise ValueError("min_asset_count must be at least 1")

    if expected_asset_count is None:
        asset_count_passed = actual_asset_count >= min_asset_count
        asset_count_detail = f"asset count: {actual_asset_count} (minimum {min_asset_count})"
    else:
        if expected_asset_count < 1:
            raise ValueError("expected_asset_count must be at least 1")
        asset_count_passed = actual_asset_count == expected_asset_count
        asset_count_detail = f"asset count: {actual_asset_count}/{expected_asset_count}"

    checks: dict[str, bool] = {"asset_count": asset_count_passed}
    details = [asset_count_detail]

    indexed_summary = summary.set_index(["model", "duration_days"])
    for duration in REALISTIC_DURATIONS:
        current_rate = float(indexed_summary.loc[("current", float(duration)), "clamp_rate"])
        candidate_rate = float(indexed_summary.loc[("candidate", float(duration)), "clamp_rate"])
        reduction = current_rate - candidate_rate
        checks[f"duration_{duration}_reduction"] = reduction >= MIN_CLAMP_REDUCTION
        checks[f"duration_{duration}_candidate_ceiling"] = (
            candidate_rate <= MAX_CANDIDATE_CLAMP_RATE
        )
        details.append(
            f"{duration}d clamp: current={current_rate:.1%}, candidate={candidate_rate:.1%}, "
            f"reduction={reduction:.1%}"
        )

    indexed_accuracy = accuracy.set_index("model")
    current_mae = float(indexed_accuracy.loc["current", "mae"])
    candidate_mae = float(indexed_accuracy.loc["candidate", "mae"])
    current_r2 = float(indexed_accuracy.loc["current", "r2"])
    candidate_r2 = float(indexed_accuracy.loc["candidate", "r2"])
    checks["common_holdout_mae"] = candidate_mae <= current_mae * (1 + MAX_MAE_REGRESSION)
    checks["common_holdout_r2"] = candidate_r2 >= current_r2 - MAX_R2_REGRESSION
    details.append(f"common holdout MAE: current={current_mae:.4f}, candidate={candidate_mae:.4f}")
    details.append(f"common holdout R²: current={current_r2:.4f}, candidate={candidate_r2:.4f}")

    return GateDecision(passed=all(checks.values()), checks=checks, details=tuple(details))
