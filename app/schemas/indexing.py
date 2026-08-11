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
        description="Echo of request start_date when supplied (S1b); null if omitted",
    )
    tentative_end_date: date | None = Field(
        default=None,
        description="Echo of request end_date when supplied (S1b); null if omitted",
    )
    needs_summary: list[NeedSummaryItem] = Field(
        default_factory=list,
        description=(
            "Structured needs from need decomposer after successful index+KG (S1c); "
            "empty list + warning when none inferred"
        ),
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Soft issues (e.g. truncated summary); empty when none",
    )
