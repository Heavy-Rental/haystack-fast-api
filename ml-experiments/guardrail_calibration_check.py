"""Measure real asset guardrails against the Phase 1 synthetic calibration.

Phase 2d-i is deliberately read-only: it queries the live Spring-owned asset
snapshot, computes the synthetic generator's implied base rate for each asset,
and compares the real bounds with the configured guardrail-ratio ranges.  It
does not load a trained model or write data/model artifacts.

Run from the repository root::

    uv run python ml-experiments/guardrail_calibration_check.py

The summary is printed to stdout and the comparison chart is written under
``ml-experiments/outputs/phase2d/`` by default.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pricing_tables as pt

from app.core.db import SessionLocal
from app.models.asset import Asset
from app.models.asset_category import AssetCategory
from app.services.pricing.category_mapping import to_feature_name
from app.services.pricing.read_resilience import (
    PricingSchemaResolution,
    resolve_pricing_schema,
)

DEFAULT_OUTPUT = SCRIPT_DIR / "outputs" / "phase2d" / "guardrail_calibration_check.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def load_real_bounds(session: Session, resolution: PricingSchemaResolution) -> pd.DataFrame:
    """Read all real assets and normalize their DB category names."""
    statement = (
        select(
            Asset.id,
            AssetCategory.name,
            Asset.capacity,
            Asset.platform_height,
            Asset.min_daily_rate,
            Asset.max_daily_rate,
        )
        .join(AssetCategory, Asset.category_id == AssetCategory.id)
        .order_by(AssetCategory.name, Asset.id)
    )
    rows = session.execute(statement, execution_options=resolution.execution_options).all()

    records = [
        {
            "asset_id": asset_id,
            "category": to_feature_name(db_category),
            "capacity": float(capacity) if capacity is not None else np.nan,
            "platform_height": (float(platform_height) if platform_height is not None else np.nan),
            "real_min": float(min_daily_rate),
            "real_max": float(max_daily_rate),
        }
        for asset_id, db_category, capacity, platform_height, min_daily_rate, max_daily_rate in rows
    ]
    if not records:
        raise RuntimeError(f"No assets found in pricing schema {resolution.schema!r}")
    return pd.DataFrame.from_records(records)


def implied_base_rate(row: pd.Series) -> float:
    """Mirror generate_synthetic_data.compute_base_daily_rate for one asset."""
    category = str(row["category"])
    driver = pt.CATEGORY_PRICE_DRIVER[category]
    if driver == "capacity":
        value = row["capacity"]
        limits = pt.CATEGORY_CAPACITY_KG[category]
    else:
        value = row["platform_height"]
        limits = pt.CATEGORY_PLATFORM_HEIGHT_M[category]
    if pd.isna(value):
        raise ValueError(
            f"Asset {int(row['asset_id'])} has no {driver} required for {category!r} pricing"
        )

    fraction = np.clip((float(value) - limits["min"]) / (limits["max"] - limits["min"]), 0, 1)
    scaled = fraction**pt.CAPACITY_ELASTICITY_EXPONENT
    anchors = pt.CATEGORY_BASE_RATE[category]
    rate = anchors["rate_at_min"] + (anchors["rate_at_max"] - anchors["rate_at_min"]) * scaled

    if category in pt.AERIAL_CATEGORIES:
        capacity = row["capacity"]
        if pd.isna(capacity):
            raise ValueError(
                f"Asset {int(row['asset_id'])} has no capacity required for {category!r} pricing"
            )
        cap_limits = pt.CATEGORY_CAPACITY_KG[category]
        cap_fraction = np.clip(
            (float(capacity) - cap_limits["min"]) / (cap_limits["max"] - cap_limits["min"]),
            0,
            1,
        )
        rate *= 1 + pt.SECONDARY_CAPACITY_SLOPE * (cap_fraction - 0.5)

    return round(rate / 5) * 5


def add_calibration_columns(bounds: pd.DataFrame) -> pd.DataFrame:
    measured = bounds.copy()
    measured["implied_base"] = measured.apply(implied_base_rate, axis=1)
    measured["real_min_ratio"] = measured["real_min"] / measured["implied_base"]
    measured["real_max_ratio"] = measured["real_max"] / measured["implied_base"]
    measured["implied_min_low"] = measured["implied_base"] * pt.GUARDRAIL_MIN_RATIO_RANGE[0]
    measured["implied_min_high"] = measured["implied_base"] * pt.GUARDRAIL_MIN_RATIO_RANGE[1]
    measured["implied_max_low"] = measured["implied_base"] * pt.GUARDRAIL_MAX_RATIO_RANGE[0]
    measured["implied_max_high"] = measured["implied_base"] * pt.GUARDRAIL_MAX_RATIO_RANGE[1]
    return measured


def summarize(measured: pd.DataFrame) -> pd.DataFrame:
    """Keep the base-scale and ratio-band checks visible as separate columns."""
    rows: list[dict[str, float | int | str]] = []
    min_lo, min_hi = pt.GUARDRAIL_MIN_RATIO_RANGE
    max_lo, max_hi = pt.GUARDRAIL_MAX_RATIO_RANGE
    for category in pt.CATEGORIES:
        group = measured[measured["category"] == category]
        if group.empty:
            continue
        rows.append(
            {
                "category": category,
                "n": len(group),
                "base_med": group["implied_base"].median(),
                "real_min_med": group["real_min"].median(),
                "real_max_med": group["real_max"].median(),
                "min_ratio_med": group["real_min_ratio"].median(),
                "min_in_band_%": group["real_min_ratio"].between(min_lo, min_hi).mean() * 100,
                "max_ratio_med": group["real_max_ratio"].median(),
                "max_in_band_%": group["real_max_ratio"].between(max_lo, max_hi).mean() * 100,
            }
        )
    return pd.DataFrame(rows).set_index("category")


def render_chart(measured: pd.DataFrame, out_path: Path) -> None:
    categories = [category for category in pt.CATEGORIES if category in set(measured["category"])]
    positions = np.arange(len(categories))
    fig, (rates_ax, ratios_ax) = plt.subplots(2, 1, figsize=(11, 9), sharex=True)

    for index, category in enumerate(categories):
        group = measured[measured["category"] == category]
        offsets = np.linspace(-0.08, 0.08, len(group))
        rates_ax.scatter(
            index + offsets, group["real_min"], marker="v", label="Real min" if index == 0 else None
        )
        rates_ax.scatter(
            index + offsets,
            group["implied_base"],
            marker="o",
            label="Implied base" if index == 0 else None,
        )
        rates_ax.scatter(
            index + offsets, group["real_max"], marker="^", label="Real max" if index == 0 else None
        )
        ratios_ax.scatter(
            index + offsets,
            group["real_min_ratio"],
            marker="v",
            label="Real min / base" if index == 0 else None,
        )
        ratios_ax.scatter(
            index + offsets,
            group["real_max_ratio"],
            marker="^",
            label="Real max / base" if index == 0 else None,
        )

    rates_ax.set_title("Knob 1: real bounds vs. CATEGORY_BASE_RATE-implied asset base")
    rates_ax.set_ylabel("SGD / day")
    rates_ax.grid(axis="y", alpha=0.25)
    rates_ax.legend(ncols=3)

    ratios_ax.axhspan(
        *pt.GUARDRAIL_MIN_RATIO_RANGE,
        color="tab:blue",
        alpha=0.15,
        label="Configured min-ratio band",
    )
    ratios_ax.axhspan(
        *pt.GUARDRAIL_MAX_RATIO_RANGE,
        color="tab:orange",
        alpha=0.15,
        label="Configured max-ratio band",
    )
    ratios_ax.set_title("Knob 2: real bound/base ratios vs. configured guardrail bands")
    ratios_ax.set_ylabel("Ratio to implied base")
    ratios_ax.set_xticks(positions, categories)
    ratios_ax.grid(axis="y", alpha=0.25)
    ratios_ax.legend(ncols=2)

    fig.suptitle(f"Phase 2d-i real-bound calibration ({len(measured)} assets)", fontsize=14)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        resolution = resolve_pricing_schema(session)
        measured = add_calibration_columns(load_real_bounds(session, resolution))

    summary = summarize(measured)
    print(
        f"Pricing schema: {resolution.schema} (degraded={resolution.degraded}); "
        f"assets measured: {len(measured)}"
    )
    print(
        "Configured ratio bands: "
        f"min={pt.GUARDRAIL_MIN_RATIO_RANGE}, max={pt.GUARDRAIL_MAX_RATIO_RANGE}\n"
    )
    print(summary.round(3).to_string())

    render_chart(measured, args.out)
    print(f"\nSaved comparison chart to {args.out}")


if __name__ == "__main__":
    main()
