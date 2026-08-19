"""Build the Phase 3 synthetic/real pricing training dataset."""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_training_dataset(
    real_rows: pd.DataFrame,
    synthetic_df: pd.DataFrame,
    *,
    min_real_rows_per_category: int,
    real_sample_weight: float,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Blend or cut over independently for each category.

    Synthetic rows remain for categories below the real-row threshold. Once
    a category reaches the threshold, only its real rows are retained. The
    returned weights align positionally with the returned DataFrame.
    """
    if min_real_rows_per_category < 1:
        raise ValueError("min_real_rows_per_category must be at least 1")
    if not np.isfinite(real_sample_weight) or real_sample_weight < 0:
        raise ValueError("real_sample_weight must be finite and non-negative")
    if "category" not in synthetic_df.columns or "category" not in real_rows.columns:
        raise ValueError("real_rows and synthetic_df must include a category column")

    if real_rows.empty:
        return synthetic_df.copy(deep=True), np.ones(len(synthetic_df), dtype=float)

    real_counts = real_rows["category"].value_counts()
    cutover_categories = set(real_counts[real_counts >= min_real_rows_per_category].index.tolist())
    retained_synthetic = synthetic_df.loc[~synthetic_df["category"].isin(cutover_categories)].copy()
    combined = pd.concat(
        [retained_synthetic, real_rows],
        ignore_index=True,
        sort=False,
    )
    weights = np.concatenate(
        [
            np.ones(len(retained_synthetic), dtype=float),
            np.full(len(real_rows), float(real_sample_weight), dtype=float),
        ]
    )
    return combined, weights
