"""Haystack-backed tools for Stage-1 project knowledge agents + S3 index gate.

Tool names are stable contracts for LangGraph nodes and traces.
Indexing tool [4] is in-process only (no MCP); forced non-LLM Coordinator gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from haystack.dataclasses import ByteStream

from app.config import Settings, get_settings
from app.pipelines.indexing.retrieval import run_vector_search
from app.pipelines.kg.query import query_knowledge_graph
from app.schemas.indexing import IngestFromProjectSpecResponse
from app.services.indexing import IndexingIngestService
from app.services.project_knowledge_session import ProjectKnowledgeSession

TOOL_PROJECT_VECTOR_SEARCH = "project_vector_search"
TOOL_PROJECT_KG_QUERY = "project_kg_query"
TOOL_RUN_INDEXING = "run_indexing_from_request"

TOOL_DESCRIPTIONS: dict[str, str] = {
    TOOL_PROJECT_VECTOR_SEARCH: (
        "Dense vector search over the project specification DocumentStore "
        "chunks for the current ingest session (filters user_id + ingest_id)."
    ),
    TOOL_PROJECT_KG_QUERY: (
        "Query the project knowledge graph (KG-1) for document nodes, "
        "entities, and optional 1-hop relationships extracted from the "
        "uploaded project specification."
    ),
    TOOL_RUN_INDEXING: (
        "Coordinator gate [4]: index project-spec sources via "
        "IndexingIngestService (meta stamp, mandatory KG-1 hard-fail, "
        "session registry). Forced non-LLM tool — not a Worker agent."
    ),
}


@dataclass(frozen=True)
class ProjectTool:
    """Callable tool with stable name + natural-language description."""

    name: str
    description: str
    func: Callable[..., list[dict[str, Any]]]

    def __call__(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return self.func(*args, **kwargs)


def _embedder_settings(settings: Settings) -> dict[str, Any]:
    mode = str(settings.indexing_embedder or "mock").strip().lower()
    if mode not in {"mock", "openai", "sentence-transformers", "st", "minilm"}:
        mode = "mock"
    return {
        "mode": mode,
        "dimension": int(settings.indexing_embedding_dim),
        "openai_api_key": settings.llm_api_key,
        "openai_model": settings.indexing_openai_embedding_model,
        "openai_base_url": settings.llm_base_url if mode == "openai" else None,
        "sentence_transformers_model": settings.indexing_st_model,
    }


def build_project_vector_search_tool(
    session: ProjectKnowledgeSession,
    *,
    settings: Settings | None = None,
    default_top_k: int = 5,
) -> ProjectTool:
    cfg = settings or get_settings()
    embed_kwargs = _embedder_settings(cfg)

    def _run(query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        return run_vector_search(
            session.document_store,
            query,
            top_k=int(top_k if top_k is not None else default_top_k),
            user_id=session.user_id,
            ingest_id=session.ingest_id,
            **embed_kwargs,
        )

    return ProjectTool(
        name=TOOL_PROJECT_VECTOR_SEARCH,
        description=TOOL_DESCRIPTIONS[TOOL_PROJECT_VECTOR_SEARCH],
        func=_run,
    )


def build_project_kg_query_tool(
    session: ProjectKnowledgeSession,
    *,
    default_limit: int = 10,
) -> ProjectTool:
    def _run(query: str, limit: int | None = None) -> list[dict[str, Any]]:
        return query_knowledge_graph(
            session.knowledge_graph,
            query,
            limit=int(limit if limit is not None else default_limit),
            include_neighbors=True,
        )

    return ProjectTool(
        name=TOOL_PROJECT_KG_QUERY,
        description=TOOL_DESCRIPTIONS[TOOL_PROJECT_KG_QUERY],
        func=_run,
    )


def build_session_tools(
    session: ProjectKnowledgeSession,
    *,
    settings: Settings | None = None,
    top_k: int = 5,
) -> dict[str, ProjectTool]:
    """Return name → tool map for the session."""
    return {
        TOOL_PROJECT_VECTOR_SEARCH: build_project_vector_search_tool(
            session, settings=settings, default_top_k=top_k
        ),
        TOOL_PROJECT_KG_QUERY: build_project_kg_query_tool(
            session, default_limit=max(top_k, 10)
        ),
    }


def run_indexing_from_request(
    *,
    user_id: str,
    user_name: str | None = None,
    project_text: str | None = None,
    file_sources: list[ByteStream] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    service: IndexingIngestService | None = None,
) -> IngestFromProjectSpecResponse:
    """In-process indexing tool for Coordinator gate [4].

    Wraps ``IndexingIngestService.ingest_from_project_spec`` so HTTP, agent
    gate, and tests share the same meta stamp / KG hard-fail / session path.
    Does not put raw file bytes into any LLM context.
    """
    svc = service if service is not None else IndexingIngestService()
    return svc.ingest_from_project_spec(
        user_id=user_id,
        user_name=user_name,
        project_text=project_text,
        file_sources=file_sources,
        start_date=start_date,
        end_date=end_date,
    )
