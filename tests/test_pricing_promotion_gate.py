from __future__ import annotations

import pandas as pd
import pytest

from app.services.pricing import promotion_gate


def _summary(current_rate: float = 0.9, candidate_rate: float = 0.3) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "model": model,
                "duration_days": float(duration),
                "clamp_rate": rate,
            }
            for duration in promotion_gate.REALISTIC_DURATIONS
            for model, rate in (
                ("current", current_rate),
                ("candidate", candidate_rate),
            )
        ]
    )


def _accuracy() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {"model": "current", "mae": 20.0, "r2": 0.95},
            {"model": "candidate", "mae": 20.5, "r2": 0.96},
        ]
    )


def test_assess_gate_defaults_to_recurring_job_asset_floor() -> None:
    passed = promotion_gate.assess_gate(
        _summary(),
        _accuracy(),
        actual_asset_count=2,
    )
    failed = promotion_gate.assess_gate(
        _summary(),
        _accuracy(),
        actual_asset_count=1,
        min_asset_count=2,
    )

    assert passed.passed is True
    assert passed.checks["asset_count"] is True
    assert "minimum 1" in passed.details[0]
    assert failed.passed is False
    assert failed.checks["asset_count"] is False


def test_assess_gate_exact_asset_count_mode_overrides_floor() -> None:
    passed = promotion_gate.assess_gate(
        _summary(),
        _accuracy(),
        actual_asset_count=27,
        expected_asset_count=27,
        min_asset_count=100,
    )
    failed = promotion_gate.assess_gate(
        _summary(),
        _accuracy(),
        actual_asset_count=26,
        expected_asset_count=27,
    )

    assert passed.checks["asset_count"] is True
    assert passed.details[0] == "asset count: 27/27"
    assert failed.checks["asset_count"] is False


@pytest.mark.parametrize(
    ("expected_asset_count", "min_asset_count", "message"),
    [(None, 0, "min_asset_count"), (0, 1, "expected_asset_count")],
)
def test_assess_gate_rejects_invalid_asset_thresholds(
    expected_asset_count: int | None,
    min_asset_count: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        promotion_gate.assess_gate(
            _summary(),
            _accuracy(),
            actual_asset_count=1,
            expected_asset_count=expected_asset_count,
            min_asset_count=min_asset_count,
        )
