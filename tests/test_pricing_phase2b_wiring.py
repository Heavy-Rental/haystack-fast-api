"""Phase 2b (lean) — pipeline wiring only
(docs/dynamic-pricing-execution-plan.md "Day 5 (cont.) -- Phase 2b (lean)").

Verifies the swap actually happened end to end: PredictPriceAdapter and
RecommendationService now populate item.pricing.daily_rate via
app.services.pricing.model.predict_price() (production model), not the old
ml-experiments prototype. Guardrail-clamping/feature-schema transform
correctness is Phase 2a's job (test_pricing_model.py, test_pricing_feature_schema.py)
-- not re-tested here.
"""

from __future__ import annotations

from datetime import date

from app.pipelines.predict_price_adapter import PredictPriceAdapter
from app.pipelines.seed_fleet import get_seed_assets
from app.services.recommendations import RecommendationService


def test_predict_price_adapter_uses_production_model_not_prototype() -> None:
    asset = next(a for a in get_seed_assets() if a["category"] == "excavator")

    out = PredictPriceAdapter().run(
        candidates=[asset],
        duration_days=7.0,
        include_pricing=True,
    )
    priced = out["priced_candidates"]

    assert len(priced) == 1
    pricing = priced[0]["pricing"]
    assert pricing is not None
    assert pricing["model_version"].startswith("prod-")
    assert "experimental-ml_experiments" not in pricing["model_version"]
    assert "fallback-category-table" not in pricing["model_version"]
    assert asset["min_daily_rate"] <= pricing["daily_rate"] <= asset["max_daily_rate"]
    assert pricing["total_price"] == round(pricing["daily_rate"] * 7.0, 2)


def test_recommendation_response_item_pricing_daily_rate_populates() -> None:
    service = RecommendationService()

    response = service.recommend_from_project_spec(
        project_text="need a scissor lift for a construction project",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert response.results_by_need
    item = response.results_by_need[0].item
    assert item is not None
    assert item.pricing is not None
    assert item.pricing.daily_rate is not None
    assert item.pricing.daily_rate > 0
    assert item.pricing.model_version.startswith("prod-")
