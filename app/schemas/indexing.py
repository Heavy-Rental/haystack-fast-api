"""Schemas for project-spec indexing HTTP response (Call 1 / S1 lean body)."""

from datetime import date

from pydantic import BaseModel, Field


class NeedSummaryItem(BaseModel):
    """One structured need inferred from the project-spec (FR-IX-023 / S1c)."""

    need_id: str | None = Field(
        default=None,
        description="Optional stable id for Call 3 (e.g. need_1)",
    )
    description: str = Field(..., min_length=1, description="Human-readable need")
    equipment_hints: list[str] = Field(
        default_factory=list,
        description="Optional category/type hints",
    )
    quantity: int | None = Field(
        default=None,
        description="Optional quantity when known",
    )


class ExpectedBudget(BaseModel):
    """Budget extracted from project-spec text only (FR-IX-023 / S1d). Never invent."""

    amount: float = Field(..., description="Extracted amount when confidently found")
    currency: str | None = Field(
        default=None,
        description="ISO-like currency code when known (e.g. SGD)",
    )
    source: str = Field(
        default="extracted",
        description="Provenance marker (e.g. extracted); not request invent",
    )


class IngestFromProjectSpecResponse(BaseModel):
    """Lean success response for POST .../submitprojectspecification.

    Indexing + mandatory KG-1 still run and register a project-knowledge session
    for Call 2. Technical indexing/KG details are not exposed on the public body.
    """

    ingest_id: str = Field(..., description="ing_ + hex identifier for Call 2")
    user_id: str = Field(..., description="Echo of request user_id")
    user_requirement_summary: str = Field(
        ...,
        description=(
            "Deterministic summary of the submitted project requirement "
            "(from project_text or extracted multipart file content)"
        ),
    )
    tentative_start_date: date | None = Field(
        default=None,
        description=(
            "Rental window start: request start_date preferred (S1b); "
            "else free-text/file extract when confident (S1e); null if unknown"
        ),
    )
    tentative_end_date: date | None = Field(
        default=None,
        description=(
            "Rental window end: request end_date preferred (S1b); "
            "else free-text/file extract when confident (S1e); null if unknown"
        ),
    )
    needs_summary: list[NeedSummaryItem] = Field(
        default_factory=list,
        description=(
            "Structured needs from need decomposer after successful index+KG (S1c); "
            "empty list + warning when none inferred"
        ),
    )
    expected_budget: ExpectedBudget | None = Field(
        default=None,
        description=(
            "Budget extracted from project text/file when confident (S1d); "
            "null if missing/uncertain — never invent; not include_pricing"
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Soft issues (e.g. truncated summary); empty when none",
    )
