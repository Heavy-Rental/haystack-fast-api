"""Compare the Phase 2d candidate with the current production pricing model.

Phase 2d-iii is deliberately read-only.  This script loads ``model.pkl`` and
``model_v2.pkl`` directly, evaluates both models over identical feature rows
for every live asset at 1/7/14/30 days, and evaluates both models over the
same deterministic v2 holdout.  It never imports the serving model loader,
calls ``reload_model()``, writes the database, or changes an artifact.

Run from the repository root::

    uv run python ml-experiments/candidate_validation_check.py

The summary and Phase 2e gate are printed to stdout.  The comparison chart is
written under ``ml-experiments/outputs/phase2d/`` by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sqlalchemy import select
from sqlalchemy.orm import Session

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.db import SessionLocal
from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.services.pricing import feature_schema as fs
from app.services.pricing import pricing_tables as pt
from app.services.pricing.category_mapping import to_feature_name
from app.services.pricing.read_resilience import (
    PricingSchemaResolution,
    resolve_pricing_schema,
)
from app.services.pricing.repository import resolve_effective_capacity

ARTIFACTS_DIR = REPO_ROOT / "app" / "services" / "pricing" / "artifacts"
DEFAULT_CURRENT_MODEL = ARTIFACTS_DIR / "model.pkl"
DEFAULT_CURRENT_META = ARTIFACTS_DIR / "current.json"
DEFAULT_CANDIDATE_MODEL = ARTIFACTS_DIR / "model_v2.pkl"
DEFAULT_CANDIDATE_META = ARTIFACTS_DIR / "current_v2.json"
DEFAULT_CANDIDATE_DATA = SCRIPT_DIR / "data" / "phase2d" / "synthetic_pricing_data_v2.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "outputs" / "phase2d" / "candidate_validation_check.png"
EXPECTED_CANDIDATE_DATA_SHA256 = (
    "3b2b79d28f42fe62e2971f48b055af0cabecadc3b5fb0b7463a58929766e2d05"
)

DURATIONS = (1, 7, 14, 30)
REALISTIC_DURATIONS = (7, 14)
EXPECTED_ASSET_COUNT = 27
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_metadata(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


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
    """Score every model on the exact v2 holdout used by the trainer."""
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


def validate_candidate_data_provenance(
    accuracy: pd.DataFrame,
    candidate_metadata: Mapping[str, Any],
) -> None:
    """Prove the ignored v2 CSV matches the tracked candidate artifact."""
    expected_counts = candidate_metadata.get("row_counts") or {}
    observed_counts = {
        "total": accuracy.attrs.get("total_rows"),
        "test": accuracy.attrs.get("test_rows"),
    }
    count_mismatches = [
        name for name, observed in observed_counts.items() if observed != expected_counts.get(name)
    ]
    observed_hash = accuracy.attrs.get("data_sha256")
    if observed_hash != EXPECTED_CANDIDATE_DATA_SHA256:
        count_mismatches.append("sha256")

    candidate = accuracy.set_index("model").loc["candidate"]
    expected_metrics = candidate_metadata.get("metrics") or {}
    metric_mismatches = [
        name
        for name in ("mae", "rmse", "r2")
        if name not in expected_metrics
        or not np.isclose(
            float(candidate[name]),
            float(expected_metrics[name]),
            rtol=1e-7,
            atol=1e-7,
        )
    ]
    mismatches = count_mismatches + metric_mismatches
    if mismatches:
        raise ValueError(
            "Candidate dataset/model provenance mismatch for: "
            f"{sorted(set(mismatches))}. Regenerate the Phase 2d v2 CSV with seed 42."
        )


def assess_gate(
    summary: pd.DataFrame,
    accuracy: pd.DataFrame,
    *,
    actual_asset_count: int,
    expected_asset_count: int = EXPECTED_ASSET_COUNT,
) -> GateDecision:
    checks: dict[str, bool] = {
        "asset_count": actual_asset_count == expected_asset_count,
    }
    details = [f"asset count: {actual_asset_count}/{expected_asset_count}"]

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
    details.append(
        f"common holdout MAE: current={current_mae:.4f}, candidate={candidate_mae:.4f}"
    )
    details.append(f"common holdout R²: current={current_r2:.4f}, candidate={candidate_r2:.4f}")

    return GateDecision(passed=all(checks.values()), checks=checks, details=tuple(details))


def render_chart(predictions: pd.DataFrame, summary: pd.DataFrame, out_path: Path) -> None:
    durations = [float(value) for value in DURATIONS]
    positions = np.arange(len(durations))
    width = 0.36
    fig, (overall_ax, category_ax) = plt.subplots(2, 1, figsize=(11, 9))

    indexed = summary.set_index(["model", "duration_days"])
    for offset, label in ((-width / 2, "current"), (width / 2, "candidate")):
        rates = [float(indexed.loc[(label, duration), "clamp_rate"]) for duration in durations]
        overall_ax.bar(positions + offset, np.array(rates) * 100, width, label=label.title())
    overall_ax.axhline(
        MAX_CANDIDATE_CLAMP_RATE * 100,
        color="tab:red",
        linestyle="--",
        linewidth=1,
        label="Candidate ceiling",
    )
    overall_ax.set_xticks(positions, [f"{int(duration)}d" for duration in durations])
    overall_ax.set_ylabel("Assets clamped (%)")
    overall_ax.set_ylim(0, 105)
    overall_ax.set_title("Current vs candidate clamp rate across all live assets")
    overall_ax.grid(axis="y", alpha=0.25)
    overall_ax.legend(ncols=3)

    by_category = (
        predictions.groupby(["model", "category", "duration_days"])["was_clamped"]
        .mean()
        .rename("clamp_rate")
    )
    categories = [category for category in fs.CATEGORIES if category in set(predictions["category"])]
    reductions = np.array(
        [
            [
                float(by_category.loc[("current", category, duration)])
                - float(by_category.loc[("candidate", category, duration)])
                for duration in durations
            ]
            for category in categories
        ]
    )
    image = category_ax.imshow(reductions * 100, cmap="RdYlGn", vmin=-100, vmax=100, aspect="auto")
    category_ax.set_xticks(positions, [f"{int(duration)}d" for duration in durations])
    category_ax.set_yticks(np.arange(len(categories)), categories)
    category_ax.set_title("Clamp-rate reduction by category (percentage points; green is better)")
    for row_index in range(len(categories)):
        for column_index in range(len(durations)):
            category_ax.text(
                column_index,
                row_index,
                f"{reductions[row_index, column_index] * 100:+.0f}",
                ha="center",
                va="center",
                color="black",
            )
    fig.colorbar(image, ax=category_ax, label="Current − candidate (percentage points)")

    fig.suptitle(f"Phase 2d-iii candidate validation ({predictions['asset_id'].nunique()} assets)")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _print_results(
    *,
    resolution: PricingSchemaResolution,
    assets: pd.DataFrame,
    summary: pd.DataFrame,
    accuracy: pd.DataFrame,
    decision: GateDecision,
    output: Path,
    candidate_data: Path,
) -> None:
    printable = summary.copy()
    printable["clamp_rate_%"] = printable["clamp_rate"] * 100
    printable = printable.drop(columns="clamp_rate")
    print(
        f"Pricing schema: {resolution.schema} (degraded={resolution.degraded}); "
        f"assets evaluated: {len(assets)}"
    )
    print(
        f"Formal artifacts: current={DEFAULT_CURRENT_MODEL.name}/{DEFAULT_CURRENT_META.name}, "
        f"candidate={DEFAULT_CANDIDATE_MODEL.name}/{DEFAULT_CANDIDATE_META.name}"
    )
    print(
        "Formal gate inputs: durations=1/7/14/30d, distance_km=20.0, "
        "period_utilization=production category fallback, lead_time_days=0.0"
    )
    print(
        f"Candidate data: {candidate_data} "
        f"(sha256={accuracy.attrs['data_sha256']})"
    )
    print("\nClamp comparison:")
    print(printable.round(2).to_string(index=False))
    print("\nCommon v2 holdout metrics:")
    print(accuracy.round(4).to_string(index=False))
    print("\nPhase 2e gate checks:")
    for name, passed in decision.checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    for detail in decision.details:
        print(f"  {detail}")
    print(f"\nPHASE 2E GATE: {'PASS' if decision.passed else 'FAIL'}")
    print("No artifacts were promoted or reloaded.")
    print(f"Saved comparison chart to {output}")


def main() -> None:
    parse_args()
    artifact_paths = (
        DEFAULT_CURRENT_MODEL,
        DEFAULT_CURRENT_META,
        DEFAULT_CANDIDATE_MODEL,
        DEFAULT_CANDIDATE_META,
    )
    before_hashes = {path: _sha256(path) for path in artifact_paths}

    current_meta = load_metadata(DEFAULT_CURRENT_META)
    candidate_meta = load_metadata(DEFAULT_CANDIDATE_META)
    validate_artifact_contract(current_meta, label="current")
    validate_artifact_contract(candidate_meta, label="candidate")

    models: dict[str, PredictModel] = {
        "current": joblib.load(DEFAULT_CURRENT_MODEL),
        "candidate": joblib.load(DEFAULT_CANDIDATE_MODEL),
    }
    for label, model in models.items():
        validate_model_features(model, label=label)

    with SessionLocal() as session:
        resolution = resolve_pricing_schema(session)
        assets = load_live_assets(session, resolution)

    rows = build_validation_rows(assets, distance_km=DEFAULT_DISTANCE_KM)
    predictions = pd.concat(
        [evaluate_model(label, model, rows) for label, model in models.items()],
        ignore_index=True,
    )
    summary = summarize_predictions(predictions)
    accuracy = evaluate_common_holdout(models, DEFAULT_CANDIDATE_DATA)
    validate_candidate_data_provenance(accuracy, candidate_meta)
    decision = assess_gate(
        summary,
        accuracy,
        actual_asset_count=len(assets),
        expected_asset_count=EXPECTED_ASSET_COUNT,
    )
    render_chart(predictions, summary, DEFAULT_OUTPUT)

    after_hashes = {path: _sha256(path) for path in artifact_paths}
    if after_hashes != before_hashes:
        raise RuntimeError("An artifact changed during read-only candidate validation")

    _print_results(
        resolution=resolution,
        assets=assets,
        summary=summary,
        accuracy=accuracy,
        decision=decision,
        output=DEFAULT_OUTPUT,
        candidate_data=DEFAULT_CANDIDATE_DATA,
    )


if __name__ == "__main__":
    main()
