"""Script-based live demo of the dynamic pricing model (Phase 1d, dynamic-pricing feature).

Scratch/offline script -- lives outside the app's SDD structure per
docs/dynamic-pricing-masterplan.md, same convention as generate_synthetic_data.py
and shap_review.py.

Why this script exists: predict_price(...) is intentionally in-process only --
no HTTP endpoint, no Postman option (SPEC-dynamic-pricing.md §5.1, §3, a
locked decision this script doesn't revisit). For a lecturer/live audience
demo, a script is the only way to show it running.

What this is, and what it deliberately is NOT (see
docs/dynamic-pricing-masterplan.md's "Live demo script" note for the full
reasoning):
- This script: 1-2 illustrative scenario pairs for a non-technical live
  audience, holding all other inputs fixed per pair. Not exhaustive.
- tests/ (separately scoped, not this script): plumbing correctness --
  output shape/type, clamping boundaries, NaN handling.
- shap_review.py (not extended by this script): comprehensive directional-
  sweep coverage across all categories/feature ranges.

Produces:
- outputs/demo_condition_effect.png -- price_per_day for the same asset at
  NEEDS_REPAIR vs EXCELLENT condition, duration_days/distance_km held fixed.
  Expect EXCELLENT priced above NEEDS_REPAIR.
- outputs/demo_duration_effect.png -- price_per_day (not total price) for the
  same asset at a short vs long duration_days, condition/distance_km held
  fixed. Expect the long-duration per-day rate below the short-duration one
  (non-linear discount).

Both plots show raw model output and guardrail-clamped output side by side
for every scenario, to visually demonstrate the clamping logic
(SPEC-dynamic-pricing.md §5.4) is doing something, not just the model itself.
"""

import argparse
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from predict_price import PricePrediction
from predict_price import predict_price as _predict_price
# Single import site; swap to app.services.pricing.model.predict_price once
# Phase 2/2b lands (SPEC-dynamic-pricing.md §5.1) -- same swap point
# app/services/pricing_client.py already frames its own import around.

SCRIPT_DIR = Path(__file__).resolve().parent

# TODO(Phase 1e/2): replace with a real Asset row via the SQLAlchemy read
# models (SPEC-dynamic-pricing.md §5.3) once they exist. Shape mirrors
# app/pipelines/seed_fleet.py's SEED_ASSETS so the swap is a loader change,
# not a script rewrite -- every scenario builder below goes through
# _load_asset_specs(), never an inline literal.
DEMO_ASSET_SPECS: dict[str, dict] = {
    "demo_excavator": {
        "category": "excavator",
        # TODO placeholder -- chosen (not arbitrary) so both pairs land near
        # the static per-category guardrail floor (pricing_tables.
        # CATEGORY_BASE_RATE["excavator"]["rate_at_min"]): one scenario per
        # pair clamps, the other doesn't, so raw vs clamped bars actually
        # differ instead of both flooring out identically. Revisit once a
        # real asset replaces this (Phase 1e/2) -- the real per-asset
        # min/maxDailyRate bounds won't line up the same way.
        "capacity": 8000.0,
        "platform_height": None,  # non-aerial
    },
}


def _load_asset_specs() -> dict[str, dict]:
    """Swap point for a real DB-backed asset lookup (Phase 1e/2)."""
    return DEMO_ASSET_SPECS


@dataclass(frozen=True)
class Scenario:
    label: str
    category: str
    condition: str
    duration_days: float
    capacity: float
    distance_km: float
    platform_height: float | None


def build_condition_pair(
    asset: dict, *, duration_days: float = 7, distance_km: float = 15
) -> list[Scenario]:
    """Same asset, only condition differs. Goal: condition up -> price up."""
    common = dict(
        category=asset["category"],
        duration_days=duration_days,
        capacity=asset["capacity"],
        distance_km=distance_km,
        platform_height=asset["platform_height"],
    )
    return [
        Scenario(label="NEEDS_REPAIR", condition="NEEDS_REPAIR", **common),
        Scenario(label="EXCELLENT", condition="EXCELLENT", **common),
    ]


def build_duration_pair(
    asset: dict,
    *,
    condition: str = "GOOD",
    distance_km: float = 15,
    short_days: float = 2,
    long_days: float = 30,
) -> list[Scenario]:
    """Same asset, only duration_days differs. Goal: non-linear per-day
    discount on longer rentals -- predict_price() already returns a per-day
    rate, so comparing raw/clamped_price directly compares price_per_day, not
    total price."""
    common = dict(
        category=asset["category"],
        condition=condition,
        capacity=asset["capacity"],
        distance_km=distance_km,
        platform_height=asset["platform_height"],
    )
    return [
        Scenario(label=f"{short_days:g}-day rental", duration_days=short_days, **common),
        Scenario(label=f"{long_days:g}-day rental", duration_days=long_days, **common),
    ]


def describe_pair_fixed(scenarios: list[Scenario], varying: str) -> str:
    """Human-readable summary of what's held fixed across the pair,
    excluding whichever field the pair varies."""
    s = scenarios[0]
    fields = {
        "category": f"category={s.category}",
        "condition": f"condition={s.condition}",
        "duration_days": f"duration_days={s.duration_days:g}",
        "capacity": f"capacity={s.capacity:g}kg",
        "distance_km": f"distance_km={s.distance_km:g}km",
        "platform_height": (
            f"platform_height={s.platform_height:g}m" if s.platform_height is not None else "platform_height=n/a"
        ),
    }
    fields.pop(varying, None)
    return "fixed: " + ", ".join(fields.values())


def plot_pair_comparison(
    scenarios: list[Scenario],
    results: list[PricePrediction],
    title: str,
    fixed_description: str,
    out_path: Path,
) -> None:
    labels = [s.label for s in scenarios]
    raw = [r.raw_price for r in results]
    clamped = [r.clamped_price for r in results]

    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 4.8))
    bars_raw = ax.bar(x - width / 2, raw, width, label="raw", color="#1f77b4")
    bars_clamped = ax.bar(x + width / 2, clamped, width, label="clamped", color="#ff7f0e")
    for bars in (bars_raw, bars_clamped):
        for bar in bars:
            ax.annotate(
                f"{bar.get_height():.0f}",
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                ha="center", va="bottom", fontsize=9,
            )
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("price_per_day ($/day)")
    ax.legend()
    fig.suptitle(title, fontsize=12)
    wrapped_fixed = "\n".join(textwrap.wrap(fixed_description, width=60))
    ax.set_title(wrapped_fixed, fontsize=9, color="gray")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def run_pair(
    scenarios: list[Scenario], varying: str, goal: str, title: str, out_path: Path
) -> None:
    print(f"\n{title}")
    print(f"  goal: {goal}")
    print(f"  {describe_pair_fixed(scenarios, varying)}")

    results = [
        _predict_price(
            category=s.category,
            condition=s.condition,
            duration_days=s.duration_days,
            capacity=s.capacity,
            distance_km=s.distance_km,
            platform_height=s.platform_height,
        )
        for s in scenarios
    ]

    print(f"  {'scenario':<18} {'raw':>8} {'clamped':>8} {'clamped?':>9}")
    for s, r in zip(scenarios, results):
        print(f"  {s.label:<18} {r.raw_price:>8.2f} {r.clamped_price:>8.2f} {str(r.was_clamped):>9}")

    plot_pair_comparison(scenarios, results, title, describe_pair_fixed(scenarios, varying), out_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plots-dir", type=Path, default=SCRIPT_DIR / "outputs")
    parser.add_argument("--asset", default="demo_excavator", choices=list(DEMO_ASSET_SPECS))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.plots_dir.mkdir(parents=True, exist_ok=True)
    asset = _load_asset_specs()[args.asset]

    run_pair(
        build_condition_pair(asset),
        "condition",
        "condition up -> price up",
        f"Condition effect ({args.asset})",
        args.plots_dir / "demo_condition_effect.png",
    )

    run_pair(
        build_duration_pair(asset),
        "duration_days",
        "non-linear per-day discount on longer rentals (price_per_day, not total price)",
        f"Duration effect ({args.asset}, price_per_day)",
        args.plots_dir / "demo_duration_effect.png",
    )

    print(f"\nPlots saved to {args.plots_dir}")


if __name__ == "__main__":
    main()
