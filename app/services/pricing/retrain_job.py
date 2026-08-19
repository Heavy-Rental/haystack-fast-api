"""Synchronous Phase 3c pricing retrain orchestration.

The job builds a versioned candidate from the Phase 3b real/synthetic blend,
compares it with the serving model through the shared Phase 3a promotion gate,
and replaces the serving artifacts only after a pass.  It deliberately owns no
scheduling concerns; Phase 3d runs this function off the application event loop.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import joblib
import pandas as pd

from app.config import get_settings
from app.core.db import SessionLocal
from app.services.pricing import blend, promotion_gate, repository
from app.services.pricing import model as pricing_model
from app.services.pricing import train as pricing_train
from app.services.pricing.read_resilience import resolve_pricing_schema

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
CURRENT_MODEL_PATH = ARTIFACTS_DIR / "model.pkl"
CURRENT_META_PATH = ARTIFACTS_DIR / "current.json"
CANDIDATE_MODEL_PATH = ARTIFACTS_DIR / "model_candidate.pkl"
CANDIDATE_META_PATH = ARTIFACTS_DIR / "current_candidate.json"
PREVIOUS_MODEL_PATH = ARTIFACTS_DIR / "model_previous.pkl"
PREVIOUS_META_PATH = ARTIFACTS_DIR / "current_previous.json"
STATE_PATH = ARTIFACTS_DIR / "retrain_state.json"

DEFAULT_MIN_REAL_ROWS_PER_CATEGORY = 20
DEFAULT_REAL_SAMPLE_WEIGHT = 5.0

Status = Literal["promoted", "gate_failed", "error"]


@dataclass(frozen=True)
class RetrainOutcome:
    """One completed retrain attempt, suitable for durable JSON state."""

    status: Status
    started_at: dt.datetime
    completed_at: dt.datetime
    message: str
    candidate_metrics: Mapping[str, float]
    gate_checks: Mapping[str, bool]
    gate_details: tuple[str, ...]


@dataclass(frozen=True)
class RetrainState:
    """Restart-safe record consumed by the Phase 3d scheduler."""

    last_run_at: dt.datetime | None
    last_outcome: RetrainOutcome | None


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _outcome_payload(outcome: RetrainOutcome) -> dict[str, Any]:
    payload = asdict(outcome)
    payload["started_at"] = outcome.started_at.isoformat()
    payload["completed_at"] = outcome.completed_at.isoformat()
    return payload


def _parse_datetime(value: object, *, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be an ISO-8601 string")
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def load_state() -> RetrainState:
    """Load the last job outcome, or return the explicit never-run state."""
    if not STATE_PATH.is_file():
        return RetrainState(last_run_at=None, last_outcome=None)

    payload = json.loads(STATE_PATH.read_text())
    raw_outcome = payload.get("last_outcome")
    if raw_outcome is None:
        return RetrainState(last_run_at=None, last_outcome=None)
    if not isinstance(raw_outcome, dict):
        raise TypeError("last_outcome must be an object")

    status = raw_outcome.get("status")
    if status not in {"promoted", "gate_failed", "error"}:
        raise ValueError(f"Unknown retrain status: {status!r}")
    outcome = RetrainOutcome(
        status=status,
        started_at=_parse_datetime(raw_outcome.get("started_at"), field="started_at"),
        completed_at=_parse_datetime(raw_outcome.get("completed_at"), field="completed_at"),
        message=str(raw_outcome.get("message") or ""),
        candidate_metrics={
            str(name): float(value)
            for name, value in dict(raw_outcome.get("candidate_metrics") or {}).items()
        },
        gate_checks={
            str(name): bool(value)
            for name, value in dict(raw_outcome.get("gate_checks") or {}).items()
        },
        gate_details=tuple(str(value) for value in raw_outcome.get("gate_details") or ()),
    )
    raw_last_run = payload.get("last_run_at")
    last_run_at = _parse_datetime(raw_last_run, field="last_run_at")
    return RetrainState(last_run_at=last_run_at, last_outcome=outcome)


def _atomic_write_text(destination: Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def save_state(outcome: RetrainOutcome) -> None:
    """Atomically persist one completed outcome without touching model metadata."""
    payload = {
        "last_run_at": outcome.completed_at.isoformat(),
        "last_outcome": _outcome_payload(outcome),
    }
    _atomic_write_text(STATE_PATH, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _configured_blend_controls() -> tuple[int, float]:
    settings = get_settings()
    minimum = int(
        getattr(
            settings,
            "pricing_retrain_min_real_rows_per_category",
            DEFAULT_MIN_REAL_ROWS_PER_CATEGORY,
        )
    )
    weight = float(
        getattr(
            settings,
            "pricing_retrain_real_sample_weight",
            DEFAULT_REAL_SAMPLE_WEIGHT,
        )
    )
    return minimum, weight


def _build_candidate(
    *,
    min_real_rows_per_category: int,
    real_sample_weight: float,
) -> dict[str, float]:
    synthetic_rows = pd.read_csv(pricing_train.DEFAULT_DATA_PATH)
    with SessionLocal() as session:
        resolution = resolve_pricing_schema(session)
        real_rows = repository.fetch_real_training_rows(session, resolution)
    training_rows, sample_weight = blend.build_training_dataset(
        real_rows,
        synthetic_rows,
        min_real_rows_per_category=min_real_rows_per_category,
        real_sample_weight=real_sample_weight,
    )
    return pricing_train.train(
        data=training_rows,
        sample_weight=sample_weight,
        model_out=CANDIDATE_MODEL_PATH,
        meta_out=CANDIDATE_META_PATH,
    )


def _load_metadata(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise TypeError(f"Artifact metadata must be an object: {path}")
    return payload


def _evaluate_candidate() -> promotion_gate.GateDecision:
    current_metadata = _load_metadata(CURRENT_META_PATH)
    candidate_metadata = _load_metadata(CANDIDATE_META_PATH)
    promotion_gate.validate_artifact_contract(current_metadata, label="current")
    promotion_gate.validate_artifact_contract(candidate_metadata, label="candidate")

    models = {
        "current": joblib.load(CURRENT_MODEL_PATH),
        "candidate": joblib.load(CANDIDATE_MODEL_PATH),
    }
    for label, loaded_model in models.items():
        promotion_gate.validate_model_features(loaded_model, label=label)

    with SessionLocal() as session:
        resolution = resolve_pricing_schema(session)
        assets = promotion_gate.load_live_assets(session, resolution)

    rows = promotion_gate.build_validation_rows(assets)
    predictions = pd.concat(
        [
            promotion_gate.evaluate_model(label, loaded_model, rows)
            for label, loaded_model in models.items()
        ],
        ignore_index=True,
    )
    summary = promotion_gate.summarize_predictions(predictions)
    accuracy = promotion_gate.evaluate_common_holdout(
        models,
        pricing_train.DEFAULT_DATA_PATH,
    )
    return promotion_gate.assess_gate(
        summary,
        accuracy,
        actual_asset_count=len(assets),
        expected_asset_count=None,
        min_asset_count=1,
    )


def _atomic_copy(source: Path, destination: Path) -> None:
    """Copy one artifact through a same-directory temporary file and replace."""
    if not source.is_file():
        raise FileNotFoundError(f"Artifact does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _rollback() -> None:
    _atomic_copy(PREVIOUS_MODEL_PATH, CURRENT_MODEL_PATH)
    _atomic_copy(PREVIOUS_META_PATH, CURRENT_META_PATH)
    pricing_model.reload_model()


def _promote() -> None:
    """Back up one generation, swap the candidate, and hot-reload serving."""
    _atomic_copy(CURRENT_MODEL_PATH, PREVIOUS_MODEL_PATH)
    _atomic_copy(CURRENT_META_PATH, PREVIOUS_META_PATH)
    try:
        _atomic_copy(CANDIDATE_MODEL_PATH, CURRENT_MODEL_PATH)
        _atomic_copy(CANDIDATE_META_PATH, CURRENT_META_PATH)
        pricing_model.reload_model()
    except Exception as promotion_error:
        try:
            _rollback()
        except Exception as rollback_error:
            raise RuntimeError(
                f"promotion failed ({promotion_error}); rollback also failed ({rollback_error})"
            ) from rollback_error
        raise RuntimeError(f"promotion failed and was rolled back: {promotion_error}") from promotion_error


def _complete(outcome: RetrainOutcome) -> RetrainOutcome:
    try:
        save_state(outcome)
    except Exception:
        logger.exception("Could not persist pricing retrain state")
    return outcome


def run_scheduled_retrain(
    *,
    min_real_rows_per_category: int | None = None,
    real_sample_weight: float | None = None,
) -> RetrainOutcome:
    """Run one complete retrain attempt; record and return instead of raising."""
    started_at = _utcnow()
    try:
        configured_minimum, configured_weight = _configured_blend_controls()
        minimum = (
            configured_minimum
            if min_real_rows_per_category is None
            else min_real_rows_per_category
        )
        weight = configured_weight if real_sample_weight is None else real_sample_weight
        candidate_metrics = _build_candidate(
            min_real_rows_per_category=minimum,
            real_sample_weight=weight,
        )
    except Exception as exc:
        logger.exception("Pricing retrain candidate build failed")
        return _complete(
            RetrainOutcome(
                status="error",
                started_at=started_at,
                completed_at=_utcnow(),
                message=f"candidate build failed: {exc}",
                candidate_metrics={},
                gate_checks={},
                gate_details=(),
            )
        )

    try:
        decision = _evaluate_candidate()
    except Exception as exc:
        logger.exception("Pricing retrain candidate evaluation or live read failed")
        return _complete(
            RetrainOutcome(
                status="error",
                started_at=started_at,
                completed_at=_utcnow(),
                message=f"candidate evaluation/live read failed: {exc}",
                candidate_metrics=dict(candidate_metrics),
                gate_checks={},
                gate_details=(),
            )
        )

    if not decision.passed:
        logger.warning(
            "Pricing retrain candidate did not pass promotion gate: checks=%s details=%s",
            dict(decision.checks),
            decision.details,
        )
        return _complete(
            RetrainOutcome(
                status="gate_failed",
                started_at=started_at,
                completed_at=_utcnow(),
                message="candidate did not pass the promotion gate",
                candidate_metrics=dict(candidate_metrics),
                gate_checks=dict(decision.checks),
                gate_details=decision.details,
            )
        )

    try:
        _promote()
    except Exception as exc:
        logger.exception("Pricing retrain promotion failed")
        return _complete(
            RetrainOutcome(
                status="error",
                started_at=started_at,
                completed_at=_utcnow(),
                message=f"promotion failed: {exc}",
                candidate_metrics=dict(candidate_metrics),
                gate_checks=dict(decision.checks),
                gate_details=decision.details,
            )
        )

    logger.info("Pricing retrain candidate promoted")
    return _complete(
        RetrainOutcome(
            status="promoted",
            started_at=started_at,
            completed_at=_utcnow(),
            message="candidate promoted and serving model reloaded",
            candidate_metrics=dict(candidate_metrics),
            gate_checks=dict(decision.checks),
            gate_details=decision.details,
        )
    )
