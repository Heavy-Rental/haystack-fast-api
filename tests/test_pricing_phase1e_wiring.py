"""Phase 1e — db/start_date/end_date threaded through the call chain
(RecommendationService -> PredictPriceAdapter -> pricing_client), per
docs/dynamic-pricing-execution-plan.md's Phase 1e task.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import app.pipelines.predict_price_adapter as ppa
from app.schemas.recommendations import DecomposedNeed
from app.services.recommendations import RecommendationService


def test_predict_price_adapter_threads_db_and_dates(monkeypatch) -> None:
    captured: list[dict] = []

    def _fake_predict_price_for_asset(**kwargs):
        captured.append(kwargs)
        return MagicMock(
            daily_rate=100.0,
            total_price=700.0,
            currency="SGD",
            deposit_rate=0.30,
            model_version="test",
            explanation="test",
        )

    monkeypatch.setattr(ppa, "predict_price_for_asset", _fake_predict_price_for_asset)
    fake_db = MagicMock()

    ppa.PredictPriceAdapter().run(
        candidates=[
            {
                "asset_id": "AST-EX-001",
                "category": "excavator",
                "condition": "GOOD",
                "capacity": 5000.0,
                "platform_height": None,
                "min_daily_rate": 250.0,
                "max_daily_rate": 600.0,
            }
        ],
        duration_days=7.0,
        include_pricing=True,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
        db=fake_db,
    )

    assert len(captured) == 1
    assert captured[0]["db"] is fake_db
    assert captured[0]["start_date"] == date(2026, 9, 1)
    assert captured[0]["end_date"] == date(2026, 9, 7)
    assert captured[0]["min_daily_rate"] == 250.0
    assert captured[0]["max_daily_rate"] == 600.0


def test_predict_price_adapter_parses_string_dates(monkeypatch) -> None:
    captured: list[dict] = []
    monkeypatch.setattr(
        ppa,
        "predict_price_for_asset",
        lambda **kwargs: (
            captured.append(kwargs)
            or MagicMock(
                daily_rate=1.0,
                total_price=1.0,
                currency="SGD",
                deposit_rate=0.3,
                model_version="t",
                explanation="t",
            )
        ),
    )

    ppa.PredictPriceAdapter().run(
        candidates=[
            {
                "asset_id": "A1",
                "category": "forklift",
                "min_daily_rate": 80.0,
                "max_daily_rate": 200.0,
            }
        ],
        start_date="2026-09-01",
        end_date="2026-09-07",
    )

    assert captured[0]["start_date"] == date(2026, 9, 1)
    assert captured[0]["end_date"] == date(2026, 9, 7)


class _FixedDecomposer:
    def __init__(self, needs: list[DecomposedNeed]) -> None:
        self._needs = needs

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        return list(self._needs)


def test_recommendation_service_threads_db_into_price_adapter() -> None:
    fake_db = MagicMock()
    captured_calls: list[dict] = []

    class _CapturingPriceAdapter:
        def run(self, **kwargs):
            captured_calls.append(kwargs)
            return {"priced_candidates": []}

    service = RecommendationService(
        decomposer=_FixedDecomposer(
            [DecomposedNeed(need_id="n1", description="scissors", equipment_hints=["scissors"])]
        ),
        price_adapter=_CapturingPriceAdapter(),
        db=fake_db,
    )

    service.recommend_from_project_spec(
        project_text="need a scissor lift",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert captured_calls
    assert captured_calls[0]["db"] is fake_db
    assert captured_calls[0]["start_date"] == date(2026, 9, 1)
    assert captured_calls[0]["end_date"] == date(2026, 9, 7)
