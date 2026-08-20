"""Call 2 quote collapses unit-need siblings that share equipment.id (FR-P-013)."""

from __future__ import annotations

from datetime import date

from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.schemas.recommend_quote import EquipmentQuote, RecommendQuoteItem
from app.schemas.recommendations import (
    NeedResult,
    PricingPayload,
    RecommendationItem,
    RecommendFromProjectSpecResponse,
)
from app.services.project_knowledge_session import ProjectKnowledgeSession
from app.services.session_recommend import (
    collapse_duplicate_equipment_quotes,
    map_recommend_to_quote,
)


def _item(
    *,
    need_id: str,
    eq_id: str,
    quantity: int = 1,
    line_total: float | None = 1295.0,
    rank: int = 1,
    price: float | None = 185.0,
) -> RecommendQuoteItem:
    return RecommendQuoteItem(
        rankOrder=rank,
        matchScore=1.0,
        reason="fixture",
        lineTotal=line_total,
        quantity=quantity,
        needId=need_id,
        mlPredictedPrice=price,
        equipment=EquipmentQuote(id=eq_id, name="Scissors Lift", baseDailyRate=price),
    )


def _session() -> ProjectKnowledgeSession:
    return ProjectKnowledgeSession(
        user_id="u1",
        ingest_id="ing_1",
        document_store=InMemoryDocumentStore(),
        meta={"user_requirement_summary": "Need two scissors lifts"},
    )


def test_collapse_same_equipment_unit_needs() -> None:
    collapsed = collapse_duplicate_equipment_quotes(
        [
            _item(need_id="need_1__u1", eq_id="17", rank=1),
            _item(need_id="need_1__u2", eq_id="17", rank=2),
        ]
    )
    assert len(collapsed) == 1
    item = collapsed[0]
    assert item.needId == "need_1"
    assert item.quantity == 2
    assert item.lineTotal == 2590.0
    assert item.equipment.id == "17"
    assert item.mlPredictedPrice == 185.0
    assert item.rankOrder == 1


def test_collapse_keeps_distinct_equipment_under_same_parent() -> None:
    collapsed = collapse_duplicate_equipment_quotes(
        [
            _item(need_id="need_1__u1", eq_id="17", rank=1),
            _item(need_id="need_1__u2", eq_id="18", rank=2),
        ]
    )
    assert [(row.needId, row.equipment.id, row.quantity) for row in collapsed] == [
        ("need_1__u1", "17", 1),
        ("need_1__u2", "18", 1),
    ]


def test_collapse_three_same_equipment_unit_needs() -> None:
    collapsed = collapse_duplicate_equipment_quotes(
        [
            _item(need_id="need_1__u1", eq_id="17", rank=1, line_total=100.0),
            _item(need_id="need_1__u2", eq_id="17", rank=2, line_total=100.0),
            _item(need_id="need_1__u3", eq_id="17", rank=3, line_total=100.0),
        ]
    )
    assert len(collapsed) == 1
    item = collapsed[0]
    assert item.needId == "need_1"
    assert item.quantity == 3
    assert item.lineTotal == 300.0
    assert item.equipment.id == "17"
    assert item.rankOrder == 1


def test_collapse_parent_id_does_not_split_on_underscore() -> None:
    collapsed = collapse_duplicate_equipment_quotes(
        [
            _item(need_id="need_soft_clay__u1", eq_id="17", rank=1),
            _item(need_id="need_soft_clay__u2", eq_id="17", rank=2),
        ]
    )
    assert len(collapsed) == 1
    assert collapsed[0].needId == "need_soft_clay"
    assert collapsed[0].quantity == 2


def test_collapse_does_not_merge_same_equipment_across_needs() -> None:
    collapsed = collapse_duplicate_equipment_quotes(
        [
            _item(need_id="need_access", eq_id="17", rank=1),
            _item(need_id="need_earthwork", eq_id="17", rank=2),
        ]
    )
    assert [row.needId for row in collapsed] == ["need_access", "need_earthwork"]
    assert all(row.quantity == 1 for row in collapsed)


def test_collapse_leaves_quantity_one_need_unchanged() -> None:
    original = _item(need_id="need_1", eq_id="17")
    collapsed = collapse_duplicate_equipment_quotes([original])
    assert len(collapsed) == 1
    assert collapsed[0].needId == "need_1"
    assert collapsed[0].quantity == 1
    assert collapsed[0].lineTotal == 1295.0


def test_collapse_mixed_unit_needs_and_other_need() -> None:
    collapsed = collapse_duplicate_equipment_quotes(
        [
            _item(need_id="need_1__u1", eq_id="17", rank=1, line_total=100.0),
            _item(need_id="need_1__u2", eq_id="17", rank=2, line_total=100.0),
            _item(need_id="need_2", eq_id="99", rank=3, line_total=50.0),
        ]
    )
    assert len(collapsed) == 2
    assert collapsed[0].needId == "need_1"
    assert collapsed[0].quantity == 2
    assert collapsed[0].lineTotal == 200.0
    assert collapsed[0].rankOrder == 1
    assert collapsed[1].needId == "need_2"
    assert collapsed[1].quantity == 1
    assert collapsed[1].rankOrder == 2


def test_map_recommend_collapses_same_fleet_id_unit_needs() -> None:
    selected = RecommendationItem(
        equipment_type="Scissors Lift",
        asset_id="Genie GS-1930",
        fleet_id=17,
        name="Genie GS-1930",
        rank=1,
        pricing=PricingPayload(daily_rate=185.0, total_price=1295.0),
    )
    quote = map_recommend_to_quote(
        user_id="u1",
        ingest_id="ing_1",
        query=None,
        recommend=RecommendFromProjectSpecResponse(
            recommendation_id="rec_test",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
            results_by_need=[
                NeedResult(need_id="need_1__u1", item=selected, warnings=[]),
                NeedResult(need_id="need_1__u2", item=selected, warnings=[]),
                NeedResult(need_id="need_1__u3", item=selected, warnings=[]),
            ],
        ),
        session=_session(),
        db=None,
    )
    assert len(quote.items) == 1
    item = quote.items[0]
    assert item.needId == "need_1"
    assert item.quantity == 3
    assert item.equipment.id == "17"
    assert item.lineTotal == 3885.0
    assert quote.estimatedTotal == 3885.0
    assert item.mlPredictedPrice == 185.0
    assert item.rankOrder == 1
