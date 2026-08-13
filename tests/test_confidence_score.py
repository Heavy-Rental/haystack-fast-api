"""Evidence-based Call 2 confidenceScore."""

from __future__ import annotations

from app.schemas.recommend_quote import EquipmentQuote, RecommendQuoteItem
from app.services.session_recommend import compute_confidence_score


def _item(
    *,
    eq_id: str = "27",
    available: bool | None = True,
    match: float = 1.0,
    price: float | None = 175.0,
) -> RecommendQuoteItem:
    return RecommendQuoteItem(
        rankOrder=1,
        matchScore=match,
        mlPredictedPrice=price,
        equipment=EquipmentQuote(id=eq_id, available=available),
    )


def test_confidence_none_when_no_items() -> None:
    assert compute_confidence_score(items=[], need_count=1, has_dates=False) is None


def test_confidence_full_evidence() -> None:
    score = compute_confidence_score(
        items=[_item(), _item(eq_id="28")],
        need_count=2,
        has_dates=True,
    )
    # 0.30 + 0.20 + 0.20 + 0.15 + 0.10 + 0.05 = 1.00 → cap 0.99
    assert score == 0.99


def test_confidence_partial_coverage_no_dates() -> None:
    score = compute_confidence_score(
        items=[_item(available=None)],
        need_count=2,
        has_dates=False,
    )
    # coverage 0.5*0.30=0.15, match 0.20, live 0.20, avail 0, priced 0.10
    assert score == 0.65


def test_confidence_seed_id_not_live() -> None:
    score = compute_confidence_score(
        items=[_item(eq_id="AST-FL-002", available=False, price=None)],
        need_count=1,
        has_dates=False,
    )
    # coverage 0.30, match 0.20, live 0, avail 0, priced 0
    assert score == 0.50
