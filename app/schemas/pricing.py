"""POST /internal/v1/pricing/quote request/response schemas.

Full contract and JSON examples: openspec/specs/dynamic-pricing/design.md
"Internal quote API". One deliberate resolution of that doc's illustrative
example: ``asset_id`` is shown there as a string code (e.g. "AST-EXC-004",
the placeholder convention app/pipelines/seed_fleet.py uses for
scratch/candidate fixtures) -- but this endpoint resolves against the real
``Asset`` row by primary key (app/models/asset.py: ``id: Mapped[int]``), so
``asset_id`` here is ``int``, matching the real schema Spring Boot's
database actually uses, not the illustrative example's string form.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator


class QuoteItemRequest(BaseModel):
    """One requested asset within a multi-item quote."""

    item_id: str = Field(..., min_length=1)
    asset_id: int


class PricingQuoteRequest(BaseModel):
    """POST /internal/v1/pricing/quote JSON body."""

    rental_plan_id: str = Field(..., min_length=1)
    start_date: date
    end_date: date
    distance_km: float = Field(..., ge=0)
    items: list[QuoteItemRequest] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_window(self) -> PricingQuoteRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class QuoteItemResult(BaseModel):
    """One item's guardrail-clamped result, or a per-item error.

    When ``error`` is set, every pricing field is null -- an unresolvable
    ``asset_id`` (or an unrecognized category) must not fail the rest of the
    batch (spec.md US-4 Scenario "unresolvable asset_id handling").
    """

    item_id: str
    asset_id: int
    daily_rate: float | None = None
    total_price: float | None = None
    was_clamped: bool | None = None
    min_daily_rate: float | None = None
    max_daily_rate: float | None = None
    model_version: str | None = None
    degraded: bool | None = None
    error: str | None = None


class PricingQuoteResponse(BaseModel):
    """Successful (200) response envelope -- always returned even if some items error."""

    rental_plan_id: str
    currency: str = "SGD"
    deposit_rate: float = 0.30
    degraded: bool
    results: list[QuoteItemResult]
    warnings: list[str] = Field(default_factory=list)
