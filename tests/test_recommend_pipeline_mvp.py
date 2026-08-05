"""FR-010.4–8 components + end-to-end recommend path (seed fleet MVP)."""

from __future__ import annotations

from datetime import date

from app.pipelines.asset_candidate_filter import AssetCandidateFilter
from app.pipelines.booking_availability_filter import BookingAvailabilityFilter
from app.pipelines.predict_price_adapter import PredictPriceAdapter
from app.pipelines.rank_rationale_generator import RankRationaleGenerator
from app.schemas.recommendations import DecomposedNeed
from app.services.recommendations import RecommendationService


class _FixedDecomposer:
    def __init__(self, needs: list[DecomposedNeed]) -> None:
        self._needs = needs

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        assert source_text
        return list(self._needs)


def test_asset_filter_matches_scissors() -> None:
    out = AssetCandidateFilter().run(
        unit_need={
            "need_id": "n1",
            "description": "Indoor elevated work",
            "equipment_hints": ["scissors lift"],
        }
    )
    cands = out["candidates"]
    assert cands
    assert all(c["equipment_type"] == "Scissors Lift" for c in cands)


def test_asset_filter_unknown_need_empty() -> None:
    out = AssetCandidateFilter().run(
        unit_need={"need_id": "n1", "description": "Need a submarine", "equipment_hints": []}
    )
    assert out["candidates"] == []


def test_availability_filters_overlapping_booking() -> None:
    # AST-EX-002 is booked 2026-09-01..2026-09-30 in seed
    candidates = [
        {"asset_id": "AST-EX-001", "equipment_type": "Excavator"},
        {"asset_id": "AST-EX-002", "equipment_type": "Excavator"},
    ]
    out = BookingAvailabilityFilter().run(
        candidates=candidates,
        start_date=date(2026, 9, 5),
        end_date=date(2026, 9, 12),
    )
    available_ids = {c["asset_id"] for c in out["available_candidates"]}
    assert "AST-EX-001" in available_ids
    assert "AST-EX-002" not in available_ids


def test_availability_pass_through_without_dates() -> None:
    candidates = [{"asset_id": "AST-EX-002"}]
    out = BookingAvailabilityFilter().run(
        candidates=candidates, start_date=None, end_date=None
    )
    assert len(out["available_candidates"]) == 1


def test_price_adapter_attaches_pricing() -> None:
    candidates = [
        {
            "asset_id": "AST-SL-001",
            "equipment_type": "Scissors Lift",
            "category": "scissor lift",
            "condition": "GOOD",
            "capacity": 300.0,
            "platform_height": 10.0,
        }
    ]
    out = PredictPriceAdapter().run(
        candidates=candidates, duration_days=7.0, include_pricing=True
    )
    priced = out["priced_candidates"]
    assert len(priced) == 1
    pricing = priced[0]["pricing"]
    assert pricing is not None
    assert pricing["daily_rate"] is not None
    assert pricing["currency"] == "SGD"
    assert pricing["deposit_rate"] == 0.30


def test_ranker_picks_one() -> None:
    unit = {"need_id": "n1", "description": "scissors", "equipment_hints": ["scissors"]}
    priced = [
        {
            "asset_id": "A",
            "equipment_type": "Scissors Lift",
            "condition": "FAIR",
            "capacity": 100,
            "pricing": {},
        },
        {
            "asset_id": "B",
            "equipment_type": "Scissors Lift",
            "condition": "EXCELLENT",
            "capacity": 200,
            "pricing": {},
        },
    ]
    out = RankRationaleGenerator().run(unit_need=unit, priced_candidates=priced)
    assert out["selected"]["asset_id"] == "B"
    assert out["selected"]["rank"] == 1
    assert "schema" in out["rationale"].lower() or "terrain" in out["rationale"].lower()


def test_ranker_empty_candidates() -> None:
    out = RankRationaleGenerator().run(
        unit_need={"need_id": "n1", "description": "x"},
        priced_candidates=[],
    )
    assert out["selected"] == {}
    assert out["rationale"] == ""


def test_e2e_scissors_yields_item() -> None:
    service = RecommendationService(
        decomposer=_FixedDecomposer(
            [
                DecomposedNeed(
                    need_id="need_1",
                    description="Indoor elevated work ~8m scissors lift",
                    equipment_hints=["scissors lift"],
                    quantity=1,
                )
            ]
        )
    )
    result = service.recommend_from_project_spec(
        project_text="Indoor elevated work ~8m scissors lift",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 12),
    )
    assert len(result.results_by_need) == 1
    item = result.results_by_need[0].item
    assert item is not None
    assert item.equipment_type == "Scissors Lift"
    assert item.rank == 1
    assert item.asset_id
    assert item.rationale
    assert item.pricing is not None
    assert item.pricing.daily_rate is not None
    assert item.availability == "available"


def test_e2e_quantity_two_scissors() -> None:
    service = RecommendationService(
        decomposer=_FixedDecomposer(
            [
                DecomposedNeed(
                    need_id="need_1",
                    description="scissors lift",
                    equipment_hints=["scissors lift"],
                    quantity=2,
                )
            ]
        )
    )
    result = service.recommend_from_project_spec(project_text="two scissors lifts")
    assert len(result.results_by_need) == 2
    assert result.results_by_need[0].need_id == "need_1__u1"
    assert result.results_by_need[1].need_id == "need_1__u2"
    # Both should get an item if enough seed units
    assert result.results_by_need[0].item is not None
    assert result.results_by_need[1].item is not None


def test_e2e_no_match_scenario_c() -> None:
    service = RecommendationService(
        decomposer=_FixedDecomposer(
            [
                DecomposedNeed(
                    need_id="need_1",
                    description="Need a submarine for underwater work",
                    equipment_hints=[],
                    quantity=1,
                )
            ]
        )
    )
    result = service.recommend_from_project_spec(
        project_text="Need a submarine for underwater work"
    )
    assert result.results_by_need[0].item is None
    assert result.results_by_need[0].warnings
