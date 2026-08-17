"""Call 1 + Call 2 evaluation pack: predicted vs labeled expected outcomes.

Uses deterministic fixtures under ``tests/fixtures/eval/`` (EVAL_SEED=42).
CI isolation comes from ``tests/conftest.py`` (fake fleet, mock embedder, etc.).

BDD:
  Feature: Dual-hop recommender offline evaluation
    Scenario: Happy path hits gold category/asset and confidence band
    Scenario: No-match yields empty items and null confidence
    Scenario: ConfidenceScore equals recomputed formula
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.core.exceptions import NotFoundError
from app.pipelines.asset_candidate_filter import AssetCandidateFilter
from app.pipelines.booking_availability_filter import BookingAvailabilityFilter
from app.pipelines.predict_price_adapter import PredictPriceAdapter
from app.schemas.recommendations import DecomposedNeed
from app.services.indexing import IndexingIngestService
from app.services.project_knowledge_session import (
    ProjectKnowledgeSession,
    get_project_knowledge_registry,
)
from app.services.recommendations import RecommendationService
from app.services.session_recommend import SessionRecommendService
from tests.eval.metrics import (
    aggregate_report,
    budget_match,
    coverage,
    date_exact_match,
    hit_at_k,
    mape,
    mean_match_score,
    ndcg_at_k,
    need_set_prf,
    recompute_confidence_from_quote,
)

FIXTURES = Path(__file__).parent / "fixtures" / "eval"
CASES_PATH = FIXTURES / "call1_call2_cases.json"
FLEET_PATH = FIXTURES / "eval_fleet.json"

# CI gates (documented in docs/call1-call2-endpoint-process.md)
HAPPY_NEED_F1_MIN = 0.85
HAPPY_HIT_AT_1_MIN = 0.85
HAPPY_MEAN_CONFIDENCE_MIN = 0.50
BUDGET_INVENT_RATE_MAX = 0.0
PRICE_MAPE_MAX = 0.01
CONFIDENCE_CONSISTENCY_MIN = 1.0


def _load_pack() -> dict[str, Any]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def _load_fleet() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(FLEET_PATH.read_text(encoding="utf-8"))
    return list(data["assets"]), list(data["bookings"])


def _case_ids() -> list[str]:
    return [c["case_id"] for c in _load_pack()["cases"]]


def _case_by_id(case_id: str) -> dict[str, Any]:
    for case in _load_pack()["cases"]:
        if case["case_id"] == case_id:
            return case
    raise KeyError(case_id)


class _FixedDecomposer:
    def __init__(self, needs: list[DecomposedNeed]) -> None:
        self._needs = needs

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        del source_text
        return list(self._needs)


class _FixedPriceAdapter(PredictPriceAdapter):
    """Attach a fixed daily rate for deterministic price MAPE."""

    def __init__(self, daily_rate: float = 185.0) -> None:
        super().__init__()
        self._daily = float(daily_rate)

    def run(  # type: ignore[override]
        self,
        candidates: list | None = None,
        duration_days: float = 7.0,
        include_pricing: bool = True,
        distance_km: float | None = None,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        db=None,
    ) -> dict[str, list]:
        del distance_km, start_date, end_date, db
        pool = list(candidates or [])
        if not pool or not include_pricing:
            return {"priced_candidates": pool}
        priced: list[dict[str, Any]] = []
        days = float(duration_days or 7.0)
        for cand in pool:
            row = dict(cand)
            row["pricing"] = {
                "daily_rate": self._daily,
                "total_price": round(self._daily * max(1.0, days), 2),
                "currency": "SGD",
                "model_version": "eval-fixture",
                "was_clamped": False,
                "explanation": "eval fixed price",
            }
            priced.append(row)
        return {"priced_candidates": priced}


def _decomposer_from_case(case: dict[str, Any]) -> _FixedDecomposer:
    golds = case["call2_expected"]["gold_by_need"]
    needs = [
        DecomposedNeed(
            need_id=str(g.get("need_id") or f"need_{i}"),
            description=str(g.get("description") or "need"),
            equipment_hints=list(g.get("equipment_hints") or []),
            quantity=int(g.get("quantity") or 1),
        )
        for i, g in enumerate(golds, start=1)
    ]
    return _FixedDecomposer(needs)


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def _run_call1(case: dict[str, Any]) -> Any:
    """Call 1 ingest with stub-friendly text; uses IndexingIngestService."""
    # Use stub decomposer from factory (conftest NEED_DECOMPOSER=stub) for Call 1
    # natural extract; gold types come from project_text keywords.
    service = IndexingIngestService()
    c1 = case["call1_expected"]
    return service.ingest_from_project_spec(
        user_id=f"eval_{case['case_id']}",
        project_text=case["project_text"],
        start_date=_parse_date(c1.get("start_date")),
        end_date=_parse_date(c1.get("end_date")),
    )


def _run_call2(case: dict[str, Any], *, user_id: str, ingest_id: str) -> Any:
    assets, bookings = _load_fleet()
    c1 = case["call1_expected"]
    c2 = case["call2_expected"]
    start = _parse_date(c1.get("start_date"))
    end = _parse_date(c1.get("end_date"))

    # Ensure session exists (Call 2 prerequisite) with meta from labels + Call 1.
    reg = get_project_knowledge_registry()
    try:
        existing = reg.get(user_id, ingest_id)
        meta = dict(existing.meta or {})
    except NotFoundError:
        meta = {}
        reg.put(
            ProjectKnowledgeSession(
                user_id=user_id,
                ingest_id=ingest_id,
                document_store=InMemoryDocumentStore(),
                meta=meta,
            )
        )
        existing = reg.get(user_id, ingest_id)

    meta.setdefault("user_requirement_summary", case["project_text"][:500])
    meta.setdefault("indexing_ok", True)
    # Align confidence need_count with Call 2 gold (injected decomposer), not
    # only Call 1 stub expansion (which can split synonyms into extra needs).
    meta["needs_summary"] = [
        {
            "need_id": g.get("need_id"),
            "description": g.get("description"),
            "equipment_hints": g.get("equipment_hints") or [],
            "quantity": g.get("quantity") or 1,
        }
        for g in c2.get("gold_by_need") or []
    ]
    if start is not None:
        meta["tentative_start_date"] = start.isoformat()
    if end is not None:
        meta["tentative_end_date"] = end.isoformat()
    existing.meta = meta
    reg.put(existing)

    price_daily = 185.0
    for g in c2.get("gold_by_need") or []:
        if g.get("price_daily") is not None:
            price_daily = float(g["price_daily"])
            break

    recommend_svc = RecommendationService(
        decomposer=_decomposer_from_case(case),
        asset_filter=AssetCandidateFilter(assets=assets),
        availability_filter=BookingAvailabilityFilter(bookings=bookings),
        price_adapter=_FixedPriceAdapter(daily_rate=price_daily),
    )
    return SessionRecommendService(
        recommendation_service=recommend_svc,
        via_agent_graph=False,
    ).recommend(user_id=user_id, ingest_id=ingest_id)


def _score_case(case: dict[str, Any]) -> dict[str, Any]:
    c1_exp = case["call1_expected"]
    c2_exp = case["call2_expected"]
    kind = case.get("kind") or "happy"

    ingest = _run_call1(case)
    user_id = ingest.user_id
    ingest_id = ingest.ingest_id

    # --- Call 1 metrics ---
    pred_hints: list[str] = []
    for n in ingest.needs_summary or []:
        pred_hints.extend(list(n.equipment_hints or []))
        if n.description:
            pred_hints.append(n.description)
    prf = need_set_prf(pred_hints, c1_exp.get("equipment_types") or [])

    start_ok = date_exact_match(
        ingest.tentative_start_date.isoformat()
        if ingest.tentative_start_date
        else None,
        c1_exp.get("start_date"),
    )
    end_ok = date_exact_match(
        ingest.tentative_end_date.isoformat() if ingest.tentative_end_date else None,
        c1_exp.get("end_date"),
    )
    pred_budget = (
        float(ingest.expected_budget.amount)
        if ingest.expected_budget is not None
        else None
    )
    bstat = budget_match(pred_budget, c1_exp.get("budget_amount"))

    summary_ok = bool((ingest.user_requirement_summary or "").strip())
    ingest_ok = bool(ingest_id and str(ingest_id).startswith("ing_"))

    # --- Call 2 metrics ---
    quote = _run_call2(case, user_id=user_id, ingest_id=ingest_id)
    items = list(quote.items or [])
    need_count = int(c2_exp.get("need_count") or 1)
    golds = list(c2_exp.get("gold_by_need") or [])

    if c2_exp.get("expect_empty_items"):
        hit_flags = [len(items) == 0]
        ndcgs = [1.0 if len(items) == 0 else 0.0]
        price_mapes: list[float] = []
    else:
        hit_flags = []
        ndcgs = []
        price_mapes = []
        # Evaluate each gold need against full item list (MVP returns one per need)
        for gold in golds:
            hit_flags.append(
                hit_at_k(
                    items,
                    gold_asset_ids=gold.get("gold_asset_ids") or [],
                    gold_categories=gold.get("gold_categories") or [],
                    k=max(1, len(items) or 1),
                )
            )
            ndcgs.append(
                ndcg_at_k(
                    items,
                    gold_asset_ids=gold.get("gold_asset_ids") or [],
                    gold_categories=gold.get("gold_categories") or [],
                    k=max(1, len(items) or 1),
                )
            )
            prefer_not = set(gold.get("prefer_not_asset_ids") or [])
            if prefer_not and items:
                top_id = str(items[0].equipment.id or "")
                # Soft: preferred available id should not be the booked one when alternatives exist
                if top_id in prefer_not and len(gold.get("gold_asset_ids") or []) > 1:
                    hit_flags[-1] = False
            expected_price = gold.get("price_daily")
            for it in items:
                m = mape(it.mlPredictedPrice, expected_price)
                if m is not None and m != float("inf"):
                    price_mapes.append(m)

    hit_rate = sum(1 for h in hit_flags if h) / max(1, len(hit_flags))
    ndcg_mean = sum(ndcgs) / max(1, len(ndcgs))
    price_mape_mean = (
        sum(price_mapes) / len(price_mapes) if price_mapes else None
    )
    cov = coverage(len(items), need_count)
    # Match map_recommend_to_quote: need_count from session needs_summary when present
    session = get_project_knowledge_registry().get(user_id, ingest_id)
    meta = session.meta or {}
    needs_meta = (
        meta.get("needs_summary") if isinstance(meta.get("needs_summary"), list) else []
    )
    conf_need_count = len(needs_meta) if needs_meta else len(golds) or need_count
    conf_has_dates = bool(
        meta.get("tentative_start_date") and meta.get("tentative_end_date")
    ) or (quote.days is not None)
    recomputed = recompute_confidence_from_quote(
        quote, need_count=max(1, conf_need_count), has_dates=conf_has_dates
    )
    actual_conf = quote.confidenceScore
    if actual_conf is None and recomputed is None:
        conf_consistent = 1.0
    elif actual_conf is not None and recomputed is not None:
        conf_consistent = (
            1.0 if abs(float(actual_conf) - float(recomputed)) < 1e-9 else 0.0
        )
    else:
        conf_consistent = 0.0

    return {
        "case_id": case["case_id"],
        "kind": kind,
        "ingest_ok": 1.0 if ingest_ok else 0.0,
        "summary_ok": 1.0 if summary_ok else 0.0,
        "need_f1": prf["f1"],
        "need_precision": prf["precision"],
        "need_recall": prf["recall"],
        "date_start_ok": 1.0 if start_ok else 0.0,
        "date_end_ok": 1.0 if end_ok else 0.0,
        "budget_match": 1.0 if bstat["match"] else 0.0,
        "budget_invented": 1.0 if bstat["invented"] else 0.0,
        "hit_at_1": bool(hit_rate >= 1.0 if c2_exp.get("hit_at_1_required") else True),
        "hit_at_1_rate": hit_rate,
        "coverage": cov,
        "ndcg": ndcg_mean,
        "mean_match_score": mean_match_score(items),
        "confidence": actual_conf,
        "confidence_recomputed": recomputed,
        "confidence_consistent": conf_consistent,
        "price_mape": price_mape_mean,
        "item_count": len(items),
        "expect_empty": bool(c2_exp.get("expect_empty_items")),
        "confidence_min": c2_exp.get("confidence_min"),
    }


@pytest.mark.parametrize("case_id", _case_ids())
def test_eval_case_predicted_vs_actual(case_id: str) -> None:
    case = _case_by_id(case_id)
    result = _score_case(case)
    c2 = case["call2_expected"]

    assert result["ingest_ok"] == 1.0, f"{case_id}: Call 1 must succeed"
    assert result["summary_ok"] == 1.0, f"{case_id}: summary must be non-empty"
    assert result["confidence_consistent"] == 1.0, (
        f"{case_id}: confidenceScore {result['confidence']} != "
        f"recomputed {result['confidence_recomputed']}"
    )
    assert result["budget_invented"] == 0.0 or not case["call1_expected"].get(
        "must_not_invent_budget"
    ), f"{case_id}: must not invent budget"

    if c2.get("expect_empty_items"):
        assert result["item_count"] == 0, f"{case_id}: expected empty items"
        assert result["confidence"] is None, f"{case_id}: confidence must be null"
        return

    if c2.get("hit_at_1_required"):
        assert result["hit_at_1_rate"] >= 1.0, (
            f"{case_id}: Hit@1 failed (rate={result['hit_at_1_rate']})"
        )
    conf_min = c2.get("confidence_min")
    if conf_min is not None:
        assert result["confidence"] is not None, f"{case_id}: missing confidence"
        assert float(result["confidence"]) + 1e-9 >= float(conf_min), (
            f"{case_id}: confidence {result['confidence']} < min {conf_min}"
        )
    if result["price_mape"] is not None:
        assert result["price_mape"] <= PRICE_MAPE_MAX, (
            f"{case_id}: price MAPE {result['price_mape']}"
        )


def test_eval_pack_macro_thresholds() -> None:
    """Aggregate gates across the seeded pack (happy vs no-match)."""
    pack = _load_pack()
    results = [_score_case(c) for c in pack["cases"]]
    happy = [r for r in results if r["kind"] == "happy"]
    no_match = [r for r in results if r["kind"] == "no_match"]
    report = aggregate_report(results)

    assert report["cases"] == len(pack["cases"])
    assert report["confidence_consistency_rate"] == CONFIDENCE_CONSISTENCY_MIN

    invent_rate = sum(r["budget_invented"] for r in results) / max(1, len(results))
    # Only count invent when label forbids it
    forbidden = [
        r
        for r, c in zip(results, pack["cases"], strict=True)
        if c["call1_expected"].get("must_not_invent_budget")
    ]
    if forbidden:
        inv = sum(r["budget_invented"] for r in forbidden) / len(forbidden)
        assert inv <= BUDGET_INVENT_RATE_MAX

    happy_f1 = sum(r["need_f1"] for r in happy) / max(1, len(happy))
    happy_hit = sum(r["hit_at_1_rate"] for r in happy) / max(1, len(happy))
    happy_conf_vals = [r["confidence"] for r in happy if r["confidence"] is not None]
    happy_conf = sum(happy_conf_vals) / len(happy_conf_vals) if happy_conf_vals else 0.0

    assert happy_f1 + 1e-9 >= HAPPY_NEED_F1_MIN, f"happy need F1 {happy_f1}"
    assert happy_hit + 1e-9 >= HAPPY_HIT_AT_1_MIN, f"happy Hit@1 {happy_hit}"
    assert happy_conf + 1e-9 >= HAPPY_MEAN_CONFIDENCE_MIN, f"happy conf {happy_conf}"

    for r in no_match:
        assert r["item_count"] == 0
        assert r["confidence"] is None

    # Calibration-lite: high-confidence cases should not underperform none/empty
    bins = report["confidence_bin_hit_rate"]
    if bins.get("high") is not None and bins.get("none") is not None:
        assert bins["high"] >= bins["none"]

    # Silence unused invent_rate when no forbidden cases
    del invent_rate
