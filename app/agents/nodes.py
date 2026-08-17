"""LangGraph node functions for Stage-1 project-knowledge agents.

Stage 1 uses explicit tool calls (not free-form ReAct) for reliable CI tests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.agents.prompts import (
    GRAPH_AGENT_SYSTEM,
    RESEARCH_AGENT_SYSTEM,
    SYNTHESIS_AGENT_SYSTEM,
    stub_synthesis_answer,
)
from app.agents.state import ProjectKnowledgeAgentState
from app.agents.tools import (
    TOOL_PROJECT_KG_QUERY,
    TOOL_PROJECT_VECTOR_SEARCH,
    ProjectTool,
)

logger = logging.getLogger(__name__)


def _append_trace(
    state: ProjectKnowledgeAgentState,
    *,
    tool: str,
    query: str,
    hit_count: int,
    agent: str,
) -> list[dict[str, Any]]:
    traces = list(state.get("tool_traces") or [])
    traces.append(
        {
            "agent": agent,
            "tool": tool,
            "query": query,
            "hit_count": hit_count,
        }
    )
    return traces


def make_research_node(
    vector_tool: ProjectTool,
) -> Callable[[ProjectKnowledgeAgentState], dict[str, Any]]:
    def research_agent(state: ProjectKnowledgeAgentState) -> dict[str, Any]:
        query = str(state.get("query") or "").strip()
        top_k = int(state.get("top_k") or 5)
        hits = vector_tool(query, top_k=top_k)
        notes_lines = [f"(prompt contract) {RESEARCH_AGENT_SYSTEM.splitlines()[0]}"]
        if hits:
            notes_lines.append(f"Retrieved {len(hits)} passage(s) via {vector_tool.name}.")
            for hit in hits[:5]:
                content = str(hit.get("content") or "").strip().replace("\n", " ")
                notes_lines.append(f"- {content[:200]}")
        else:
            notes_lines.append("No vector hits for this query.")
        notes = "\n".join(notes_lines)
        return {
            "research_hits": hits,
            "research_notes": notes,
            "tool_traces": _append_trace(
                state,
                tool=TOOL_PROJECT_VECTOR_SEARCH,
                query=query,
                hit_count=len(hits),
                agent="research",
            ),
        }

    return research_agent


def make_graph_node(
    kg_tool: ProjectTool,
) -> Callable[[ProjectKnowledgeAgentState], dict[str, Any]]:
    def graph_agent(state: ProjectKnowledgeAgentState) -> dict[str, Any]:
        query = str(state.get("query") or "").strip()
        top_k = int(state.get("top_k") or 5)
        hits = kg_tool(query, limit=max(top_k, 10))
        notes_lines = [f"(prompt contract) {GRAPH_AGENT_SYSTEM.splitlines()[0]}"]
        if hits:
            notes_lines.append(f"Matched {len(hits)} node(s) via {kg_tool.name}.")
            for hit in hits[:5]:
                preview = str(hit.get("content_preview") or "").strip().replace("\n", " ")
                ntype = hit.get("node_type") or "node"
                notes_lines.append(f"- [{ntype}] {preview[:200]}")
        else:
            notes_lines.append("No knowledge-graph hits for this query.")
        notes = "\n".join(notes_lines)
        return {
            "graph_hits": hits,
            "graph_notes": notes,
            "tool_traces": _append_trace(
                state,
                tool=TOOL_PROJECT_KG_QUERY,
                query=query,
                hit_count=len(hits),
                agent="graph",
            ),
        }

    return graph_agent


def make_synthesis_node(
    *,
    mode: str = "stub",
    llm_call: Callable[[str, str], str] | None = None,
) -> Callable[[ProjectKnowledgeAgentState], dict[str, Any]]:
    agent_mode = (mode or "stub").strip().lower()

    def synthesis_agent(state: ProjectKnowledgeAgentState) -> dict[str, Any]:
        query = str(state.get("query") or "")
        research_hits = list(state.get("research_hits") or [])
        graph_hits = list(state.get("graph_hits") or [])
        research_notes = str(state.get("research_notes") or "")
        graph_notes = str(state.get("graph_notes") or "")

        sources_used: list[str] = []
        traces = list(state.get("tool_traces") or [])
        for tr in traces:
            name = str(tr.get("tool") or "")
            if name and name not in sources_used:
                sources_used.append(name)

        if agent_mode == "llm" and llm_call is not None:
            user_blob = (
                f"Query: {query}\n\n"
                f"Research notes:\n{research_notes}\n\n"
                f"Graph notes:\n{graph_notes}\n\n"
                f"Research hits JSON count: {len(research_hits)}\n"
                f"Graph hits JSON count: {len(graph_hits)}\n"
            )
            try:
                answer = llm_call(SYNTHESIS_AGENT_SYSTEM, user_blob)
            except Exception as exc:  # noqa: BLE001
                logger.warning("llm synthesis failed, falling back to stub: %s", exc)
                answer = stub_synthesis_answer(
                    query=query,
                    research_hits=research_hits,
                    graph_hits=graph_hits,
                    research_notes=research_notes,
                    graph_notes=graph_notes,
                )
        else:
            answer = stub_synthesis_answer(
                query=query,
                research_hits=research_hits,
                graph_hits=graph_hits,
                research_notes=research_notes,
                graph_notes=graph_notes,
            )

        return {
            "final_answer": answer,
            "sources_used": sources_used,
        }

    return synthesis_agent
