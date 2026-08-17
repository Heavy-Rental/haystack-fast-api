"""Coordinator gate [4]: forced non-LLM indexing edge (Phase 3 / S3).

Architecture:
  START → index_gate → END

``index_gate`` always invokes ``run_indexing_from_request`` (in-process tool
wrapping ``IndexingIngestService``). It is **not** an LLM Worker and does not
use free-form tool calling.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, TypedDict

from haystack.dataclasses import ByteStream
from langgraph.graph import END, START, StateGraph

from app.agents.tools import TOOL_RUN_INDEXING, run_indexing_from_request
from app.core.exceptions import BadRequestError
from app.schemas.indexing import IngestFromProjectSpecResponse
from app.services.indexing import IndexingIngestService


class IndexingGateState(TypedDict, total=False):
    """STM for the indexing gate graph (seed for later S7 ``indexing_ok``)."""

    user_id: str
    user_name: str | None
    project_text: str | None
    file_sources: list[ByteStream]
    start_date: date | None
    end_date: date | None
    indexing_ok: bool
    ingest_id: str
    response: IngestFromProjectSpecResponse | None
    error_message: str
    tool_traces: list[dict[str, Any]]


@dataclass
class IndexingGateResult:
    """Outcome of ``run_indexing_gate`` (success path always has response)."""

    indexing_ok: bool
    response: IngestFromProjectSpecResponse | None = None
    error_message: str | None = None
    tool_traces: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ingest_id(self) -> str | None:
        if self.response is not None:
            return self.response.ingest_id
        return None


def _gate_trace(
    *,
    indexing_ok: bool,
    ingest_id: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "role": "coordinator",
        "node": "index_gate",
        "tool": TOOL_RUN_INDEXING,
        "indexing_ok": indexing_ok,
    }
    if ingest_id:
        trace["ingest_id"] = ingest_id
    if error_message:
        trace["error_message"] = error_message
    return trace


def make_index_gate_node(
    service: IndexingIngestService | None = None,
) -> Callable[[IndexingGateState], dict[str, Any]]:
    """Build the forced index_gate node (deterministic tool call, no LLM)."""

    def index_gate(state: IndexingGateState) -> dict[str, Any]:
        traces = list(state.get("tool_traces") or [])
        try:
            response = run_indexing_from_request(
                user_id=str(state.get("user_id") or ""),
                user_name=state.get("user_name"),
                project_text=state.get("project_text"),
                file_sources=state.get("file_sources"),
                start_date=state.get("start_date"),
                end_date=state.get("end_date"),
                service=service,
            )
            traces.append(
                _gate_trace(
                    indexing_ok=True,
                    ingest_id=response.ingest_id,
                )
            )
            return {
                "indexing_ok": True,
                "ingest_id": response.ingest_id,
                "response": response,
                "error_message": "",
                "tool_traces": traces,
            }
        except BadRequestError as exc:
            msg = exc.message
            traces.append(
                _gate_trace(indexing_ok=False, error_message=msg)
            )
            return {
                "indexing_ok": False,
                "ingest_id": "",
                "response": None,
                "error_message": msg,
                "tool_traces": traces,
            }
        except Exception as exc:  # noqa: BLE001 — gate must not invent success
            msg = f"indexing gate failed: {exc}"
            traces.append(
                _gate_trace(indexing_ok=False, error_message=msg)
            )
            return {
                "indexing_ok": False,
                "ingest_id": "",
                "response": None,
                "error_message": msg,
                "tool_traces": traces,
            }

    return index_gate


def build_indexing_gate_graph(
    service: IndexingIngestService | None = None,
):
    """Compile ``START → index_gate → END`` (Coordinator gate [4])."""
    builder = StateGraph(IndexingGateState)
    builder.add_node("index_gate", make_index_gate_node(service=service))
    builder.add_edge(START, "index_gate")
    builder.add_edge("index_gate", END)
    return builder.compile()


def run_indexing_gate(
    *,
    user_id: str,
    user_name: str | None = None,
    project_text: str | None = None,
    file_sources: list[ByteStream] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    service: IndexingIngestService | None = None,
) -> IndexingGateResult:
    """Run the forced indexing gate; re-raise BadRequestError on failure.

    On success returns ``IndexingGateResult`` with lean response + traces.
    On failure sets ``indexing_ok=false`` in graph state then raises
    ``BadRequestError`` so HTTP remains 400 (parity with direct service).
    """
    graph = build_indexing_gate_graph(service=service)
    initial: IndexingGateState = {
        "user_id": user_id,
        "user_name": user_name,
        "project_text": project_text,
        "file_sources": list(file_sources or []),
        "start_date": start_date,
        "end_date": end_date,
        "indexing_ok": False,
        "ingest_id": "",
        "response": None,
        "error_message": "",
        "tool_traces": [],
    }
    final = dict(graph.invoke(initial))
    traces = list(final.get("tool_traces") or [])
    if not final.get("indexing_ok"):
        msg = str(final.get("error_message") or "indexing gate failed")
        raise BadRequestError(msg)

    response = final.get("response")
    if not isinstance(response, IngestFromProjectSpecResponse):
        raise BadRequestError("indexing gate produced no lean response")

    return IndexingGateResult(
        indexing_ok=True,
        response=response,
        error_message=None,
        tool_traces=traces,
    )
