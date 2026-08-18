"""FR-010.6 — Attach predict_price() fields to candidates."""

from __future__ import annotations

from datetime import date
from typing import Any

from haystack import component
from sqlalchemy.orm import Session

from app.services.pricing_client import predict_price_for_asset


def _parse_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip()
    return date.fromisoformat(text) if text else None


@component
class PredictPriceAdapter:
    """Call the production predict_price() for each available candidate."""

    def __init__(self, default_distance_km: float = 15.0) -> None:
        self._distance_km = default_distance_km

    @component.output_types(priced_candidates=list)
    def run(
        self,
        candidates: list | None = None,
        duration_days: float = 7.0,
        include_pricing: bool = True,
        distance_km: float | None = None,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        db: Session | None = None,
    ) -> dict[str, list]:
        pool = list(candidates or [])
        if not pool:
            return {"priced_candidates": []}

        dist = float(distance_km if distance_km is not None else self._distance_km)
        days = max(1.0, float(duration_days or 7.0))
        parsed_start = _parse_date(start_date)
        parsed_end = _parse_date(end_date)
        priced: list[dict[str, Any]] = []

        for raw in pool:
            candidate = dict(raw)
            if include_pricing:
                height = candidate.get("platform_height")
                capacity = candidate.get("capacity")
                price = predict_price_for_asset(
                    category=str(candidate.get("category") or "forklift"),
                    condition=str(candidate.get("condition") or "GOOD"),
                    duration_days=days,
                    capacity=None if capacity is None else float(capacity),
                    distance_km=dist,
                    platform_height=None if height is None else float(height),
                    min_daily_rate=float(candidate["min_daily_rate"]),
                    max_daily_rate=float(candidate["max_daily_rate"]),
                    db=db,
                    start_date=parsed_start,
                    end_date=parsed_end,
                )
                candidate["pricing"] = {
                    "daily_rate": price.daily_rate,
                    "total_price": price.total_price,
                    "currency": price.currency,
                    "deposit_rate": price.deposit_rate,
                    "model_version": price.model_version,
                    "explanation": price.explanation,
                    "was_clamped": price.was_clamped,
                }
            else:
                candidate["pricing"] = None
            priced.append(candidate)
        return {"priced_candidates": priced}
