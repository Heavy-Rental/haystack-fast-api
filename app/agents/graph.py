"""Compile and run the Stage-1 project-knowledge LangGraph."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    make_graph_node,
    make_research_node,
    make_synthesis_node,
)
from app.agents.state import ProjectKnowledgeAgentState
from app.agents.tools import (
    TOOL_PROJECT_KG_QUERY,
    TOOL_PROJECT_VECTOR_SEARCH,
    build_session_tools,
)
from app.config import Settings, get_settings
from app.services.project_knowledge_session import ProjectKnowledgeSession


def build_project_knowledge_graph(
    session: ProjectKnowledgeSession,
    *,
    settings: Settings | None = None,
    top_k: int = 5,
    agent_mode: str | None = None,
    llm_call: Callable[[str, str], str] | None = None,
):
    """Build fixed sequential graph: research → graph → synthesis."""
    cfg = settings or get_settings()
    mode = (agent_mode if agent_mode is not None else cfg.project_agent_mode) or "stub"
    tools = build_session_tools(session, settings=cfg, top_k=top_k)

    builder = StateGraph(ProjectKnowledgeAgentState)
    builder.add_node(
        "research_agent",
        make_research_node(tools[TOOL_PROJECT_VECTOR_SEARCH]),
    )
    builder.add_node(
        "graph_agent",
        make_graph_node(tools[TOOL_PROJECT_KG_QUERY]),
    )
    builder.add_node(
        "synthesis_agent",
        make_synthesis_node(mode=str(mode), llm_call=llm_call),
    )
    builder.add_edge(START, "research_agent")
    builder.add_edge("research_agent", "graph_agent")
    builder.add_edge("graph_agent", "synthesis_agent")
    builder.add_edge("synthesis_agent", END)
    return builder.compile()


def run_project_knowledge_agents(
    session: ProjectKnowledgeSession,
    *,
    query: str,
    top_k: int | None = None,
    settings: Settings | None = None,
    agent_mode: str | None = None,
    llm_call: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Invoke the multi-agent graph for a project knowledge session."""
    cfg = settings or get_settings()
    k = int(top_k if top_k is not None else cfg.project_agent_top_k)
    graph = build_project_knowledge_graph(
        session,
        settings=cfg,
        top_k=k,
        agent_mode=agent_mode,
        llm_call=llm_call,
    )
    initial: ProjectKnowledgeAgentState = {
        "user_id": session.user_id,
        "ingest_id": session.ingest_id,
        "query": query,
        "top_k": k,
        "research_hits": [],
        "graph_hits": [],
        "tool_traces": [],
        "sources_used": [],
        "research_notes": "",
        "graph_notes": "",
        "final_answer": "",
    }
    return dict(graph.invoke(initial))
