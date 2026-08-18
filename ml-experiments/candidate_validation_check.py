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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.db import SessionLocal
from app.services.pricing import feature_schema as fs
from app.services.pricing import promotion_gate as _promotion_gate
from app.services.pricing.promotion_gate import (
    DEFAULT_DISTANCE_KM,
    DURATIONS,
    MAX_CANDIDATE_CLAMP_RATE,
    GateDecision,
    PredictModel,
    build_validation_rows,
    evaluate_common_holdout,
    evaluate_model,
    load_live_assets,
    summarize_predictions,
    validate_artifact_contract,
    validate_model_features,
)
from app.services.pricing.read_resilience import (
    PricingSchemaResolution,
    resolve_pricing_schema,
)

ARTIFACTS_DIR = REPO_ROOT / "app" / "services" / "pricing" / "artifacts"
DEFAULT_CURRENT_MODEL = ARTIFACTS_DIR / "model.pkl"
DEFAULT_CURRENT_META = ARTIFACTS_DIR / "current.json"
DEFAULT_CANDIDATE_MODEL = ARTIFACTS_DIR / "model_v2.pkl"
DEFAULT_CANDIDATE_META = ARTIFACTS_DIR / "current_v2.json"
DEFAULT_CANDIDATE_DATA = SCRIPT_DIR / "data" / "phase2d" / "synthetic_pricing_data_v2.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "outputs" / "phase2d" / "candidate_validation_check.png"
EXPECTED_CANDIDATE_DATA_SHA256 = "3b2b79d28f42fe62e2971f48b055af0cabecadc3b5fb0b7463a58929766e2d05"

REALISTIC_DURATIONS = _promotion_gate.REALISTIC_DURATIONS

EXPECTED_ASSET_COUNT = 27


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
    expected_asset_count: int | None = EXPECTED_ASSET_COUNT,
    min_asset_count: int = 1,
) -> GateDecision:
    return _promotion_gate.assess_gate(
        summary,
        accuracy,
        actual_asset_count=actual_asset_count,
        expected_asset_count=expected_asset_count,
        min_asset_count=min_asset_count,
    )


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
    categories = [
        category for category in fs.CATEGORIES if category in set(predictions["category"])
    ]
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
    print(f"Candidate data: {candidate_data} (sha256={accuracy.attrs['data_sha256']})")
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
