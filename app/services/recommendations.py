"""Recommendation intake: free-text/file → decompose → expand quantity → envelope.

Downstream Asset SQL, availability, pricing, and ranking are stubbed until
parent pipeline stages land (Days 3–5).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from app.core.exceptions import BadRequestError
from app.schemas.recommendations import (
    DecomposedNeed,
    NeedResult,
    RecommendFromProjectSpecResponse,
    RecommendOptions,
    UnitNeed,
)
from app.services.need_decomposer import NeedDecomposer, StubNeedDecomposer

logger = logging.getLogger(__name__)

STUB_WARNING = (
    "Intake accepted; candidate selection, availability, pricing, "
    "and ranking are not wired yet (stub pipeline)."
)


class RecommendationService:
    """Orchestrates intake through unit-need assembly with singular item per need."""

    def __init__(self, decomposer: NeedDecomposer | None = None) -> None:
        self._decomposer: NeedDecomposer = decomposer or StubNeedDecomposer()

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

        source_text = self._resolve_source_text(project_text, file_text)
        options = options or RecommendOptions()

        decomposed = self._decomposer.decompose(source_text)
        if not decomposed:
            raise BadRequestError("could not extract any equipment needs from project text")

        unit_needs = self._expand_quantity(decomposed)
        if not unit_needs:
            raise BadRequestError("no unit-needs after quantity expansion")

        recommendation_id = f"rec_{uuid.uuid4().hex}"
        logger.info(
            "recommendation intake recommendation_id=%s unit_need_count=%s "
            "start_date=%s end_date=%s",
            recommendation_id,
            len(unit_needs),
            start_date,
            end_date,
        )

        results_by_need = [
            self._recommend_for_unit_need(
                unit,
                start_date=start_date,
                end_date=end_date,
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

    def _resolve_source_text(
        self, project_text: str | None, file_text: str | None
    ) -> str:
        parts: list[str] = []
        if file_text is not None and file_text.strip():
            parts.append(file_text.strip())
        if project_text is not None and project_text.strip():
            parts.append(project_text.strip())
        if not parts:
            raise BadRequestError(
                "project_text or file must provide non-empty unstructured text"
            )
        return "\n\n".join(parts)

    def _expand_quantity(self, needs: list[DecomposedNeed]) -> list[UnitNeed]:
        """FR-006: quantity N → N unit-needs; RecommendationItem never carries quantity."""
        units: list[UnitNeed] = []
        for need in needs:
            base_id = need.need_id.strip()
            description = need.description.strip()
            if not base_id or not description:
                raise BadRequestError("decomposed need missing need_id or description")
            n = max(1, need.quantity)
            hints = list(need.equipment_hints)
            if n == 1:
                units.append(
                    UnitNeed(
                        need_id=base_id,
                        description=description,
                        equipment_hints=hints,
                    )
                )
            else:
                for i in range(1, n + 1):
                    units.append(
                        UnitNeed(
                            need_id=f"{base_id}__u{i}",
                            description=description,
                            equipment_hints=hints,
                        )
                    )
        return units

    def _recommend_for_unit_need(
        self,
        unit: UnitNeed,
        *,
        start_date: date | None,
        end_date: date | None,
        include_pricing: bool,
    ) -> NeedResult:
        """Per unit-need: exactly one item when ranked; null while stubbed (FR-007)."""
        _ = (unit, start_date, end_date, include_pricing)
        return NeedResult(
            need_id=unit.need_id,
            item=None,
            warnings=[STUB_WARNING],
        )
