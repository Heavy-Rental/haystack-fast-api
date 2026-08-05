"""Recommendation orchestration: full FR-010 MVP pipeline structure.

1–3: intake_front Haystack graph (resolve → decompose → expand)
4–8: per unit-need component chain (filter → availability → price → rank → assemble)
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from haystack import Pipeline

from app.core.exceptions import BadRequestError
from app.pipelines.asset_candidate_filter import AssetCandidateFilter
from app.pipelines.booking_availability_filter import BookingAvailabilityFilter
from app.pipelines.intake_front import build_intake_front_pipeline, run_intake_front
from app.pipelines.predict_price_adapter import PredictPriceAdapter
from app.pipelines.rank_rationale_generator import RankRationaleGenerator
from app.schemas.recommendations import (
    NeedResult,
    PricingPayload,
    RecommendationItem,
    RecommendFromProjectSpecResponse,
    RecommendOptions,
    UnitNeed,
)
from app.services.need_decomposer import NeedDecomposer
from app.services.need_decomposer_factory import create_need_decomposer

logger = logging.getLogger(__name__)

NO_MATCH_WARNING = (
    "No available equipment matched this need for the requested window "
    "(or no catalog match). Refine equipment type, dates, or quantity."
)


class RecommendationService:
    """Full FR-010 orchestration under pipelines/services (routers stay thin)."""

    def __init__(
        self,
        *,
        decomposer: NeedDecomposer | None = None,
        pipeline: Pipeline | None = None,
        asset_filter: AssetCandidateFilter | None = None,
        availability_filter: BookingAvailabilityFilter | None = None,
        price_adapter: PredictPriceAdapter | None = None,
        ranker: RankRationaleGenerator | None = None,
        default_duration_days: float = 7.0,
        default_distance_km: float = 15.0,
    ) -> None:
        self._decomposer: NeedDecomposer = decomposer or create_need_decomposer()
        self._pipeline = pipeline or build_intake_front_pipeline(
            decomposer=self._decomposer
        )
        self._asset_filter = asset_filter or AssetCandidateFilter()
        self._availability_filter = availability_filter or BookingAvailabilityFilter()
        self._price_adapter = price_adapter or PredictPriceAdapter(
            default_distance_km=default_distance_km
        )
        self._ranker = ranker or RankRationaleGenerator()
        self._default_duration_days = default_duration_days

    def recommend_from_project_spec(
        self,
        *,
        project_text: str | None = None,
        file_text: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        options: RecommendOptions | None = None,
    ) -> RecommendFromProjectSpecResponse:
        if start_date is not None and end_date is not None and end_date < start_date:
            raise BadRequestError("end_date must be on or after start_date")

        options = options or RecommendOptions()

        # FR-010.1–3
        unit_dicts = run_intake_front(
            self._pipeline,
            project_text=project_text,
            file_text=file_text,
        )
        if not unit_dicts:
            raise BadRequestError(
                "project_text or file must provide non-empty unstructured text "
                "that yields at least one equipment need"
            )

        unit_needs = [self._to_unit_need(u) for u in unit_dicts]
        recommendation_id = f"rec_{uuid.uuid4().hex}"
        duration_days = self._duration_days(start_date, end_date)
        logger.info(
            "recommendation recommendation_id=%s unit_need_count=%s "
            "start_date=%s end_date=%s duration_days=%s",
            recommendation_id,
            len(unit_needs),
            start_date,
            end_date,
            duration_days,
        )

        results_by_need = [
            self._recommend_for_unit_need(
                unit,
                start_date=start_date,
                end_date=end_date,
                duration_days=duration_days,
                include_pricing=options.include_pricing,
            )
            for unit in unit_needs
        ]

        return RecommendFromProjectSpecResponse(
            recommendation_id=recommendation_id,
            start_date=start_date,
            end_date=end_date,
            results_by_need=results_by_need,
        )

    def _recommend_for_unit_need(
        self,
        unit: UnitNeed,
        *,
        start_date: date | None,
        end_date: date | None,
        duration_days: float,
        include_pricing: bool,
    ) -> NeedResult:
        """FR-010.4–8: filter → availability → price → rank → assemble."""
        unit_dict = unit.model_dump()

        # 4. Asset candidates
        candidates = self._asset_filter.run(unit_need=unit_dict).get("candidates") or []

        # 5. Availability (before rank when dates present — FR-013)
        available = (
            self._availability_filter.run(
                candidates=candidates,
                start_date=start_date,
                end_date=end_date,
            ).get("available_candidates")
            or []
        )

        # 6. Pricing
        priced = (
            self._price_adapter.run(
                candidates=available,
                duration_days=duration_days,
                include_pricing=include_pricing,
            ).get("priced_candidates")
            or []
        )

        # 7. Rank / rationale — exactly one pick
        rank_out = self._ranker.run(unit_need=unit_dict, priced_candidates=priced)
        selected = rank_out.get("selected") or {}
        rationale = str(rank_out.get("rationale") or "")

        # 8. Assemble
        if not selected or not selected.get("asset_id"):
            return NeedResult(
                need_id=unit.need_id,
                item=None,
                warnings=[NO_MATCH_WARNING],
            )

        pricing_raw = selected.get("pricing")
        pricing = None
        if isinstance(pricing_raw, dict):
            pricing = PricingPayload(
                daily_rate=pricing_raw.get("daily_rate"),
                weekly_rate=pricing_raw.get("weekly_rate"),
                currency=str(pricing_raw.get("currency") or "SGD"),
                deposit_rate=float(pricing_raw.get("deposit_rate") or 0.30),
                model_version=pricing_raw.get("model_version"),
                explanation=pricing_raw.get("explanation"),
            )

        item = RecommendationItem(
            equipment_type=selected.get("equipment_type"),
            asset_id=selected.get("asset_id"),
            rank=int(selected.get("rank") or 1),
            rationale=rationale or None,
            pricing=pricing,
            availability=str(selected.get("availability") or "available"),
        )
        return NeedResult(need_id=unit.need_id, item=item, warnings=[])

    def _duration_days(self, start: date | None, end: date | None) -> float:
        if start is not None and end is not None:
            days = (end - start).days + 1
            return float(max(1, days))
        return float(self._default_duration_days)

    @staticmethod
    def _to_unit_need(raw: dict[str, Any]) -> UnitNeed:
        return UnitNeed(
            need_id=str(raw["need_id"]),
            description=str(raw["description"]),
            equipment_hints=list(raw.get("equipment_hints") or []),
        )
