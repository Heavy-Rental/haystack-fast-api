"""Predicted-vs-actual metrics for Call 1 / Call 2 evaluation packs.

Pure functions only — no network, no LLM. Used by pytest eval suites and
documented in ``docs/call1-call2-endpoint-process.md``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from app.schemas.recommend_quote import AssetRecommendResponse, RecommendQuoteItem
from app.services.session_recommend import compute_confidence_score

# Canonical model categories (lowercase) used for set metrics.
_CANONICAL_ALIASES: dict[str, str] = {
    "boom lift": "boom lift",
    "boom": "boom lift",
    "aerial": "boom lift",
    "scissor lift": "scissor lift",
    "scissors lift": "scissor lift",
    "scissor": "scissor lift",
    "scissors": "scissor lift",
    "elevated": "scissor lift",
    "forklift": "forklift",
    "fork lift": "forklift",
    "fork": "forklift",
    "warehouse": "forklift",
    "excavator": "excavator",
    "excavate": "excavator",
    "trench": "excavator",
}


def normalize_equipment_type(text: str | None) -> str | None:
    """Map free-text hint / display name to a canonical model category."""
    if text is None:
        return None
    raw = str(text).strip().lower()
    if not raw:
        return None
    if raw in _CANONICAL_ALIASES:
        return _CANONICAL_ALIASES[raw]
    # Longest alias match (prefer multi-word).
    best: str | None = None
    best_len = -1
    for alias, canon in _CANONICAL_ALIASES.items():
        if alias in raw and len(alias) > best_len:
            best = canon
            best_len = len(alias)
    return best


def normalize_type_set(values: Iterable[str | None]) -> set[str]:
    out: set[str] = set()
    for v in values:
        canon = normalize_equipment_type(v)
        if canon:
            out.add(canon)
    return out


def need_set_prf(
    predicted_hints: Iterable[str | None],
    gold_types: Iterable[str | None],
) -> dict[str, float]:
    """Precision / recall / F1 over canonical equipment type sets."""
    pred = normalize_type_set(predicted_hints)
    gold = normalize_type_set(gold_types)
    if not pred and not gold:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not pred:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    if not gold:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp = len(pred & gold)
    precision = tp / len(pred)
    recall = tp / len(gold)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def date_exact_match(
    predicted: str | None,
    gold: str | None,
) -> bool:
    """ISO date string equality; both null counts as match."""
    p = str(predicted).strip()[:10] if predicted is not None else None
    g = str(gold).strip()[:10] if gold is not None else None
    if not p:
        p = None
    if not g:
        g = None
    return p == g


def budget_match(
    predicted_amount: float | None,
    gold_amount: float | None,
    *,
    tol: float = 1.0,
) -> dict[str, Any]:
    """Budget exact/near match and invent detection when gold is null."""
    if gold_amount is None:
        invented = predicted_amount is not None
        return {
            "match": not invented,
            "invented": invented,
            "abs_error": None,
        }
    if predicted_amount is None:
        return {"match": False, "invented": False, "abs_error": None}
    err = abs(float(predicted_amount) - float(gold_amount))
    return {
        "match": err <= tol,
        "invented": False,
        "abs_error": err,
    }


def hit_at_k(
    items: Sequence[Any],
    *,
    gold_asset_ids: Sequence[str] | None = None,
    gold_categories: Sequence[str] | None = None,
    k: int = 1,
) -> bool:
    """True if any of the top-k items matches gold id or category."""
    gold_ids = {str(x).strip() for x in (gold_asset_ids or []) if str(x).strip()}
    gold_cats = normalize_type_set(gold_categories or [])
    if not gold_ids and not gold_cats:
        return False
    for item in list(items)[: max(1, int(k))]:
        eq_id, cat = _item_id_and_category(item)
        if eq_id and eq_id in gold_ids:
            return True
        if cat and normalize_equipment_type(cat) in gold_cats:
            return True
    return False


def _item_id_and_category(item: Any) -> tuple[str | None, str | None]:
    if isinstance(item, RecommendQuoteItem):
        eq = item.equipment
        return (
            str(eq.id).strip() if eq and eq.id is not None else None,
            str(eq.category) if eq and eq.category else None,
        )
    if isinstance(item, dict):
        eq = item.get("equipment") or {}
        if isinstance(eq, dict):
            eid = eq.get("id")
            cat = eq.get("category") or eq.get("name")
            return (
                str(eid).strip() if eid is not None else None,
                str(cat) if cat else None,
            )
        eid = item.get("asset_id") or item.get("id")
        cat = item.get("category") or item.get("equipment_type")
        return (
            str(eid).strip() if eid is not None else None,
            str(cat) if cat else None,
        )
    return None, None


def graded_relevance(
    item: Any,
    *,
    gold_asset_ids: Sequence[str] | None = None,
    gold_categories: Sequence[str] | None = None,
) -> float:
    """1.0 exact asset id, 0.5 same category, else 0.0."""
    gold_ids = {str(x).strip() for x in (gold_asset_ids or []) if str(x).strip()}
    gold_cats = normalize_type_set(gold_categories or [])
    eq_id, cat = _item_id_and_category(item)
    if eq_id and eq_id in gold_ids:
        return 1.0
    if cat and normalize_equipment_type(cat) in gold_cats:
        return 0.5
    return 0.0


def ndcg_at_k(
    items: Sequence[Any],
    *,
    gold_asset_ids: Sequence[str] | None = None,
    gold_categories: Sequence[str] | None = None,
    k: int = 1,
) -> float:
    """nDCG@k with graded relevance (exact=1, category=0.5)."""
    width = max(1, int(k))
    rels = [
        graded_relevance(
            item,
            gold_asset_ids=gold_asset_ids,
            gold_categories=gold_categories,
        )
        for item in list(items)[:width]
    ]
    if not rels:
        return 0.0
    dcg = 0.0
    for i, rel in enumerate(rels):
        dcg += rel / math.log2(i + 2)
    ideal = sorted(
        [
            graded_relevance(
                item,
                gold_asset_ids=gold_asset_ids,
                gold_categories=gold_categories,
            )
            for item in items
        ]
        or [0.0],
        reverse=True,
    )[:width]
    # Ideal from gold alone when list short: max possible grades
    if not any(ideal):
        # still compute ideal from known gold presence
        ideal_grades = ([1.0] if gold_asset_ids else []) + (
            [0.5] if gold_categories and not gold_asset_ids else []
        )
        if not ideal_grades and gold_categories:
            ideal_grades = [0.5]
        ideal = (ideal_grades + [0.0] * width)[:width]
        ideal = sorted(ideal, reverse=True)
    idcg = 0.0
    for i, rel in enumerate(ideal):
        idcg += rel / math.log2(i + 2)
    if idcg <= 0:
        return 0.0
    return round(dcg / idcg, 4)


def coverage(item_count: int, need_count: int) -> float:
    needs = max(1, int(need_count or 0))
    return round(min(1.0, float(item_count) / needs), 4)


def mape(predicted: float | None, actual: float | None) -> float | None:
    """Mean absolute percentage error for a single price pair."""
    if predicted is None or actual is None:
        return None
    a = float(actual)
    if a == 0:
        return None if float(predicted) == 0 else float("inf")
    return abs(float(predicted) - a) / abs(a)


def mean_match_score(items: Sequence[RecommendQuoteItem | dict[str, Any]]) -> float | None:
    scores: list[float] = []
    for item in items:
        if isinstance(item, RecommendQuoteItem):
            if item.matchScore is not None:
                scores.append(float(item.matchScore))
        elif isinstance(item, dict) and item.get("matchScore") is not None:
            scores.append(float(item["matchScore"]))
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def recompute_confidence_from_quote(
    quote: AssetRecommendResponse | dict[str, Any],
    *,
    need_count: int,
    has_dates: bool | None = None,
) -> float | None:
    """Recompute confidenceScore from quote items (drift guard)."""
    if isinstance(quote, AssetRecommendResponse):
        items = list(quote.items or [])
        days = quote.days
        conf_has_dates = has_dates if has_dates is not None else (days is not None and days > 0)
        return compute_confidence_score(
            items=items,
            need_count=need_count,
            has_dates=bool(conf_has_dates),
        )
    raw_items = list(quote.get("items") or [])
    items = [RecommendQuoteItem.model_validate(x) if isinstance(x, dict) else x for x in raw_items]
    if has_dates is None:
        has_dates = quote.get("days") is not None
    return compute_confidence_score(
        items=items,
        need_count=need_count,
        has_dates=bool(has_dates),
    )


def confidence_bin(score: float | None) -> str:
    if score is None:
        return "none"
    if score < 0.40:
        return "low"
    if score < 0.70:
        return "medium"
    return "high"


def aggregate_report(case_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Macro averages + confidence-bin hit rates for a pack run."""
    n = len(case_results)
    if n == 0:
        return {"cases": 0}

    def _avg(key: str) -> float | None:
        vals = [
            float(r[key])
            for r in case_results
            if r.get(key) is not None and not (isinstance(r[key], float) and math.isnan(r[key]))
        ]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 4)

    bins: dict[str, list[bool]] = {"none": [], "low": [], "medium": [], "high": []}
    for r in case_results:
        b = confidence_bin(r.get("confidence"))
        hit = bool(r.get("hit_at_1"))
        bins.setdefault(b, []).append(hit)

    bin_hit_rate = {
        name: (round(sum(1 for x in hits if x) / len(hits), 4) if hits else None)
        for name, hits in bins.items()
    }

    return {
        "cases": n,
        "mean_need_f1": _avg("need_f1"),
        "mean_hit_at_1": _avg("hit_at_1_rate"),
        "mean_coverage": _avg("coverage"),
        "mean_confidence": _avg("confidence"),
        "mean_match_score": _avg("mean_match_score"),
        "mean_ndcg": _avg("ndcg"),
        "mean_price_mape": _avg("price_mape"),
        "budget_invent_rate": _avg("budget_invented"),
        "confidence_consistency_rate": _avg("confidence_consistent"),
        "confidence_bin_hit_rate": bin_hit_rate,
    }
