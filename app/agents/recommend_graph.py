"""Recommend-mode LangGraph DAG (S7.3 / Phase 7).

Isolated from Stage-1 Q&A (``app.agents.graph``). Sequence:

    START → check_gate → (refuse) synthesis → END
                      → project_worker → delegator → execute_needs → synthesis → END

Fan-out: must-seq fleet→price within a need; batches of ``RECOMMEND_FANOUT_CAP``
across needs. HTTP Call 2 is wired behind ``RECOMMEND_VIA_AGENT_GRAPH`` (S7.5).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.recommend_nodes import (
    check_gate,
    make_delegator,
    make_execute_needs,
    make_project_worker,
    make_synthesis_node,
    route_after_gate,
)
from app.agents.recommend_state import RecommendAgentState, empty_recommend_state
from app.agents.tool_factory import (
    RecommendRuntime,
    RecommendToolCatalog,
    build_recommend_runtime,
    build_recommend_tool_catalog,
)
from app.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.services.need_decomposer import NeedDecomposer
from app.services.project_knowledge_session import (
    ProjectKnowledgeSession,
    get_project_knowledge_registry,
)


def build_recommend_graph(
    *,
    source_text: str,
    catalog: RecommendToolCatalog | None = None,
    decomposer: NeedDecomposer | None = None,
    fanout_cap: int = 4,
    price_fn: Callable[..., dict[str, Any]] | None = None,
    include_pricing: bool = True,
    runtime: RecommendRuntime | None = None,
    agent_mode: str | None = None,
    rationale_fn: Callable[..., Any] | None = None,
):
    """Compile the recommend C/W/D graph (injected tools + prompt-backed stub)."""
    if runtime is not None:
        tools = runtime.catalog
        mode = agent_mode if agent_mode is not None else runtime.agent_mode
    else:
        tools = catalog if catalog is not None else build_recommend_tool_catalog(
            backend="fake", decomposer=decomposer
        )
        mode = agent_mode if agent_mode is not None else "stub"
    cap = max(1, int(fanout_cap))

    builder = StateGraph(RecommendAgentState)
    builder.add_node("check_gate", check_gate)
    builder.add_node(
        "project_worker",
        make_project_worker(
            source_text, catalog=tools, decomposer=decomposer
        ),
    )
    builder.add_node("delegator", make_delegator(catalog=tools))
    builder.add_node(
        "execute_needs",
        make_execute_needs(
            tools,
            fanout_cap=cap,
            price_fn=price_fn,
            include_pricing=include_pricing,
        ),
    )
    builder.add_node(
        "synthesis",
        make_synthesis_node(agent_mode=str(mode), rationale_fn=rationale_fn),
    )
    builder.add_edge(START, "check_gate")
    builder.add_conditional_edges(
        "check_gate",
        route_after_gate,
        {"project_worker": "project_worker", "synthesis": "synthesis"},
    )
    builder.add_edge("project_worker", "delegator")
    builder.add_edge("delegator", "execute_needs")
    builder.add_edge("execute_needs", "synthesis")
    builder.add_edge("synthesis", END)
    return builder.compile()


def run_recommend_graph(
    *,
    user_id: str,
    ingest_id: str,
    indexing_ok: bool,
    source_text: str,
    start_date: str | None = None,
    end_date: str | None = None,
    include_pricing: bool = True,
    catalog: RecommendToolCatalog | None = None,
    decomposer: NeedDecomposer | None = None,
    fanout_cap: int | None = None,
    price_fn: Callable[..., dict[str, Any]] | None = None,
    settings: Settings | None = None,
    runtime: RecommendRuntime | None = None,
    agent_mode: str | None = None,
    rationale_fn: Callable[..., Any] | None = None,
    project_session: ProjectKnowledgeSession | None = None,
) -> RecommendAgentState:
    """Invoke one recommend-mode graph run (Call 2 uses this when flagged)."""
    cfg = settings or get_settings()
    cap = int(fanout_cap) if fanout_cap is not None else int(cfg.recommend_fanout_cap)
    cap = max(1, cap)

    owned_session = None
    tools_catalog = catalog
    pk_session = project_session
    if pk_session is None:
        try:
            pk_session = get_project_knowledge_registry().get(user_id, ingest_id)
        except NotFoundError:
            pk_session = None
    if runtime is None and tools_catalog is None:
        kind = str(getattr(cfg, "fleet_backend", None) or "fake").strip().lower()
        if kind == "sql":
            from app.core.db import SessionLocal

            owned_session = SessionLocal()
            tools_catalog = build_recommend_tool_catalog(
                backend="sql",
                session=owned_session,
                decomposer=decomposer,
                settings=cfg,
                project_session=pk_session,
            )
        else:
            tools_catalog = build_recommend_tool_catalog(
                backend="fake",
                decomposer=decomposer,
                settings=cfg,
                project_session=pk_session,
            )

    injected = runtime
    if injected is None:
        injected = build_recommend_runtime(
            catalog=tools_catalog,
            decomposer=decomposer,
            settings=cfg,
            agent_mode=agent_mode
            if agent_mode is not None
            else (cfg.project_agent_mode or "stub"),
        )
    tools = injected.catalog

    try:
        return _invoke_recommend_graph(
            user_id=user_id,
            ingest_id=ingest_id,
            indexing_ok=indexing_ok,
            source_text=source_text,
            start_date=start_date,
            end_date=end_date,
            include_pricing=include_pricing,
            tools=tools,
            injected=injected,
            decomposer=decomposer,
            cap=cap,
            price_fn=price_fn,
            agent_mode=agent_mode,
            rationale_fn=rationale_fn,
        )
    finally:
        if owned_session is not None:
            owned_session.close()


def _invoke_recommend_graph(
    *,
    user_id: str,
    ingest_id: str,
    indexing_ok: bool,
    source_text: str,
    start_date: str | None,
    end_date: str | None,
    include_pricing: bool,
    tools: RecommendToolCatalog,
    injected: RecommendRuntime,
    decomposer: NeedDecomposer | None,
    cap: int,
    price_fn: Callable[..., dict[str, Any]] | None,
    agent_mode: str | None,
    rationale_fn: Callable[..., Any] | None,
) -> RecommendAgentState:
    graph = build_recommend_graph(
        source_text=source_text,
        catalog=tools,
        decomposer=decomposer,
        fanout_cap=cap,
        price_fn=price_fn,
        include_pricing=include_pricing,
        runtime=injected,
        agent_mode=agent_mode,
        rationale_fn=rationale_fn,
    )
    initial = empty_recommend_state(
        user_id=user_id,
        ingest_id=ingest_id,
        indexing_ok=indexing_ok,
        start_date=start_date,
        end_date=end_date,
        include_pricing=include_pricing,
    )
    return dict(graph.invoke(initial))  # type: ignore[return-value]
