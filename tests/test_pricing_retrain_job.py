from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services.pricing import feature_schema as fs
from app.services.pricing import retrain_job
from app.services.pricing.promotion_gate import GateDecision


def _metadata(trained_at: str) -> dict[str, object]:
    return {
        "trained_at": trained_at,
        "feature_columns": fs.FEATURE_COLUMNS,
        "condition_order": fs.CONDITION_ORDER,
        "categories": fs.CATEGORIES,
        "target_column": fs.TARGET_COLUMN,
        "metrics": {"mae": 1.0, "rmse": 2.0, "r2": 0.99},
    }


@pytest.fixture
def isolated_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    paths = {
        "current_model": tmp_path / "model.pkl",
        "current_meta": tmp_path / "current.json",
        "candidate_model": tmp_path / "model_candidate.pkl",
        "candidate_meta": tmp_path / "current_candidate.json",
        "previous_model": tmp_path / "model_previous.pkl",
        "previous_meta": tmp_path / "current_previous.json",
        "state": tmp_path / "retrain_state.json",
    }
    for constant, key in (
        ("CURRENT_MODEL_PATH", "current_model"),
        ("CURRENT_META_PATH", "current_meta"),
        ("CANDIDATE_MODEL_PATH", "candidate_model"),
        ("CANDIDATE_META_PATH", "candidate_meta"),
        ("PREVIOUS_MODEL_PATH", "previous_model"),
        ("PREVIOUS_META_PATH", "previous_meta"),
        ("STATE_PATH", "state"),
    ):
        monkeypatch.setattr(retrain_job, constant, paths[key])

    paths["current_model"].write_bytes(b"serving-model")
    paths["current_meta"].write_text(json.dumps(_metadata("2026-08-13T00:00:00+00:00")))
    return paths


def _candidate_builder(paths: dict[str, Path]):
    def build(*, min_real_rows_per_category: int, real_sample_weight: float):
        assert min_real_rows_per_category == 20
        assert real_sample_weight == 5.0
        paths["candidate_model"].write_bytes(b"candidate-model")
        paths["candidate_meta"].write_text(
            json.dumps(_metadata("2026-08-19T00:00:00+00:00"))
        )
        return {"mae": 1.0, "rmse": 2.0, "r2": 0.99}

    return build


def _decision(passed: bool) -> GateDecision:
    return GateDecision(
        passed=passed,
        checks={"asset_count": True, "quality": passed},
        details=("asset count: 27 (minimum 1)",),
    )


def test_gate_pass_promotes_candidate_backs_up_serving_and_saves_state(
    isolated_artifacts: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    reload_model = Mock()
    monkeypatch.setattr(retrain_job, "_build_candidate", _candidate_builder(isolated_artifacts))
    monkeypatch.setattr(retrain_job, "_evaluate_candidate", lambda: _decision(True))
    monkeypatch.setattr(retrain_job.pricing_model, "reload_model", reload_model)

    outcome = retrain_job.run_scheduled_retrain()

    assert outcome.status == "promoted"
    assert isolated_artifacts["current_model"].read_bytes() == b"candidate-model"
    assert isolated_artifacts["previous_model"].read_bytes() == b"serving-model"
    assert json.loads(isolated_artifacts["current_meta"].read_text())["trained_at"].startswith(
        "2026-08-19"
    )
    assert json.loads(isolated_artifacts["previous_meta"].read_text())["trained_at"].startswith(
        "2026-08-13"
    )
    reload_model.assert_called_once_with()
    state = retrain_job.load_state()
    assert state.last_run_at == outcome.completed_at
    assert state.last_outcome == outcome


def test_gate_failure_keeps_serving_artifacts_untouched(
    isolated_artifacts: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    reload_model = Mock()
    monkeypatch.setattr(retrain_job, "_build_candidate", _candidate_builder(isolated_artifacts))
    monkeypatch.setattr(retrain_job, "_evaluate_candidate", lambda: _decision(False))
    monkeypatch.setattr(retrain_job.pricing_model, "reload_model", reload_model)

    outcome = retrain_job.run_scheduled_retrain()

    assert outcome.status == "gate_failed"
    assert outcome.gate_checks == {"asset_count": True, "quality": False}
    assert isolated_artifacts["current_model"].read_bytes() == b"serving-model"
    assert not isolated_artifacts["previous_model"].exists()
    reload_model.assert_not_called()


@pytest.mark.parametrize("failure_stage", ["build", "live_read"])
def test_training_or_live_read_failure_is_recorded_without_promotion(
    failure_stage: str,
    isolated_artifacts: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if failure_stage == "build":
        monkeypatch.setattr(
            retrain_job,
            "_build_candidate",
            Mock(side_effect=RuntimeError("training failed")),
        )
    else:
        monkeypatch.setattr(retrain_job, "_build_candidate", _candidate_builder(isolated_artifacts))
        monkeypatch.setattr(
            retrain_job,
            "_evaluate_candidate",
            Mock(side_effect=RuntimeError("live read failed")),
        )

    outcome = retrain_job.run_scheduled_retrain()

    assert outcome.status == "error"
    assert failure_stage.replace("_", " ") in outcome.message
    assert isolated_artifacts["current_model"].read_bytes() == b"serving-model"
    assert retrain_job.load_state().last_outcome == outcome


def test_promotion_failure_rolls_back_both_serving_artifacts(
    isolated_artifacts: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retrain_job, "_build_candidate", _candidate_builder(isolated_artifacts))
    monkeypatch.setattr(retrain_job, "_evaluate_candidate", lambda: _decision(True))
    reload_model = Mock()
    monkeypatch.setattr(retrain_job.pricing_model, "reload_model", reload_model)
    real_atomic_copy = retrain_job._atomic_copy
    failed_once = False

    def fail_candidate_metadata_once(source: Path, destination: Path) -> None:
        nonlocal failed_once
        if source == isolated_artifacts["candidate_meta"] and not failed_once:
            failed_once = True
            raise OSError("simulated promotion failure")
        real_atomic_copy(source, destination)

    monkeypatch.setattr(retrain_job, "_atomic_copy", fail_candidate_metadata_once)

    outcome = retrain_job.run_scheduled_retrain()

    assert outcome.status == "error"
    assert "promotion failed" in outcome.message
    assert isolated_artifacts["current_model"].read_bytes() == b"serving-model"
    assert json.loads(isolated_artifacts["current_meta"].read_text())["trained_at"].startswith(
        "2026-08-13"
    )
    reload_model.assert_called_once_with()


def test_state_round_trip_and_never_run_default(
    isolated_artifacts: dict[str, Path],
) -> None:
    assert retrain_job.load_state() == retrain_job.RetrainState(
        last_run_at=None,
        last_outcome=None,
    )

    started = dt.datetime(2026, 8, 19, 10, 0, tzinfo=dt.UTC)
    outcome = retrain_job.RetrainOutcome(
        status="gate_failed",
        started_at=started,
        completed_at=started + dt.timedelta(minutes=2),
        message="candidate did not pass",
        candidate_metrics={"mae": 1.25},
        gate_checks={"quality": False},
        gate_details=("quality check failed",),
    )

    retrain_job.save_state(outcome)

    assert retrain_job.load_state() == retrain_job.RetrainState(
        last_run_at=outcome.completed_at,
        last_outcome=outcome,
    )
