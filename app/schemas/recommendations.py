"""Recommendation intake request/response schemas (free-text / file MVP)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RecommendOptions(BaseModel):
    """Optional flags for the recommendation path."""

    include_pricing: bool = Field(
        default=True, description="Attach predict_price() fields when true"
    )


class RecommendFromProjectSpecRequest(BaseModel):
    """POST /api/v1/recommendations/from-project-spec JSON body."""

    project_text: str = Field(
        ...,
        min_length=1,
        description="Unstructured project description (single free-text box)",
    )
    start_date: date | None = Field(
        default=None, description="Rental window start (ISO 8601 date)"
    )
    end_date: date | None = Field(
        default=None, description="Rental window end (ISO 8601 date)"
    )
    options: RecommendOptions = Field(default_factory=RecommendOptions)

    @field_validator("project_text", mode="before")
    @classmethod
    def strip_project_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_date_window(self) -> "RecommendFromProjectSpecRequest":
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
        if not self.project_text:
            raise ValueError("project_text must not be empty")
        return self


class DecomposedNeed(BaseModel):
    """Internal need after LLM decomposition (not a public client form row)."""

    need_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    equipment_hints: list[str] = Field(default_factory=list)
    quantity: int = Field(default=1, ge=1, description="Expanded away before response")


class UnitNeed(BaseModel):
    """One unit after quantity expansion; maps 1:1 to a results_by_need row."""

    need_id: str
    description: str
    equipment_hints: list[str] = Field(default_factory=list)


class PricingPayload(BaseModel):
    """Pricing fields on a recommendation item (from predict_price for this window).

    ``daily_rate`` is scoped to the requested rental duration (a model input).
    Do not re-scale it for a different window — call predict_price again.
    ``total_price`` is the estimated total: daily_rate × duration_days.
    """

    daily_rate: float | None = Field(
        default=None,
        description="Predicted price per day for the requested duration window",
    )
    total_price: float | None = Field(
        default=None,
        description="Estimated total for the requested duration (daily_rate × duration_days)",
    )
    currency: str = "SGD"
    deposit_rate: float = 0.30
    model_version: str | None = None
    explanation: str | None = None


class RecommendationItem(BaseModel):
    """Exactly one selected recommendation for a unit-need (no quantity field)."""

    equipment_type: str | None = None
    asset_id: str | None = None
    rank: int | None = None
    rationale: str | None = None
    pricing: PricingPayload | None = None
    availability: Literal["available", "unavailable", "unknown"] | str = "unknown"


class NeedResult(BaseModel):
    """Result for one unit-need: exactly one ranked item, or null if no match/stub."""

    need_id: str
    item: RecommendationItem | None = Field(
        default=None,
        description="Exactly one ranked RecommendationItem when selected; null if none",
    )
    warnings: list[str] = Field(default_factory=list)


class RecommendFromProjectSpecResponse(BaseModel):
    """Successful recommendation response envelope."""

    recommendation_id: str
    start_date: date | None = None
    end_date: date | None = None
    results_by_need: list[NeedResult]
