from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "ml-experiments" / "phase2e_serving_smoke.py"
SPEC = importlib.util.spec_from_file_location("phase2e_serving_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def _representative_assets() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "asset_id": 1,
                "category": "forklift",
                "condition": "GOOD",
                "capacity": 2500.0,
                "platform_height": None,
                "min_daily_rate": 1.0,
                "max_daily_rate": 10_000.0,
            },
            {
                "asset_id": 2,
                "category": "scissor lift",
                "condition": "GOOD",
                "capacity": 350.0,
                "platform_height": 10.0,
                "min_daily_rate": 1.0,
                "max_daily_rate": 10_000.0,
            },
            {
                "asset_id": 3,
                "category": "boom lift",
                "condition": "GOOD",
                "capacity": 250.0,
                "platform_height": 18.0,
                "min_daily_rate": 1.0,
                "max_daily_rate": 10_000.0,
            },
            {
                "asset_id": 4,
                "category": "excavator",
                "condition": "GOOD",
                "capacity": 5000.0,
                "platform_height": None,
                "min_daily_rate": 1.0,
                "max_daily_rate": 10_000.0,
            },
        ]
    )


def test_phase2e_artifact_identities() -> None:
    smoke.verify_artifact_identities()


def test_promoted_model_runs_through_production_path_for_every_category() -> None:
    previous_model = smoke.pricing_model._model
    smoke.pricing_model.reload_model()
    assert smoke.pricing_model._model is not previous_model

    results = smoke.evaluate_serving_path(_representative_assets())

    assert len(results) == 4 * len(smoke.validation.DURATIONS)
    assert set(results["model_version"]) == {smoke.EXPECTED_MODEL_VERSION}
    assert (results["raw_price"] > 0).all()
    assert (results["clamped_price"] >= 1.0).all()
    assert (results["clamped_price"] <= 10_000.0).all()
