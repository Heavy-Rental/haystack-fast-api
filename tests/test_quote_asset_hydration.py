"""Call 2 quote equipment is hydrated from the assets table."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.pipelines.asset_candidate_filter import AssetCandidateFilter
from app.pipelines.booking_availability_filter import BookingAvailabilityFilter
from app.schemas.recommendations import (
    DecomposedNeed,
    NeedResult,
    PricingPayload,
    RecommendFromProjectSpecResponse,
    RecommendationItem,
)
from app.services.project_knowledge_session import ProjectKnowledgeSession
from app.services.recommendations import RecommendationService
from app.services.session_recommend import map_recommend_to_quote


def _session() -> ProjectKnowledgeSession:
    return ProjectKnowledgeSession(
        user_id="u1",
        ingest_id="ing_1",
        document_store=InMemoryDocumentStore(),
        meta={"user_requirement_summary": "Need scissors lift"},
    )


def _recommend_with(item: RecommendationItem) -> RecommendFromProjectSpecResponse:
    return RecommendFromProjectSpecResponse(
        recommendation_id="rec_test",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
        results_by_need=[NeedResult(need_id="need_1", item=item, warnings=[])],
    )


def _db_for_asset(
    asset_row: tuple,
    *,
    bookings: list | None = None,
) -> MagicMock:
    db = MagicMock()

    def execute(stmt, **kwargs):
        result = MagicMock()
        text = str(stmt).lower()
        if "booking" in text:
            result.first.return_value = None
            result.all.return_value = list(bookings or [])
        else:
            result.first.return_value = asset_row
            result.all.return_value = [asset_row]
        return result

    db.execute.side_effect = execute
    return db


def test_quote_equipment_id_is_assets_pk_when_row_found() -> None:
    """Spring FKs recommendation_items.asset_id to assets.id, not assets.name."""
    db = _db_for_asset(
        (
            17,
            "Genie GS-1930",
            "Scissors Lift",
            "GOOD",
            300,
            8.0,
            120.0,
            280.0,
            "8m indoor scissor",
            2022,
            "Tuas Yard",
        )
    )

    quote = map_recommend_to_quote(
        user_id="u1",
        ingest_id="ing_1",
        query=None,
        recommend=_recommend_with(
            RecommendationItem(
                equipment_type="Fork Lift",
                asset_id="AST-FL-002",
                fleet_id=None,
                name="AST-FL-002",
                rank=1,
                pricing=PricingPayload(daily_rate=105.16, total_price=736.12),
                availability="available",
            )
        ),
        session=_session(),
        db=db,
    )
    assert len(quote.items) == 1
    equipment = quote.items[0].equipment
    assert equipment.id == "17"
    assert equipment.name == "Genie GS-1930"
    assert equipment.category == "Scissors Lift"
    assert equipment.capacity == 300.0
    assert equipment.purchaseYear == 2022
    assert equipment.location == "Tuas Yard"
    assert equipment.desc == "8m indoor scissor"
    assert equipment.available is True
    assert equipment.platformHeight == 8.0
    assert equipment.tags == []
    assert equipment.extra.get("capacity") == 300.0
    dumped = equipment.model_dump()
    assert dumped["platformHeight"] == 8.0


def test_quote_live_sql_drops_seed_id_when_assets_row_missing() -> None:
    """Live fleet must not emit AST-* when the assets table has no match."""
    db = MagicMock()
    result = MagicMock()
    result.first.return_value = None
    db.execute.return_value = result

    quote = map_recommend_to_quote(
        user_id="u1",
        ingest_id="ing_1",
        query=None,
        recommend=_recommend_with(
            RecommendationItem(
                equipment_type="Fork Lift",
                asset_id="AST-FL-002",
                rank=1,
                pricing=PricingPayload(daily_rate=105.16, total_price=736.12),
            )
        ),
        session=_session(),
        db=db,
        require_table_row=True,
    )
    assert quote.items == []
    assert any("AST-FL-002" in w and "omitted" in w for w in quote.warnings)


def test_quote_keeps_seed_id_when_assets_row_missing() -> None:
    db = MagicMock()
    result = MagicMock()
    result.first.return_value = None
    db.execute.return_value = result

    quote = map_recommend_to_quote(
        user_id="u1",
        ingest_id="ing_1",
        query=None,
        recommend=_recommend_with(
            RecommendationItem(
                equipment_type="Fork Lift",
                asset_id="AST-FL-002",
                rank=1,
                pricing=PricingPayload(daily_rate=105.16, total_price=736.12),
            )
        ),
        session=_session(),
        db=db,
    )
    assert quote.items[0].equipment.id == "AST-FL-002"
    assert quote.items[0].equipment.name == "Fork Lift"


def test_quote_omits_platform_height_for_forklift() -> None:
    db = _db_for_asset(
        (
            27,
            "Hyster H4.2FT Forklift",
            "Fork Lift",
            "GOOD",
            4200,
            4.0,
            100.0,
            240.0,
            "4.2t counterbalance",
            2021,
            "Tuas",
        )
    )
    quote = map_recommend_to_quote(
        user_id="u1",
        ingest_id="ing_1",
        query=None,
        recommend=_recommend_with(
            RecommendationItem(
                equipment_type="Fork Lift",
                asset_id="Hyster H4.2FT Forklift",
                fleet_id=27,
                rank=1,
                pricing=PricingPayload(daily_rate=175.0, total_price=1225.0),
            )
        ),
        session=_session(),
        db=db,
    )
    equipment = quote.items[0].equipment
    assert equipment.platformHeight is None
    assert "platformHeight" not in equipment.model_dump()


def test_quote_available_false_when_live_hold_overlaps() -> None:
    db = _db_for_asset(
        (
            27,
            "Hyster H4.2FT Forklift",
            "Fork Lift",
            "GOOD",
            4200,
            None,
            100.0,
            240.0,
            "4.2t counterbalance",
            2021,
            None,
        ),
        bookings=[(date(2026, 9, 1), date(2026, 9, 30))],
    )
    quote = map_recommend_to_quote(
        user_id="u1",
        ingest_id="ing_1",
        query=None,
        recommend=_recommend_with(
            RecommendationItem(
                equipment_type="Fork Lift",
                asset_id="Hyster H4.2FT Forklift",
                fleet_id=27,
                rank=1,
                pricing=PricingPayload(daily_rate=175.0, total_price=1225.0),
            )
        ),
        session=_session(),
        db=db,
    )
    equipment = quote.items[0].equipment
    assert equipment.id == "27"
    assert equipment.available is False
    assert equipment.capacity == 4200.0
    assert equipment.desc == "4.2t counterbalance"


def test_quote_uses_fleet_id_without_db_when_already_known() -> None:
    quote = map_recommend_to_quote(
        user_id="u1",
        ingest_id="ing_1",
        query=None,
        recommend=_recommend_with(
            RecommendationItem(
                equipment_type="Scissors Lift",
                asset_id="Genie GS-1930",
                fleet_id=17,
                name="Genie GS-1930",
                rank=1,
                pricing=PricingPayload(daily_rate=185.0, total_price=1295.0),
            )
        ),
        session=_session(),
        db=None,
    )
    equipment = quote.items[0].equipment
    assert equipment.id == "17"
    assert equipment.name == "Genie GS-1930"


def test_recommendation_service_uses_live_assets_when_sql_backend(
    monkeypatch,
) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("FLEET_BACKEND", "sql")
    get_settings.cache_clear()

    live = [
        {
            "id": 17,
            "asset_id": "Genie GS-1930",
            "name": "Genie GS-1930",
            "equipment_type": "Scissors Lift",
            "category": "scissor lift",
            "condition": "GOOD",
            "capacity": 300.0,
            "platform_height": 8.0,
            "min_daily_rate": 120.0,
            "max_daily_rate": 280.0,
        }
    ]
    monkeypatch.setattr(
        "app.services.recommendations.load_live_fleet",
        lambda db=None, resolution=None: (live, []),
    )

    class _Fixed:
        def decompose(self, source_text: str):
            del source_text
            return [
                DecomposedNeed(
                    need_id="need_1",
                    description="Need scissors lift",
                    equipment_hints=["scissor lift"],
                    quantity=1,
                )
            ]

    service = RecommendationService(decomposer=_Fixed())
    result = service.recommend_from_project_spec(
        project_text="Need scissors lift for indoor elevated work"
    )
    item = result.results_by_need[0].item
    assert item is not None
    assert item.asset_id == "Genie GS-1930"
    assert item.fleet_id == 17
    assert item.name == "Genie GS-1930"
    get_settings.cache_clear()


def test_recommendation_service_sql_does_not_fall_back_to_seed(
    monkeypatch,
) -> None:
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("FLEET_BACKEND", "sql")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.recommendations.load_live_fleet",
        lambda db=None, resolution=None: (_ for _ in ()).throw(
            RuntimeError("db down")
        ),
    )
    service = RecommendationService(
        decomposer=MagicMock(
            decompose=lambda source_text: [
                DecomposedNeed(
                    need_id="need_1",
                    description="Need scissors lift",
                    equipment_hints=["scissor lift"],
                    quantity=1,
                )
            ]
        )
    )
    assert isinstance(service._asset_filter, AssetCandidateFilter)
    assert service._asset_filter._assets == []
    assert isinstance(service._availability_filter, BookingAvailabilityFilter)
    get_settings.cache_clear()
