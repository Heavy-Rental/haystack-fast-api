"""Unit tests for offline Call 1 / Call 2 evaluation metrics."""

from __future__ import annotations

from app.schemas.recommend_quote import EquipmentQuote, RecommendQuoteItem
from tests.eval.metrics import (
    aggregate_report,
    budget_match,
    confidence_bin,
    coverage,
    date_exact_match,
    hit_at_k,
    mape,
    mean_match_score,
    ndcg_at_k,
    need_set_prf,
    normalize_equipment_type,
    recompute_confidence_from_quote,
)


def test_normalize_equipment_type_aliases() -> None:
    assert normalize_equipment_type("Scissors Lift") == "scissor lift"
    assert normalize_equipment_type("fork lift") == "forklift"
    assert normalize_equipment_type("BOOM") == "boom lift"
    assert normalize_equipment_type("submarine") is None


def test_need_set_f1_perfect_and_partial() -> None:
    perfect = need_set_prf(["scissor lift"], ["scissors lift"])
    assert perfect["f1"] == 1.0
    partial = need_set_prf(["scissor lift", "excavator"], ["scissor lift"])
    assert partial["recall"] == 1.0
    assert partial["precision"] == 0.5


def test_need_set_empty_both() -> None:
    assert need_set_prf([], [])["f1"] == 1.0


def test_date_exact_match() -> None:
    assert date_exact_match("2026-09-01", "2026-09-01")
    assert date_exact_match(None, None)
    assert not date_exact_match("2026-09-01", None)


def test_budget_match_and_invent() -> None:
    assert budget_match(12000, 12000)["match"] is True
    assert budget_match(100.0, None)["invented"] is True
    assert budget_match(None, None)["invented"] is False
    assert budget_match(None, 5000)["match"] is False


def test_hit_at_k_and_ndcg() -> None:
    items = [
        RecommendQuoteItem(
            rankOrder=1,
            matchScore=1.0,
            mlPredictedPrice=185.0,
            equipment=EquipmentQuote(id="AST-SL-002", category="Scissors Lift"),
        )
    ]
    assert hit_at_k(
        items,
        gold_asset_ids=["AST-SL-001", "AST-SL-002"],
        gold_categories=["Scissors Lift"],
        k=1,
    )
    assert ndcg_at_k(
        items,
        gold_asset_ids=["AST-SL-002"],
        gold_categories=["Scissors Lift"],
        k=1,
    ) == 1.0


def test_hit_at_k_category_only() -> None:
    items = [
        {
            "equipment": {"id": "AST-X", "category": "Excavator"},
            "matchScore": 0.8,
        }
    ]
    assert hit_at_k(items, gold_categories=["excavator"], k=1)


def test_coverage_mape_mean_match() -> None:
    assert coverage(1, 2) == 0.5
    assert coverage(3, 2) == 1.0
    assert mape(185.0, 185.0) == 0.0
    assert mape(None, 185.0) is None
    items = [
        RecommendQuoteItem(
            matchScore=1.0,
            equipment=EquipmentQuote(id="1"),
        ),
        RecommendQuoteItem(
            matchScore=0.5,
            equipment=EquipmentQuote(id="2"),
        ),
    ]
    assert mean_match_score(items) == 0.75


def test_recompute_confidence_matches_formula() -> None:
    items = [
        RecommendQuoteItem(
            matchScore=1.0,
            mlPredictedPrice=185.0,
            equipment=EquipmentQuote(id="27", available=True),
        )
    ]
    quote = {
        "items": [
            {
                "matchScore": 1.0,
                "mlPredictedPrice": 185.0,
                "equipment": {"id": "27", "available": True},
            }
        ],
        "days": 14,
    }
    score = recompute_confidence_from_quote(quote, need_count=1, has_dates=True)
    assert score == 0.99


def test_confidence_bin_and_aggregate() -> None:
    assert confidence_bin(None) == "none"
    assert confidence_bin(0.2) == "low"
    assert confidence_bin(0.55) == "medium"
    assert confidence_bin(0.9) == "high"
    report = aggregate_report(
        [
            {
                "need_f1": 1.0,
                "hit_at_1_rate": 1.0,
                "hit_at_1": True,
                "coverage": 1.0,
                "confidence": 0.8,
                "mean_match_score": 1.0,
                "ndcg": 1.0,
                "price_mape": 0.0,
                "budget_invented": 0.0,
                "confidence_consistent": 1.0,
            },
            {
                "need_f1": 0.0,
                "hit_at_1_rate": 0.0,
                "hit_at_1": False,
                "coverage": 0.0,
                "confidence": None,
                "mean_match_score": None,
                "ndcg": 0.0,
                "price_mape": None,
                "budget_invented": 0.0,
                "confidence_consistent": 1.0,
            },
        ]
    )
    assert report["cases"] == 2
    assert report["mean_hit_at_1"] == 0.5
    assert report["confidence_bin_hit_rate"]["high"] == 1.0
    assert report["confidence_bin_hit_rate"]["none"] == 0.0
