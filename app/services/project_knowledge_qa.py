"""Service facade: project-knowledge multi-agent Q&A (Stage 1)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.agents.graph import run_project_knowledge_agents
from app.config import Settings, get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.project_knowledge import (
    ProjectKnowledgeHit,
    ProjectKnowledgeQueryResponse,
    ProjectKnowledgeToolTrace,
)
from app.services.project_knowledge_session import (
    ProjectKnowledgeSessionRegistry,
    get_or_load_session,
    get_project_knowledge_registry,
)

logger = logging.getLogger(__name__)


def _llm_call_factory(settings: Settings) -> Any:
    """Return a simple system/user → text callable using OpenAI-compatible API."""

    def llm_call(system: str, user: str) -> str:
        if not settings.llm_api_key:
            raise BadRequestError("LLM_API_KEY is required when PROJECT_AGENT_MODE=llm")
        url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.llm_model,
            "temperature": settings.llm_temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise BadRequestError("LLM returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            raise BadRequestError("LLM returned empty content")
        return str(content)

    return llm_call


class ProjectKnowledgeQAService:
    """Resolve session and run LangGraph multi-agent Q&A."""

    def __init__(
        self,
        *,
        registry: ProjectKnowledgeSessionRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._registry = registry or get_project_knowledge_registry()
        self._settings = settings or get_settings()

    def ask(
        self,
        *,
        user_id: str,
        ingest_id: str,
        query: str,
        top_k: int | None = None,
        kg_artifact_path: str | None = None,
    ) -> ProjectKnowledgeQueryResponse:
        uid = (user_id or "").strip()
        iid = (ingest_id or "").strip()
        q = (query or "").strip()
        if not uid:
            raise BadRequestError("user_id is required")
        if not iid:
            raise BadRequestError("ingest_id is required")
        if not q:
            raise BadRequestError("query must not be empty")

        try:
            session = get_or_load_session(
                uid,
                iid,
                kg_artifact_path=kg_artifact_path,
                registry=self._registry,
            )
        except NotFoundError:
            raise
        except Exception as exc:
            logger.warning("session resolve failed: %s", exc)
            raise NotFoundError(
                f"project knowledge session not found for user_id={uid!r} ingest_id={iid!r}"
            ) from exc

        mode = str(self._settings.project_agent_mode or "stub").strip().lower()
        llm_call = _llm_call_factory(self._settings) if mode == "llm" else None
        k = int(top_k if top_k is not None else self._settings.project_agent_top_k)

        result = run_project_knowledge_agents(
            session,
            query=q,
            top_k=k,
            settings=self._settings,
            agent_mode=mode,
            llm_call=llm_call,
        )

        research_hits = [
            ProjectKnowledgeHit(
                content=str(h.get("content") or h.get("content_preview") or ""),
                score=h.get("score"),
                meta={
                    **dict(h.get("meta") or {}),
                    **({"node_type": h["node_type"]} if h.get("node_type") is not None else {}),
                    **({"node_id": h["node_id"]} if h.get("node_id") is not None else {}),
                },
            )
            for h in list(result.get("research_hits") or [])
        ]
        graph_hits = [
            ProjectKnowledgeHit(
                content=str(h.get("content_preview") or h.get("content") or ""),
                score=h.get("score"),
                meta={k2: h[k2] for k2 in ("node_id", "node_type") if h.get(k2) is not None}
                | dict(h.get("properties") or {}),
            )
            for h in list(result.get("graph_hits") or [])
        ]
        traces = [
            ProjectKnowledgeToolTrace(
                agent=str(t.get("agent") or ""),
                tool=str(t.get("tool") or ""),
                query=str(t.get("query") or ""),
                hit_count=int(t.get("hit_count") or 0),
            )
            for t in list(result.get("tool_traces") or [])
        ]

        return ProjectKnowledgeQueryResponse(
            user_id=uid,
            ingest_id=iid,
            query=q,
            answer=str(result.get("final_answer") or ""),
            sources_used=list(result.get("sources_used") or []),
            research_hits=research_hits,
            graph_hits=graph_hits,
            tool_traces=traces,
            research_notes=str(result.get("research_notes") or "") or None,
            graph_notes=str(result.get("graph_notes") or "") or None,
        )
