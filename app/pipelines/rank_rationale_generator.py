"""FR-010.7 — Select one best candidate and emit honest rationale (MVP template)."""

from __future__ import annotations

from typing import Any

from haystack import component

_CONDITION_SCORE = {
    "NEEDS_REPAIR": 0,
    "FAIR": 1,
    "GOOD": 2,
    "EXCELLENT": 3,
}


def _score(candidate: dict[str, Any], unit_need: dict[str, Any]) -> float:
    score = float(_CONDITION_SCORE.get(str(candidate.get("condition") or ""), 1))
    hints = [str(h).lower() for h in (unit_need.get("equipment_hints") or [])]
    etype = str(candidate.get("equipment_type") or "").lower()
    cat = str(candidate.get("category") or "").lower()
    desc = str(unit_need.get("description") or "").lower()
    for h in hints:
        if h and (h in etype or h in cat or h in desc):
            score += 2.0
    # Prefer higher capacity slightly
    score += min(float(candidate.get("capacity") or 0.0) / 10000.0, 1.0)
    return score


def build_template_rationale(unit_need: dict[str, Any], selected: dict[str, Any]) -> str:
    etype = selected.get("equipment_type") or "equipment"
    desc = (unit_need.get("description") or "").strip() or "the stated project need"
    return (
        f"Selected {etype} ({selected.get('asset_id')}) as the best available match "
        f"for: {desc}. "
        f"Assumed category alignment from equipment hints/description keywords. "
        f"Refine capacity, platform height, or outdoor/rough-terrain requirements if needed "
        f"(schema does not capture terrain/operator-required)."
    )


@component
class RankRationaleGenerator:
    """Pick exactly one candidate (rank=1) and produce rationale text."""

    @component.output_types(selected=dict, rationale=str)
    def run(
        self,
        unit_need: dict | None = None,
        priced_candidates: list | None = None,
    ) -> dict[str, Any]:
        need = unit_need or {}
        pool = list(priced_candidates or [])
        if not pool:
            return {"selected": {}, "rationale": ""}

        ranked = sorted(pool, key=lambda c: _score(c, need), reverse=True)
        best = dict(ranked[0])
        best["rank"] = 1
        rationale = build_template_rationale(need, best)
        return {"selected": best, "rationale": rationale}
