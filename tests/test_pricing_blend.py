from __future__ import annotations

import json
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app.services.pricing import feature_schema as fs
from app.services.pricing import train as pricing_train
from app.services.pricing.blend import build_training_dataset


def _rows(categories: list[str], *, start_price: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "category": categories,
            "condition": ["GOOD"] * len(categories),
            "duration_days": [7] * len(categories),
            "capacity": [2500.0] * len(categories),
            "distance_km": [15.0] * len(categories),
            "period_utilization": [0.5] * len(categories),
            "lead_time_days": [10] * len(categories),
            "platform_height": [np.nan] * len(categories),
            "price_per_day": [start_price + i for i in range(len(categories))],
        }
    )


def test_build_training_dataset_blends_categories_below_cutover() -> None:
    synthetic = _rows(["forklift", "forklift", "excavator"], start_price=10.0)
    real = _rows(["forklift"], start_price=200.0)

    combined, weights = build_training_dataset(
        real,
        synthetic,
        min_real_rows_per_category=2,
        real_sample_weight=5.0,
    )

    pd.testing.assert_frame_equal(combined.iloc[:3].reset_index(drop=True), synthetic)
    assert combined["category"].tolist() == ["forklift", "forklift", "excavator", "forklift"]
    np.testing.assert_array_equal(weights, np.array([1.0, 1.0, 1.0, 5.0]))


@pytest.mark.parametrize("real_count", [2, 3])
def test_build_training_dataset_cuts_over_category_at_or_above_threshold(
    real_count: int,
) -> None:
    synthetic = _rows(["forklift", "forklift", "excavator"], start_price=10.0)
    real = _rows(["forklift"] * real_count, start_price=200.0)

    combined, weights = build_training_dataset(
        real,
        synthetic,
        min_real_rows_per_category=2,
        real_sample_weight=4.0,
    )

    assert combined["category"].tolist() == ["excavator", *(["forklift"] * real_count)]
    np.testing.assert_array_equal(weights, np.array([1.0, *([4.0] * real_count)]))


def test_build_training_dataset_empty_real_rows_is_pure_synthetic() -> None:
    synthetic = _rows(["forklift", "excavator"], start_price=10.0)
    empty_real = synthetic.iloc[0:0].copy()

    combined, weights = build_training_dataset(
        empty_real,
        synthetic,
        min_real_rows_per_category=20,
        real_sample_weight=5.0,
    )

    pd.testing.assert_frame_equal(combined, synthetic)
    assert combined is not synthetic
    np.testing.assert_array_equal(weights, np.ones(len(synthetic)))


def test_build_training_dataset_rejects_invalid_controls() -> None:
    synthetic = _rows(["forklift"])
    real = synthetic.iloc[0:0].copy()

    with pytest.raises(ValueError, match="min_real_rows_per_category"):
        build_training_dataset(
            real,
            synthetic,
            min_real_rows_per_category=0,
            real_sample_weight=5.0,
        )
    with pytest.raises(ValueError, match="real_sample_weight"):
        build_training_dataset(
            real,
            synthetic,
            min_real_rows_per_category=1,
            real_sample_weight=-1.0,
        )


def test_train_accepts_in_memory_data_and_threads_training_weights(tmp_path, monkeypatch) -> None:
    data = _rows(
        [
            "forklift",
            "excavator",
            "boom lift",
            "scissor lift",
            "forklift",
        ]
    )
    weights = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    captured: dict[str, object] = {}

    class FakeModel:
        def __init__(self, **kwargs):
            captured["model_kwargs"] = kwargs

        def fit(self, X, y, *, sample_weight=None):
            captured["fit_rows"] = len(X)
            captured["fit_weights"] = sample_weight
            return self

        def predict(self, X):
            return np.full(len(X), 100.0)

    def fake_split(X, y, split_weights, **kwargs):
        assert kwargs == {"test_size": 0.2, "random_state": 17}
        return X.iloc[:3], X.iloc[3:], y.iloc[:3], y.iloc[3:], split_weights[:3], split_weights[3:]

    monkeypatch.setattr(pricing_train, "XGBRegressor", FakeModel)
    monkeypatch.setattr(pricing_train, "train_test_split", fake_split)
    monkeypatch.setattr(pricing_train.joblib, "dump", MagicMock())
    model_out = tmp_path / "candidate.pkl"
    meta_out = tmp_path / "candidate.json"

    pricing_train.train(
        data=data,
        sample_weight=weights,
        seed=17,
        model_out=model_out,
        meta_out=meta_out,
    )

    np.testing.assert_array_equal(captured["fit_weights"], weights[:3])
    assert captured["fit_rows"] == 3
    metadata = json.loads(meta_out.read_text())
    assert metadata["data_source"] == "in-memory"
    assert metadata["row_counts"] == {"train": 3, "test": 2, "total": 5}
    assert metadata["feature_columns"] == fs.FEATURE_COLUMNS


def test_train_rejects_weight_length_mismatch() -> None:
    with pytest.raises(ValueError, match="sample_weight length"):
        pricing_train.train(data=_rows(["forklift", "excavator"]), sample_weight=np.ones(1))
