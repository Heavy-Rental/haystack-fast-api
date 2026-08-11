"""POST /internal/v1/pricing/quote (openspec/specs/dynamic-pricing/spec.md US-4).

Synchronous, service-to-service only (Spring Boot -> Haystack), never
renter-facing. Registered directly on the app in app/main.py, deliberately
NOT included under app.api.api_router (the public /api/v1 surface) -- see
spec.md "Requirement: No renter-facing predict route".

Reuses app/services/pricing/model.py's predict_price(...) -- no second
prediction path, per spec's explicit "SHALL reuse the same ... predict_price(...)
path" requirement (US-4). category/condition/capacity/platform_height and the
real guardrail bounds are resolved server-side from asset_id alone; the
request body never carries them.

Read-resilience note: each item resolves its own schema twice -- once here
for the guardrail-bound Asset read (get_asset_for_pricing), once more
inside predict_price(...) itself for period_utilization/lead_time_days (it
always does its own resolution when given db/start_date/end_date, and has
no parameter to accept a precomputed one). Both are real tiered resolutions
against the same shared resolver, just not collapsed into a single call --
an item's `degraded` flag ORs both outcomes so it never under-reports. A
single predict_price(...) call's own internal reads still never mix schemas
(model.py's existing guarantee, unchanged).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.pricing import (
    PricingQuoteRequest,
    PricingQuoteResponse,
    QuoteItemRequest,
    QuoteItemResult,
)
from app.services.pricing.model import predict_price
from app.services.pricing.read_resilience import resolve_pricing_schema
from app.services.pricing.repository import get_asset_for_pricing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/v1/pricing", tags=["internal-pricing"])


@router.post("/quote", response_model=PricingQuoteResponse)
def quote(body: PricingQuoteRequest, db: Session = Depends(get_db)) -> PricingQuoteResponse:
    """Authoritative, guardrail-clamped price per requested asset at checkout."""
    results = [_quote_one_item(db, body, item) for item in body.items]
    return PricingQuoteResponse(
        rental_plan_id=body.rental_plan_id,
        degraded=any(r.degraded for r in results),
        results=results,
    )


def _quote_one_item(
    db: Session, body: PricingQuoteRequest, item: QuoteItemRequest
) -> QuoteItemResult:
    # PricingSchemaUnavailable (cold start -- neither schema has the
    # relations) is deliberately NOT caught here: it's a systemic condition,
    # not specific to this item, so it propagates to the global exception
    # handler (500) rather than being reported as 1-of-N per-item errors.
    resolution = resolve_pricing_schema(db)

    try:
        asset = get_asset_for_pricing(db, resolution, item.asset_id)
    except KeyError as exc:
        return QuoteItemResult(
            item_id=item.item_id,
            asset_id=item.asset_id,
            error=f"unrecognized_category: {exc}",
        )
    if asset is None:
        return QuoteItemResult(
            item_id=item.item_id, asset_id=item.asset_id, error="asset_not_found"
        )

    prediction = predict_price(
        category=asset.category,
        condition=asset.condition,
        duration_days=(body.end_date - body.start_date).days,
        capacity=asset.capacity,
        distance_km=body.distance_km,
        platform_height=asset.platform_height,
        min_daily_rate=asset.min_daily_rate,
        max_daily_rate=asset.max_daily_rate,
        db=db,
        start_date=body.start_date,
        end_date=body.end_date,
    )

    return QuoteItemResult(
        item_id=item.item_id,
        asset_id=item.asset_id,
        daily_rate=prediction.clamped_price,
        total_price=round(prediction.clamped_price * prediction.duration_days, 2),
        was_clamped=prediction.was_clamped,
        min_daily_rate=prediction.min_daily_rate,
        max_daily_rate=prediction.max_daily_rate,
        model_version=prediction.model_version,
        degraded=resolution.degraded or prediction.degraded,
    )
