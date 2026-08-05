"""FR-010.3 / FR-006 — Expand internal needs with quantity into unit-needs."""

from __future__ import annotations

from typing import Any

from haystack import component


def expand_needs_to_unit_dicts(needs: list[Any]) -> list[dict[str, Any]]:
    """Pure helper: quantity N → N unit-need dicts (immutable input)."""
    units: list[dict[str, Any]] = []
    for raw in needs or []:
        if isinstance(raw, dict):
            base_id = str(raw.get("need_id", "")).strip()
            description = str(raw.get("description", "")).strip()
            hints = list(raw.get("equipment_hints") or [])
            try:
                quantity = int(raw.get("quantity", 1))
            except (TypeError, ValueError):
                quantity = 1
        else:
            base_id = str(getattr(raw, "need_id", "")).strip()
            description = str(getattr(raw, "description", "")).strip()
            hints = list(getattr(raw, "equipment_hints", None) or [])
            try:
                quantity = int(getattr(raw, "quantity", 1))
            except (TypeError, ValueError):
                quantity = 1

        if not base_id or not description:
            continue

        n = max(1, quantity)
        if n == 1:
            units.append(
                {
                    "need_id": base_id,
                    "description": description,
                    "equipment_hints": hints,
                }
            )
        else:
            for i in range(1, n + 1):
                units.append(
                    {
                        "need_id": f"{base_id}__u{i}",
                        "description": description,
                        "equipment_hints": list(hints),
                    }
                )
    return units


@component
class ExpandQuantityComponent:
    """Expand decomposed needs into unit-needs (no quantity on RecommendationItem)."""

    @component.output_types(unit_needs=list)
    def run(self, needs: list | None = None) -> dict[str, list]:
        # Empty list is valid (FR-018b); service decides 400 if empty after expand.
        return {"unit_needs": expand_needs_to_unit_dicts(list(needs or []))}
