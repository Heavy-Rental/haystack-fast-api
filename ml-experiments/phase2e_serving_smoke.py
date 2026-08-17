"""Verify the promoted Phase 2e model through the production prediction path.

Unlike ``candidate_validation_check.py``, this script intentionally imports
and reloads ``app.services.pricing.model``. It reads the same 27 live assets
and fixed 1/7/14/30-day inputs used by the Phase 2d-iii gate, then calls
``predict_price()`` once per asset/window and confirms the promoted serving
path reproduces the validated candidate clamp counts.

Run from the repository root::

    uv run python ml-experiments/phase2e_serving_smoke.py
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import candidate_validation_check as validation

from app.core.db import SessionLocal
from app.services.pricing import feature_schema as fs
from app.services.pricing import model as pricing_model
from app.services.pricing.read_resilience import resolve_pricing_schema

ARTIFACTS_DIR = REPO_ROOT / "app" / "services" / "pricing" / "artifacts"
SERVING_MODEL = ARTIFACTS_DIR / "model.pkl"
SERVING_META = ARTIFACTS_DIR / "current.json"
ROLLBACK_MODEL = ARTIFACTS_DIR / "model_v1.pkl"
ROLLBACK_META = ARTIFACTS_DIR / "current_v1.json"
CANDIDATE_MODEL = ARTIFACTS_DIR / "model_v2.pkl"
CANDIDATE_META = ARTIFACTS_DIR / "current_v2.json"

EXPECTED_V1_MODEL_SHA256 = "7c8e8d98d6626fa6991c1e7648739700b0bcb60ee557881522311da6dbb0b0fe"
EXPECTED_V1_META_SHA256 = "4c4131c40a1919e468724da7b38e004b1d03a8b91f2011932e5c71b7ad15d0d9"
EXPECTED_MODEL_VERSION = "prod-2026-08-13"
EXPECTED_CLAMPED_BY_DURATION = {1: 3, 7: 7, 14: 8, 30: 8}
EXPECTED_EXCAVATOR_CLAMPED = {7: 3, 14: 4, 30: 4}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact_identities() -> None:
    """Prove v1 recovery and v2 serving identities before prediction."""
    if sha256(ROLLBACK_MODEL) != EXPECTED_V1_MODEL_SHA256:
        raise RuntimeError("model_v1.pkl does not match the pre-promotion serving model")
    if sha256(ROLLBACK_META) != EXPECTED_V1_META_SHA256:
        raise RuntimeError("current_v1.json does not match the pre-promotion metadata")
    if sha256(SERVING_MODEL) != sha256(CANDIDATE_MODEL):
        raise RuntimeError("serving model.pkl is not byte-identical to model_v2.pkl")
    if sha256(SERVING_META) != sha256(CANDIDATE_META):
        raise RuntimeError("serving current.json is not byte-identical to current_v2.json")

    metadata = json.loads(SERVING_META.read_text())
    validation.validate_artifact_contract(metadata, label="promoted serving")


def evaluate_serving_path(assets: pd.DataFrame) -> pd.DataFrame:
    """Call the real ``predict_price()`` for every supplied asset/window."""
    records: list[dict[str, object]] = []
    for asset in assets.to_dict(orient="records"):
        category = str(asset["category"])
        raw_condition = asset.get("condition")
        raw_capacity = asset.get("capacity")
        raw_height = asset.get("platform_height")
        for duration in validation.DURATIONS:
            result = pricing_model.predict_price(
                category=category,
                condition=None if pd.isna(raw_condition) else str(raw_condition),
                duration_days=duration,
                capacity=None if pd.isna(raw_capacity) else float(raw_capacity),
                distance_km=validation.DEFAULT_DISTANCE_KM,
                platform_height=None if pd.isna(raw_height) else float(raw_height),
                min_daily_rate=float(asset["min_daily_rate"]),
                max_daily_rate=float(asset["max_daily_rate"]),
            )
            if not math.isfinite(result.raw_price) or result.raw_price <= 0:
                raise RuntimeError(
                    f"Asset {asset['asset_id']} returned invalid raw price {result.raw_price}"
                )
            if not result.min_daily_rate <= result.clamped_price <= result.max_daily_rate:
                raise RuntimeError(f"Asset {asset['asset_id']} escaped its guardrails")
            if result.model_version != EXPECTED_MODEL_VERSION:
                raise RuntimeError(
                    f"Unexpected serving version {result.model_version!r}; "
                    f"expected {EXPECTED_MODEL_VERSION!r}"
                )
            records.append(
                {
                    "asset_id": int(asset["asset_id"]),
                    "category": category,
                    "duration_days": int(duration),
                    "raw_price": result.raw_price,
                    "clamped_price": result.clamped_price,
                    "was_clamped": result.was_clamped,
                    "model_version": result.model_version,
                }
            )

    results = pd.DataFrame.from_records(records)
    missing_categories = set(fs.CATEGORIES) - set(results["category"])
    if missing_categories:
        raise RuntimeError(f"Serving smoke is missing categories: {sorted(missing_categories)}")
    return results


def verify_live_results(results: pd.DataFrame, *, asset_count: int) -> None:
    if asset_count != validation.EXPECTED_ASSET_COUNT:
        raise RuntimeError(
            f"Expected {validation.EXPECTED_ASSET_COUNT} live assets, found {asset_count}"
        )

    clamped = results.groupby("duration_days")["was_clamped"].sum().astype(int).to_dict()
    if clamped != EXPECTED_CLAMPED_BY_DURATION:
        raise RuntimeError(
            f"Promoted serving clamp counts {clamped} do not reproduce the validated candidate "
            f"counts {EXPECTED_CLAMPED_BY_DURATION}"
        )

    excavator = results[results["category"] == "excavator"]
    excavator_clamped = (
        excavator[excavator["duration_days"].isin(EXPECTED_EXCAVATOR_CLAMPED)]
        .groupby("duration_days")["was_clamped"]
        .sum()
        .astype(int)
        .to_dict()
    )
    if excavator_clamped != EXPECTED_EXCAVATOR_CLAMPED:
        raise RuntimeError(
            "Excavator serving-path results differ from the documented residual watch case: "
            f"{excavator_clamped}"
        )


def main() -> None:
    verify_artifact_identities()
    previous_model = pricing_model._model
    pricing_model.reload_model()
    if pricing_model._model is previous_model:
        raise RuntimeError("reload_model() did not replace the in-process model object")

    with SessionLocal() as session:
        resolution = resolve_pricing_schema(session)
        assets = validation.load_live_assets(session, resolution)

    results = evaluate_serving_path(assets)
    verify_live_results(results, asset_count=len(assets))

    summary = results.groupby("duration_days").agg(
        assets=("asset_id", "size"), clamped=("was_clamped", "sum")
    )
    summary["clamp_rate_%"] = summary["clamped"] / summary["assets"] * 100
    excavator = results[results["category"] == "excavator"].groupby("duration_days").agg(
        assets=("asset_id", "size"), clamped=("was_clamped", "sum")
    )
    excavator["clamp_rate_%"] = excavator["clamped"] / excavator["assets"] * 100

    print(
        f"Phase 2e serving smoke PASS: schema={resolution.schema}, "
        f"degraded={resolution.degraded}, assets={len(assets)}, "
        f"model_version={EXPECTED_MODEL_VERSION}"
    )
    print("\nAll-category clamp summary:")
    print(summary.round(2).to_string())
    print("\nExcavator watch summary:")
    print(excavator.round(2).to_string())


if __name__ == "__main__":
    main()
