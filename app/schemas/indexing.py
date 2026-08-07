"""Schemas for project-spec indexing (Parts 1–3: classify + convert + vectorize)."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class IngestDocumentPreview(BaseModel):
    """Lightweight document/chunk preview for API responses."""

    content_preview: str = Field(
        ...,
        description="First characters of extracted document content",
    )
    content_length: int = Field(..., ge=0)
    meta: dict[str, Any] = Field(default_factory=dict)
    data_kind: Literal["structured", "unstructured"] | str | None = None
    has_embedding: bool = Field(
        default=False,
        description="True when the chunk carries a vector embedding",
    )


class IngestFromProjectSpecResponse(BaseModel):
    """Successful ingest response for /from-project-spec (classify → write)."""

    ingest_id: str = Field(..., description="ing_ + hex identifier")
    data_kind: Literal["structured", "unstructured", "mixed"] = Field(
        ...,
        description="Aggregate kind of classified sources",
    )
    mime_types_seen: list[str] = Field(default_factory=list)
    filenames: list[str] = Field(default_factory=list)
    structured_count: int = Field(default=0, ge=0, description="Classified structured sources")
    unstructured_count: int = Field(
        default=0, ge=0, description="Classified unstructured sources"
    )
    document_count: int = Field(
        default=0,
        ge=0,
        description="Documents produced by converters (pre-split)",
    )
    structured_document_count: int = Field(default=0, ge=0)
    unstructured_document_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Chunks after split (and embed), typically written to the store",
    )
    documents_written: int = Field(
        default=0,
        ge=0,
        description="Chunks written to the DocumentStore",
    )
    documents: list[IngestDocumentPreview] = Field(
        default_factory=list,
        description="Chunk previews after split/embed (content truncated)",
    )
    warnings: list[str] = Field(default_factory=list)
