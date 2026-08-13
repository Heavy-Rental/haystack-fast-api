from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "ml-experiments" / "candidate_validation_check.py"
)
SPEC = importlib.util.spec_from_file_location("candidate_validation_check", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
validation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validation
SPEC.loader.exec_module(validation)


class DurationModel:
    def __init__(self, multiplier: float) -> None:
        self.multiplier = multiplier

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return features["duration_days"].to_numpy(dtype=float) * self.multiplier


def _assets() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "asset_id": 1,
                "asset_name": "Forklift A",
                "category": "forklift",
                "condition": None,
                "capacity": None,
                "platform_height": None,
                "min_daily_rate": 5.0,
                "max_daily_rate": 10.0,
            },
            {
                "asset_id": 2,
                "asset_name": "Scissor A",
                "category": "scissor lift",
                "condition": "EXCELLENT",
                "capacity": 300.0,
                "platform_height": 10.0,
                "min_daily_rate": 6.0,
                "max_daily_rate": 12.0,
            },
        ]
    )


def test_build_rows_reuses_production_fallbacks_and_crosses_durations() -> None:
    rows = validation.build_validation_rows(_assets(), durations=(1, 7), distance_km=18.5)

    assert len(rows) == 4
    forklift = rows[rows["asset_id"] == 1]
    assert set(forklift["condition"]) == {"GOOD"}
    assert forklift["capacity"].notna().all()
    assert forklift["platform_height"].isna().all()
    assert set(rows["distance_km"]) == {18.5}
    assert set(rows["duration_days"]) == {1.0, 7.0}


def test_evaluate_model_uses_production_clamp_math_and_summarizes_direction() -> None:
    rows = validation.build_validation_rows(_assets(), durations=(1, 7))
    evaluated = validation.evaluate_model("candidate", DurationModel(2.0), rows)
    summary = validation.summarize_predictions(evaluated)

    one_day = evaluated[evaluated["duration_days"] == 1]
    seven_day = evaluated[evaluated["duration_days"] == 7]
    assert set(one_day["clamp_direction"]) == {"below_min"}
    assert set(seven_day["clamp_direction"]) == {"above_max"}
    assert set(summary["clamped"]) == {2}
    assert set(summary["clamp_rate"]) == {1.0}
    with pytest.raises(ValueError, match="non-finite predictions"):
        validation.evaluate_model("candidate", DurationModel(np.nan), rows)


def test_build_rows_rejects_non_finite_or_inverted_guardrails() -> None:
    assets = _assets()
    assets.loc[0, "min_daily_rate"] = np.nan
    with pytest.raises(ValueError, match="invalid daily-rate guardrails"):
        validation.build_validation_rows(assets)

    assets.loc[0, "min_daily_rate"] = 11.0
    with pytest.raises(ValueError, match="invalid daily-rate guardrails"):
        validation.build_validation_rows(assets)


def test_common_holdout_scores_both_models_on_identical_rows(tmp_path: Path) -> None:
    rows = []
    for duration in range(1, 21):
        rows.append(
            {
                "category": "forklift",
                "condition": "GOOD",
                "duration_days": duration,
                "capacity": 2500.0,
                "distance_km": 20.0,
                "period_utilization": 0.7,
                "lead_time_days": 5.0,
                "platform_height": np.nan,
                "price_per_day": duration * 2.0,
            }
        )
    data_path = tmp_path / "candidate.csv"
    pd.DataFrame.from_records(rows).to_csv(data_path, index=False)

    metrics = validation.evaluate_common_holdout(
        {"current": DurationModel(1.0), "candidate": DurationModel(2.0)}, data_path
    ).set_index("model")

    assert metrics.loc["candidate", "mae"] == pytest.approx(0.0)
    assert metrics.loc["candidate", "r2"] == pytest.approx(1.0)
    assert metrics.loc["current", "mae"] > metrics.loc["candidate", "mae"]


def test_common_holdout_missing_data_has_regeneration_command(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="generate_synthetic_data.py"):
        validation.evaluate_common_holdout(
            {"current": DurationModel(1.0), "candidate": DurationModel(2.0)},
            tmp_path / "missing.csv",
        )


def test_candidate_data_provenance_rejects_wrong_hash_or_metrics() -> None:
    accuracy = pd.DataFrame.from_records(
        [
            {"model": "current", "mae": 30.0, "rmse": 40.0, "r2": 0.5},
            {"model": "candidate", "mae": 10.0, "rmse": 12.0, "r2": 0.9},
        ]
    )
    accuracy.attrs.update(total_rows=5000, test_rows=1000, data_sha256="wrong")
    metadata = {
        "row_counts": {"total": 5000, "test": 1000},
        "metrics": {"mae": 10.0, "rmse": 12.0, "r2": 0.9},
    }

    with pytest.raises(ValueError, match="provenance mismatch"):
        validation.validate_candidate_data_provenance(accuracy, metadata)

    accuracy.attrs["data_sha256"] = validation.EXPECTED_CANDIDATE_DATA_SHA256
    metadata["metrics"]["mae"] = 11.0
    with pytest.raises(ValueError, match="provenance mismatch"):
        validation.validate_candidate_data_provenance(accuracy, metadata)

    metadata["metrics"]["mae"] = 10.0
    validation.validate_candidate_data_provenance(accuracy, metadata)


def test_artifact_contract_rejects_feature_schema_drift() -> None:
    metadata = {
        "feature_columns": ["wrong"],
        "condition_order": validation.fs.CONDITION_ORDER,
        "categories": validation.fs.CATEGORIES,
        "target_column": validation.fs.TARGET_COLUMN,
    }

    with pytest.raises(ValueError, match="feature_columns"):
        validation.validate_artifact_contract(metadata, label="candidate")


def _gate_summary(current_rate: float, candidate_rate: float) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "model": model,
                "duration_days": float(duration),
                "assets": 27,
                "clamped": round(rate * 27),
                "below_min": 0,
                "above_max": 0,
                "clamp_rate": rate,
            }
            for duration in validation.REALISTIC_DURATIONS
            for model, rate in (("current", current_rate), ("candidate", candidate_rate))
        ]
    )


def test_gate_passes_only_when_clamp_accuracy_and_completeness_pass() -> None:
    accuracy = pd.DataFrame.from_records(
        [
            {"model": "current", "mae": 20.0, "rmse": 25.0, "r2": 0.95},
            {"model": "candidate", "mae": 20.5, "rmse": 25.5, "r2": 0.96},
        ]
    )
    passed = validation.assess_gate(
        _gate_summary(0.93, 0.30), accuracy, actual_asset_count=27
    )
    failed = validation.assess_gate(
        _gate_summary(0.93, 0.60), accuracy, actual_asset_count=26
    )

    assert passed.passed is True
    assert all(passed.checks.values())
    assert failed.passed is False
    assert failed.checks["asset_count"] is False
    assert failed.checks["duration_7_candidate_ceiling"] is False
