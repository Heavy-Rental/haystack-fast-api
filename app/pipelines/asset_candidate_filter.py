"""FR-010.4 — Filter seeded (or injected) fleet candidates for a unit-need."""

from __future__ import annotations

from typing import Any

from haystack import component

from app.pipelines.catalog import infer_model_categories, is_approved_display_type
from app.pipelines.seed_fleet import get_seed_assets


@component
class AssetCandidateFilter:
    """Match unit-need to approved catalog assets (seed subset for MVP)."""

    def __init__(self, assets: list[dict[str, Any]] | None = None) -> None:
        self._assets = assets  # None → use seed fleet at run

    @component.output_types(candidates=list)
    def run(self, unit_need: dict | None = None) -> dict[str, list]:
        need = unit_need or {}
        categories = infer_model_categories(need)
        fleet = self._assets if self._assets is not None else get_seed_assets()

        if not categories:
            # No recognizable equipment signal → empty (Scenario C style)
            return {"candidates": []}

        candidates: list[dict[str, Any]] = []
        for asset in fleet:
            if not is_approved_display_type(str(asset.get("equipment_type") or "")):
                continue
            if asset.get("category") in categories:
                candidates.append(dict(asset))
        return {"candidates": candidates}
