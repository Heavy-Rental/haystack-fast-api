"""Schemas for project-spec indexing HTTP response (Call 1 / S1 lean body)."""

from pydantic import BaseModel, Field


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
    warnings: list[str] = Field(
        default_factory=list,
        description="Soft issues (e.g. truncated summary); empty when none",
    )
