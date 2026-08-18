"""Schemas for Stage-1 project-knowledge multi-agent Q&A."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectKnowledgeQueryRequest(BaseModel):
    """POST /internal/v1/recommendations/project-knowledge/query (Call 3 chatbot Q&A)."""

    user_id: str = Field(..., min_length=1, description="Same user_id used at ingest")
    ingest_id: str = Field(
        ...,
        min_length=1,
        description="ingest_id returned by /submitprojectspecification",
    )
    query: str = Field(..., min_length=1, description="Natural-language question")
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional retrieval depth override",
    )
    kg_artifact_path: str | None = Field(
        default=None,
        description=(
            "Optional path to reload KG-1 if the process-local session was lost. "
            "Vector store remains empty until re-ingest."
        ),
    )


class ProjectKnowledgeHit(BaseModel):
    content: str = ""
    score: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ProjectKnowledgeToolTrace(BaseModel):
    agent: str
    tool: str
    query: str
    hit_count: int = 0


class ProjectKnowledgeQueryResponse(BaseModel):
    user_id: str
    ingest_id: str
    query: str
    answer: str
    sources_used: list[str] = Field(default_factory=list)
    research_hits: list[ProjectKnowledgeHit] = Field(default_factory=list)
    graph_hits: list[ProjectKnowledgeHit] = Field(default_factory=list)
    tool_traces: list[ProjectKnowledgeToolTrace] = Field(default_factory=list)
    research_notes: str | None = None
    graph_notes: str | None = None
