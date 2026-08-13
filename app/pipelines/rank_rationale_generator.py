"""FR-010.7 — Select one best candidate and emit honest rationale."""

from __future__ import annotations

import re
from typing import Any

from haystack import component

from app.pipelines.catalog import infer_model_categories

_HEIGHT_M = re.compile(r"~?\s*(\d+(?:\.\d+)?)\s*m\b", re.I)

_CONDITION_SCORE = {
    "NEEDS_REPAIR": 0,
    "FAIR": 1,
    "GOOD": 2,
    "EXCELLENT": 3,
}


def _tie_break(candidate: dict[str, Any]) -> tuple[float, float]:
    cond = float(_CONDITION_SCORE.get(str(candidate.get("condition") or ""), 1))
    try:
        cap = float(candidate.get("capacity") or 0.0)
    except (TypeError, ValueError):
        cap = 0.0
    return cond, cap


def wanted_categories(unit_need: dict[str, Any]) -> list[str]:
    """Model categories this need is asking for (hints first)."""
    hints = [str(h).strip() for h in (unit_need.get("equipment_hints") or []) if str(h).strip()]
    if hints:
        return infer_model_categories(
            {"equipment_hints": hints, "description": ""}
        ) or [h.lower() for h in hints]
    return infer_model_categories(unit_need)


def _needed_height_m(unit_need: dict[str, Any]) -> float | None:
    blob = str(unit_need.get("description") or "")
    match = _HEIGHT_M.search(blob)
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def _daily_rate(candidate: dict[str, Any]) -> float | None:
    pricing = candidate.get("pricing")
    raw = None
    if isinstance(pricing, dict):
        raw = pricing.get("daily_rate")
    if raw is None:
        raw = candidate.get("daily_rate")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _is_available(candidate: dict[str, Any]) -> bool:
    if candidate.get("available") is True:
        return True
    if candidate.get("available") is False:
        return False
    status = str(candidate.get("availability") or "").strip().lower()
    return status in {"", "available"}


def score_need_match(unit_need: dict[str, Any], candidate: dict[str, Any]) -> float:
    """Traceable 0..1 match: category 0.50 + height 0.20 + available 0.15 + priced 0.15."""
    wanted = wanted_categories(unit_need)
    cat = str(candidate.get("category") or "").strip().lower()
    etype = str(candidate.get("equipment_type") or "").strip().lower()
    category_hit = 0.0
    if wanted:
        if cat in wanted or any(w in etype or w in cat for w in wanted):
            category_hit = 1.0
    score = 0.50 * category_hit

    need_h = _needed_height_m(unit_need)
    if need_h is not None:
        plat = candidate.get("platform_height")
        try:
            if plat is not None and float(plat) >= need_h:
                score += 0.20
        except (TypeError, ValueError):
            pass

    if _is_available(candidate):
        score += 0.15
    if _daily_rate(candidate) is not None:
        score += 0.15
    return round(min(1.0, max(0.0, score)), 2)


def build_evidence_rationale(
    unit_need: dict[str, Any],
    selected: dict[str, Any],
) -> str:
    """Factual one-liner from the same signals as ``score_need_match``. No invent."""
    hints = [
        str(h).strip()
        for h in (unit_need.get("equipment_hints") or [])
        if str(h).strip()
    ]
    label = hints[0] if hints else (
        wanted_categories(unit_need)[0] if wanted_categories(unit_need) else "need"
    )
    name = selected.get("name") or selected.get("asset_id") or "asset"
    cat = selected.get("category") or selected.get("equipment_type") or "unknown"
    bits = [f"category {cat}"]
    if selected.get("available") is True:
        bits.append("available=true")
    elif selected.get("available") is False:
        bits.append("available=false")
    else:
        status = str(selected.get("availability") or "").strip().lower()
        if status:
            bits.append(f"available={status}")
    rate = _daily_rate(selected)
    if rate is not None:
        bits.append(f"daily_rate={rate}")
    height = selected.get("platform_height")
    if height is not None:
        bits.append(f"platform_height={height}m")
    score = selected.get("match_score")
    if score is not None:
        bits.append(f"match_score={score}")
    return f"Matched {label} to {name} ({', '.join(bits)})."


def build_template_rationale(unit_need: dict[str, Any], selected: dict[str, Any]) -> str:
    return build_evidence_rationale(unit_need, selected)


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

        ranked = sorted(
            pool,
            key=lambda c: (score_need_match(need, c), *_tie_break(c)),
            reverse=True,
        )
        best = dict(ranked[0])
        best["rank"] = 1
        best["match_score"] = score_need_match(need, best)
        rationale = build_evidence_rationale(need, best)
        return {"selected": best, "rationale": rationale}
