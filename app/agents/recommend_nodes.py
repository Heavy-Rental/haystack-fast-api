"""Recommend-mode LangGraph nodes (S7.3 / Phase 7).

Coordinator gate check, Project Worker [5], Delegator, Fleet [6] and
Pricing [7] workers, plus a Coordinator-owned ``execute_needs`` scheduler
that applies fan-out cap without racing F-2 partition writes.

Workers do not spawn siblings. Tools are in-process / injected only.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Callable

from app.agents.fleet_tools import (
    TOOL_CHECK_BOOKING_AVAILABILITY,
    TOOL_DECOMPOSE_PROJECT_NEEDS,
    TOOL_FILTER_FLEET_CANDIDATES,
    TOOL_RETRIEVE_FLEET_ASSETS,
    decompose_project_needs,
)
from app.agents.neo4j_tools import (
    TEMPLATE_ASSET_NEIGHBORS,
    TOOL_NEO4J_CYPHER_READ,
)
from app.agents.tool_factory import (
    RecommendToolCatalog,
    WORKER_KIND_FLEET,
    WORKER_KIND_PRICING,
    neo4j_available,
    tools_for_worker,
    validate_work_plan,
)
from app.agents.recommend_state import (
    ROLE_DELEGATOR,
    ROLE_FLEET_WORKER,
    ROLE_PRICING_WORKER,
    ROLE_PROJECT_WORKER,
    RecommendAgentState,
    apply_partition_write,
    indexing_ok,
    write_fleet_slice,
    write_price_rows,
)
from app.agents.recommend_synthesis import synthesize_recommendation
from app.agents.recommend_traces import append_tool_trace, elapsed_ms, now
from app.agents.tools import TOOL_PREDICT_ASSET_PRICE
from app.pipelines.expand_quantity import expand_needs_to_unit_dicts
from app.services.need_decomposer import NeedDecomposer

PriceFn = Callable[..., dict[str, Any]]


def _as_dict(state: RecommendAgentState | dict[str, Any]) -> dict[str, Any]:
    return dict(state)


def _append_trace(
    state: RecommendAgentState | dict[str, Any],
    **fields: Any,
) -> list[dict[str, Any]]:
    return append_tool_trace(state, **fields)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text)


def duration_days_from_run(state: RecommendAgentState | dict[str, Any]) -> float:
    """Rental length from ``run`` dates; default 1 when a bound is missing."""
    run = _as_dict(state).get("run") or {}
    start = _parse_date(run.get("start_date"))
    end = _parse_date(run.get("end_date"))
    if start is not None and end is not None:
        return float(max(1, (end - start).days + 1))
    return 1.0


def check_gate(
    state: RecommendAgentState | dict[str, Any],
) -> dict[str, Any]:
    """Coordinator non-agent: record indexing gate; do not run tools."""
    started = now()
    ok = indexing_ok(state)
    traces = _append_trace(
        state,
        role="coordinator",
        node="check_gate",
        status="ok" if ok else "refused",
        gate=ok,
        duration_ms=elapsed_ms(started),
    )
    return {"tool_traces": traces}


def route_after_gate(state: RecommendAgentState | dict[str, Any]) -> str:
    return "synthesis" if not indexing_ok(state) else "project_worker"


def make_project_worker(
    source_text: str,
    *,
    catalog: RecommendToolCatalog | None = None,
    decomposer: NeedDecomposer | None = None,
) -> Callable[[RecommendAgentState], dict[str, Any]]:
    def project_worker(state: RecommendAgentState) -> dict[str, Any]:
        started = now()
        traces = _append_trace(
            state,
            role="worker",
            node="project_worker",
            status="start",
        )
        working = {**_as_dict(state), "tool_traces": traces}
        tool_started = now()
        if decomposer is not None:
            raw = decompose_project_needs(source_text, decomposer=decomposer)
        elif catalog is not None and TOOL_DECOMPOSE_PROJECT_NEEDS in catalog:
            raw = catalog.get(TOOL_DECOMPOSE_PROJECT_NEEDS)(source_text)
        else:
            raw = decompose_project_needs(source_text)
        traces = _append_trace(
            working,
            role="worker",
            node="project_worker",
            tool=TOOL_DECOMPOSE_PROJECT_NEEDS,
            status="ok",
            duration_ms=elapsed_ms(tool_started),
        )
        working["tool_traces"] = traces
        units = expand_needs_to_unit_dicts(list(raw or []))
        proposed = deepcopy(_as_dict(state))
        project = dict(proposed.get("project") or {})
        project["needs"] = units
        proposed["project"] = project
        traces = _append_trace(
            working,
            role="worker",
            node="project_worker",
            status="completed",
            duration_ms=elapsed_ms(started),
        )
        proposed["tool_traces"] = traces
        result = apply_partition_write(ROLE_PROJECT_WORKER, state, proposed)
        return {"project": result["project"], "tool_traces": result["tool_traces"]}

    return project_worker


def make_delegator(
    catalog: RecommendToolCatalog | None = None,
) -> Callable[[RecommendAgentState], dict[str, Any]]:
    def delegator(state: RecommendAgentState) -> dict[str, Any]:
        include_pricing = bool((_as_dict(state).get("run") or {}).get("include_pricing", True))
        needs = (_as_dict(state).get("project") or {}).get("needs") or []
        graph_ok = neo4j_available(catalog)
        plan: list[dict[str, Any]] = []
        if indexing_ok(state):
            for need in needs:
                if not isinstance(need, dict):
                    continue
                need_id = str(need.get("need_id") or "").strip()
                if not need_id:
                    continue
                fleet_tools = list(tools_for_worker(WORKER_KIND_FLEET))
                fleet_item: dict[str, Any] = {
                    "worker_kind": WORKER_KIND_FLEET,
                    "need_id": need_id,
                    "tool_allowlist": fleet_tools,
                }
                if graph_ok:
                    if TOOL_NEO4J_CYPHER_READ not in fleet_item["tool_allowlist"]:
                        fleet_item["tool_allowlist"] = [
                            *fleet_tools,
                            TOOL_NEO4J_CYPHER_READ,
                        ]
                else:
                    fleet_item["skip_tools"] = [TOOL_NEO4J_CYPHER_READ]
                plan.append(fleet_item)
                if include_pricing:
                    plan.append(
                        {
                            "worker_kind": WORKER_KIND_PRICING,
                            "need_id": need_id,
                            "tool_allowlist": list(
                                tools_for_worker(WORKER_KIND_PRICING)
                            ),
                        }
                    )
        validate_work_plan(plan)
        started = now()
        proposed = deepcopy(_as_dict(state))
        proposed["work_plan"] = plan
        proposed["tool_traces"] = _append_trace(
            state,
            role="delegator",
            node="delegator",
            status="ok",
            duration_ms=elapsed_ms(started),
        )
        result = apply_partition_write(ROLE_DELEGATOR, state, proposed)
        return {"work_plan": result["work_plan"], "tool_traces": result["tool_traces"]}

    return delegator


def _need_ids_from_plan(state: RecommendAgentState | dict[str, Any]) -> list[str]:
    plan = _as_dict(state).get("work_plan") or []
    ids: list[str] = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        if item.get("worker_kind") != WORKER_KIND_FLEET:
            continue
        need_id = str(item.get("need_id") or "").strip()
        if need_id and need_id not in ids:
            ids.append(need_id)
    return ids


def _batches(items: list[str], cap: int) -> list[list[str]]:
    width = max(1, int(cap))
    return [items[i : i + width] for i in range(0, len(items), width)]


def _find_need(
    state: RecommendAgentState | dict[str, Any], need_id: str
) -> dict[str, Any]:
    for need in (_as_dict(state).get("project") or {}).get("needs") or []:
        if isinstance(need, dict) and str(need.get("need_id")) == need_id:
            return need
    return {"need_id": need_id}


def _fleet_plan_item(
    state: RecommendAgentState | dict[str, Any], need_id: str
) -> dict[str, Any]:
    for item in _as_dict(state).get("work_plan") or []:
        if not isinstance(item, dict):
            continue
        if item.get("worker_kind") != WORKER_KIND_FLEET:
            continue
        if str(item.get("need_id") or "") == need_id:
            return item
    return {}


def _should_run_neo4j(
    state: RecommendAgentState | dict[str, Any],
    need_id: str,
    catalog: RecommendToolCatalog,
) -> bool:
    if TOOL_NEO4J_CYPHER_READ not in catalog:
        return False
    item = _fleet_plan_item(state, need_id)
    skip = item.get("skip_tools") or []
    if TOOL_NEO4J_CYPHER_READ in skip:
        return False
    allow = item.get("tool_allowlist")
    if allow is not None and TOOL_NEO4J_CYPHER_READ not in allow:
        return False
    return neo4j_available(catalog)


def run_fleet_worker(
    state: RecommendAgentState | dict[str, Any],
    need_id: str,
    catalog: RecommendToolCatalog,
) -> RecommendAgentState:
    """Fleet Worker [6] for one need_id (must run before pricing)."""
    started = now()
    working = deepcopy(_as_dict(state))
    working["tool_traces"] = _append_trace(
        state,
        role="worker",
        node="fleet_worker",
        need_id=need_id,
        status="start",
    )

    need = _find_need(working, need_id)
    retrieve = catalog.get(TOOL_RETRIEVE_FLEET_ASSETS)
    tool_started = now()
    assets = list(retrieve() or [])
    working["tool_traces"] = _append_trace(
        working,
        role="worker",
        node="fleet_worker",
        need_id=need_id,
        tool=TOOL_RETRIEVE_FLEET_ASSETS,
        status="ok",
        duration_ms=elapsed_ms(tool_started),
    )

    filt = catalog.get(TOOL_FILTER_FLEET_CANDIDATES)
    tool_started = now()
    candidates = list(filt(assets, unit_need=need) or [])
    working["tool_traces"] = _append_trace(
        working,
        role="worker",
        node="fleet_worker",
        need_id=need_id,
        tool=TOOL_FILTER_FLEET_CANDIDATES,
        status="ok",
        duration_ms=elapsed_ms(tool_started),
    )

    run = working.get("run") or {}
    avail = catalog.get(TOOL_CHECK_BOOKING_AVAILABILITY)
    tool_started = now()
    split = avail(
        candidates,
        start_date=run.get("start_date"),
        end_date=run.get("end_date"),
    )
    working["tool_traces"] = _append_trace(
        working,
        role="worker",
        node="fleet_worker",
        need_id=need_id,
        tool=TOOL_CHECK_BOOKING_AVAILABILITY,
        status="ok",
        duration_ms=elapsed_ms(tool_started),
    )

    available = list((split or {}).get("available") or [])
    graph_notes: list[dict[str, Any]] = []
    source_tables = ["assets", "bookings"]
    if _should_run_neo4j(working, need_id, catalog):
        read = catalog.get(TOOL_NEO4J_CYPHER_READ)
        seen: set[str] = set()
        for cand in available:
            asset_id = str((cand or {}).get("asset_id") or "")
            if not asset_id:
                continue
            tool_started = now()
            hits = list(
                read(template=TEMPLATE_ASSET_NEIGHBORS, asset_id=asset_id) or []
            )
            working["tool_traces"] = _append_trace(
                working,
                role="worker",
                node="fleet_worker",
                need_id=need_id,
                tool=TOOL_NEO4J_CYPHER_READ,
                status="ok",
                duration_ms=elapsed_ms(tool_started),
            )
            for note in hits:
                note_id = str((note or {}).get("id") or "")
                if note_id and note_id in seen:
                    continue
                if note_id:
                    seen.add(note_id)
                graph_notes.append(note)
        if graph_notes:
            source_tables.append("kg-2")

    # Persist traces first (fleet role may write tool_traces), then fleet slice.
    traced = apply_partition_write(ROLE_FLEET_WORKER, state, working, need_id=need_id)
    updated = write_fleet_slice(
        traced,
        need_id,
        candidates=available,
        unavailable=list((split or {}).get("unavailable") or []),
        source_tables=source_tables,
        graph_notes=graph_notes or None,
    )
    done = deepcopy(_as_dict(updated))
    done["tool_traces"] = _append_trace(
        updated,
        role="worker",
        node="fleet_worker",
        need_id=need_id,
        status="completed",
        duration_ms=elapsed_ms(started),
    )
    return apply_partition_write(ROLE_FLEET_WORKER, updated, done, need_id=need_id)


def _call_price(
    *,
    price_fn: PriceFn | None,
    catalog: RecommendToolCatalog,
    **kwargs: Any,
) -> dict[str, Any]:
    if price_fn is not None:
        result = price_fn(**kwargs)
    else:
        result = catalog.get(TOOL_PREDICT_ASSET_PRICE)(**kwargs)
    return dict(result or {})


def run_pricing_worker(
    state: RecommendAgentState | dict[str, Any],
    need_id: str,
    catalog: RecommendToolCatalog,
    *,
    price_fn: PriceFn | None = None,
) -> RecommendAgentState:
    """Pricing Worker [7] for one need_id (candidates must already exist)."""
    started = now()
    working = deepcopy(_as_dict(state))
    working["tool_traces"] = _append_trace(
        state,
        role="worker",
        node="pricing_worker",
        need_id=need_id,
        status="start",
    )

    slice_ = (working.get("fleet_by_need") or {}).get(need_id) or {}
    candidates = [
        c for c in (slice_.get("candidates") or []) if isinstance(c, dict)
    ]
    duration = duration_days_from_run(working)
    run = working.get("run") or {}
    start = _parse_date(run.get("start_date"))
    end = _parse_date(run.get("end_date"))

    rows: list[dict[str, Any]] = []
    for cand in candidates:
        asset_id = cand.get("asset_id")
        tool_started = now()
        try:
            price = _call_price(
                price_fn=price_fn,
                catalog=catalog,
                category=str(cand.get("category") or ""),
                condition=str(cand.get("condition") or "GOOD"),
                duration_days=duration,
                capacity=cand.get("capacity"),
                distance_km=float(cand.get("distance_km") or 0.0),
                platform_height=cand.get("platform_height"),
                min_daily_rate=float(cand.get("min_daily_rate") or 0.0),
                max_daily_rate=float(cand.get("max_daily_rate") or 0.0),
                asset_id=asset_id,
                start_date=start,
                end_date=end,
            )
            working["tool_traces"] = _append_trace(
                working,
                role="worker",
                node="pricing_worker",
                need_id=need_id,
                tool=TOOL_PREDICT_ASSET_PRICE,
                status="ok",
                duration_ms=elapsed_ms(tool_started),
            )
        except Exception:
            working["tool_traces"] = _append_trace(
                working,
                role="worker",
                node="pricing_worker",
                need_id=need_id,
                tool=TOOL_PREDICT_ASSET_PRICE,
                status="error",
                duration_ms=elapsed_ms(tool_started),
            )
            continue
        rate = price.get("daily_rate")
        try:
            if rate is None or float(rate) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        if asset_id is None:
            continue
        row = {
            "asset_id": asset_id,
            "daily_rate": price.get("daily_rate"),
            "total_price": price.get("total_price"),
            "currency": price.get("currency") or "SGD",
            "was_clamped": price.get("was_clamped"),
            "model_version": price.get("model_version"),
            "explanation": price.get("explanation"),
        }
        rows.append(row)

    traced = apply_partition_write(
        ROLE_PRICING_WORKER, state, working, need_id=need_id
    )
    if rows:
        updated = write_price_rows(traced, need_id, rows)
    else:
        # Legal empty write for this need (no silent zeros).
        updated = write_price_rows(traced, need_id, [])
    done = deepcopy(_as_dict(updated))
    done["tool_traces"] = _append_trace(
        updated,
        role="worker",
        node="pricing_worker",
        need_id=need_id,
        status="completed",
        duration_ms=elapsed_ms(started),
    )
    return apply_partition_write(
        ROLE_PRICING_WORKER, updated, done, need_id=need_id
    )


def make_execute_needs(
    catalog: RecommendToolCatalog,
    *,
    fanout_cap: int = 4,
    price_fn: PriceFn | None = None,
    include_pricing: bool = True,
) -> Callable[[RecommendAgentState], dict[str, Any]]:
    def execute_needs(state: RecommendAgentState) -> dict[str, Any]:
        current: RecommendAgentState | dict[str, Any] = deepcopy(_as_dict(state))
        validate_work_plan(current.get("work_plan") or [])
        need_ids = _need_ids_from_plan(current)
        cap = max(1, int(fanout_cap))
        run_include = bool(
            (_as_dict(current).get("run") or {}).get("include_pricing", include_pricing)
        )
        for batch in _batches(need_ids, cap):
            for need_id in batch:
                current = run_fleet_worker(current, need_id, catalog)
            if not run_include:
                continue
            for need_id in batch:
                slice_ = (current.get("fleet_by_need") or {}).get(need_id) or {}
                if not (slice_.get("candidates") or []):
                    continue
                current = run_pricing_worker(
                    current, need_id, catalog, price_fn=price_fn
                )
        return {
            "fleet_by_need": current.get("fleet_by_need") or {},
            "prices_by_need": current.get("prices_by_need") or {},
            "tool_traces": current.get("tool_traces") or [],
        }

    return execute_needs


def make_synthesis_node(
    *,
    agent_mode: str = "stub",
    rationale_fn: Callable[..., str] | None = None,
) -> Callable[[RecommendAgentState], dict[str, Any]]:
    def synthesis(state: RecommendAgentState) -> dict[str, Any]:
        result = synthesize_recommendation(
            state, agent_mode=agent_mode, rationale_fn=rationale_fn
        )
        return {
            "recommendation": result["recommendation"],
            "tool_traces": result["tool_traces"],
        }

    return synthesis
