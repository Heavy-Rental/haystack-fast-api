"""Shared stochastic imputations used by pricing training-data builders."""

from __future__ import annotations

import numpy as np

from app.services.pricing import pricing_tables as pt


def sample_distance_km(rng: np.random.Generator, n: int) -> np.ndarray:
    """Sample the Phase 1 distance proxy used when no real distance exists.

    Phase 3 real booking rows still have no schema-backed delivery distance.
    Keeping this sampler shared with the synthetic generator prevents the
    imputed real rows from drifting to a different distribution.
    """
    raw = (
        rng.gamma(
            shape=pt.DISTANCE_KM_GAMMA_SHAPE,
            scale=pt.DISTANCE_KM_GAMMA_SCALE,
            size=n,
        )
        + 1
    )
    return np.clip(
        np.round(raw),
        pt.DISTANCE_KM_MIN,
        pt.DISTANCE_KM_MAX,
    ).astype(int)
