"""G-1 tool_traces helpers for the recommend graph (S7.6 / Phase 7).

Contract fields: role, node, status; need_id on fan-out; tool when a
named tool ran; duration_ms on terminal spans (ok / completed / error /
refused). Traces stay on RecommendAgentState — not the Call 2 quote DTO.
"""

from __future__ import annotations

import time
from typing import Any

from app.agents.recommend_state import RecommendAgentState

TERMINAL_TRACE_STATUSES: frozenset[str] = frozenset(
    {"ok", "completed", "error", "refused"}
)


def now() -> float:
    """Monotonic clock for span duration."""
    return time.perf_counter()


def elapsed_ms(started_at: float) -> float:
    """Non-negative milliseconds since ``started_at`` (perf_counter)."""
    return max(0.0, (time.perf_counter() - started_at) * 1000.0)


def append_tool_trace(
    state: RecommendAgentState | dict[str, Any],
    *,
    role: str,
    node: str,
    status: str,
    need_id: str | None = None,
    tool: str | None = None,
    duration_ms: float | None = None,
    **extra: Any,
) -> list[dict[str, Any]]:
    """Append one trace event and return the new ``tool_traces`` list."""
    traces = list((dict(state).get("tool_traces") or []))
    event: dict[str, Any] = {
        "role": role,
        "node": node,
        "status": status,
    }
    if need_id is not None:
        event["need_id"] = need_id
    if tool is not None:
        event["tool"] = tool
    if duration_ms is None and status in TERMINAL_TRACE_STATUSES:
        duration_ms = 0.0
    if duration_ms is not None:
        event["duration_ms"] = float(duration_ms)
    for key, value in extra.items():
        if value is not None:
            event[key] = value
    traces.append(event)
    return traces
