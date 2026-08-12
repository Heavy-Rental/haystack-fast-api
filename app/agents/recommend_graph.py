"""Recommend-mode LangGraph DAG (S7.3 / Phase 7).

Isolated from Stage-1 Q&A (``app.agents.graph``). Sequence:

    START → check_gate → (refuse) synthesis → END
                      → project_worker → delegator → execute_needs → synthesis → END

Fan-out: must-seq fleet→price within a need; batches of ``RECOMMEND_FANOUT_CAP``
across needs. HTTP Call 2 is not wired here (S7.5).
"""

from __future__ import annotations

from typing import Any, Callable

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
from app.agents.tool_factory import RecommendToolCatalog, build_recommend_tool_catalog
from app.config import Settings, get_settings
from app.services.need_decomposer import NeedDecomposer


def build_recommend_graph(
    *,
    source_text: str,
    catalog: RecommendToolCatalog | None = None,
    decomposer: NeedDecomposer | None = None,
    fanout_cap: int = 4,
    price_fn: Callable[..., dict[str, Any]] | None = None,
    include_pricing: bool = True,
):
    """Compile the recommend C/W/D graph (stub synthesis, injected tools)."""
    tools = catalog if catalog is not None else build_recommend_tool_catalog(
        backend="fake", decomposer=decomposer
    )
    cap = max(1, int(fanout_cap))

    builder = StateGraph(RecommendAgentState)
    builder.add_node("check_gate", check_gate)
    builder.add_node(
        "project_worker",
        make_project_worker(
            source_text, catalog=tools, decomposer=decomposer
        ),
    )
    builder.add_node("delegator", make_delegator())
    builder.add_node(
        "execute_needs",
        make_execute_needs(
            tools,
            fanout_cap=cap,
            price_fn=price_fn,
            include_pricing=include_pricing,
        ),
    )
    builder.add_node("synthesis", make_synthesis_node())
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
) -> RecommendAgentState:
    """Invoke one recommend-mode graph run. Does not touch Call 2 HTTP."""
    cfg = settings or get_settings()
    cap = int(fanout_cap) if fanout_cap is not None else int(cfg.recommend_fanout_cap)
    cap = max(1, cap)

    tools = catalog if catalog is not None else build_recommend_tool_catalog(
        backend="fake", decomposer=decomposer
    )

    graph = build_recommend_graph(
        source_text=source_text,
        catalog=tools,
        decomposer=decomposer,
        fanout_cap=cap,
        price_fn=price_fn,
        include_pricing=include_pricing,
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
