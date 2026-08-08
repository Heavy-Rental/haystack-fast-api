"""LangGraph state for Stage-1 project-knowledge multi-agent runs."""

from __future__ import annotations

from typing import Any, TypedDict


class ProjectKnowledgeAgentState(TypedDict, total=False):
    user_id: str
    ingest_id: str
    query: str
    top_k: int
    research_notes: str
    research_hits: list[dict[str, Any]]
    graph_notes: str
    graph_hits: list[dict[str, Any]]
    final_answer: str
    sources_used: list[str]
    tool_traces: list[dict[str, Any]]
