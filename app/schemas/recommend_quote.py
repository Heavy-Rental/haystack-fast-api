"""Call 2 recommend / quote response DTO (portal getassetrecommendations).

Maps FR-010 ``results_by_need`` into a commercial-style quote envelope.
Equipment ids and rates MUST come from fleet + pricing tools only (no invent).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_serializer


class EquipmentQuote(BaseModel):
    """Tool-backed equipment identity and rates (never invented)."""

    id: str | None = Field(
        default=None,
        description="assets.id when live SQL; seed asset_id otherwise",
    )
    name: str | None = Field(
        default=None,
        description="assets.name when live SQL; equipment_type otherwise",
    )
    category: str | None = None
    baseDailyRate: float | None = Field(
        default=None, description="Predicted daily rate for rental window"
    )
    weekly: float | None = Field(default=None, description="Optional weekly rate if known")
    capacity: float | None = Field(
        default=None, description="assets.capacity when the row resolves"
    )
    purchaseYear: int | None = Field(
        default=None, description="assets.purchase_year when the row resolves"
    )
    location: str | None = Field(default=None, description="assets.location when the column exists")
    available: bool | None = Field(
        default=None,
        description="False when a live-hold booking overlaps the rental window",
    )
    desc: str | None = Field(default=None, description="assets.description when the row resolves")
    platformHeight: float | None = Field(
        default=None,
        description=(
            "assets.platform_height for Scissors Lift / Boom Lift "
            "(category_id 2 or 3) only; omitted otherwise"
        ),
    )
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extra catalog fields (condition, …)",
    )

    @model_serializer(mode="wrap")
    def _omit_platform_height_unless_set(self, handler):
        data = handler(self)
        if data.get("platformHeight") is None:
            data.pop("platformHeight", None)
        return data


class RecommendQuoteItem(BaseModel):
    rankOrder: int = 1
    matchScore: float | None = None
    reason: str | None = None
    lineTotal: float | None = None
    quantity: int = 1
    needId: str | None = None
    mlPredictedPrice: float | None = Field(
        default=None,
        description=(
            "Predicted daily rate from pricing_client / predict_price "
            "(same value as equipment.baseDailyRate). Never invented."
        ),
    )
    equipment: EquipmentQuote = Field(default_factory=EquipmentQuote)


class AssetRecommendRequest(BaseModel):
    """POST .../project-knowledge/getassetrecommendations (Call 2 recommend)."""

    user_id: str = Field(..., min_length=1)
    ingest_id: str = Field(..., min_length=1)
    query: str | None = Field(
        default=None,
        description="Optional focus / predefined prompt; not required for recommend",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional cap on returned items (default: all unit-needs)",
    )


class AssetRecommendResponse(BaseModel):
    """Call 2 recommend quote envelope for Spring / React portal."""

    user_id: str
    ingest_id: str
    query: str | None = None
    quoteRef: str
    confidenceScore: float | None = None
    days: int | None = None
    estimatedTotal: float | None = None
    specSummary: str | None = None
    rationale: str | None = None
    items: list[RecommendQuoteItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendationId: str | None = Field(
        default=None,
        description="Internal recommendation_id (rec_…) when produced by MVP service",
    )
