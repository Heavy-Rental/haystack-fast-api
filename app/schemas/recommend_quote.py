"""Call 2 recommend / quote response DTO (portal getassetrecommendations).

Maps FR-010 ``results_by_need`` into a commercial-style quote envelope.
Equipment ids and rates MUST come from fleet + pricing tools only (no invent).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EquipmentQuote(BaseModel):
    """Tool-backed equipment identity and rates (never invented)."""

    id: str | None = Field(default=None, description="asset_id from catalog/fleet")
    name: str | None = Field(
        default=None, description="Display name or equipment_type"
    )
    category: str | None = None
    baseDailyRate: float | None = Field(
        default=None, description="Predicted daily rate for rental window"
    )
    weekly: float | None = Field(
        default=None, description="Optional weekly rate if known"
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extra catalog fields (condition, capacity, …)",
    )


class RecommendQuoteItem(BaseModel):
    rankOrder: int = 1
    matchScore: float | None = None
    reason: str | None = None
    lineTotal: float | None = None
    quantity: int = 1
    needId: str | None = None
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
