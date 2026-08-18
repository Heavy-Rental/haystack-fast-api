"""Tool-free Coordinator synthesis [8] (S7.4 / Phase 7).

Merges ``fleet_by_need`` + ``prices_by_need`` into ``results_by_need``.
Never calls tools. Never invents ``asset_id`` or rates. Empty fleet or
missing prices → ``item: null`` + warning (no silent zeros).

See Feasibility_Study multi-agent-synthesis-recommend-output.md and
implementation-plan Stage S7.4.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from app.agents.recommend_prompts import apply_rationale_only
from app.agents.recommend_state import (
    ROLE_COORDINATOR,
    RecommendAgentState,
    apply_partition_write,
    indexing_ok,
)
from app.agents.recommend_traces import append_tool_trace, elapsed_ms, now
from app.pipelines.rank_rationale_generator import (
    _tie_break,
    build_evidence_rationale,
    score_need_match,
)

logger = logging.getLogger(__name__)


class SynthesisSchemaError(ValueError):
    """``results_by_need`` failed the Coordinator output schema check."""


def validate_recommendation_shape(results: Any) -> None:
    """Reject malformed ``results_by_need`` rows before F-2 apply."""
    if not isinstance(results, list):
        raise SynthesisSchemaError(f"results_by_need must be a list, got {type(results).__name__}")
    for i, row in enumerate(results):
        if not isinstance(row, dict):
            raise SynthesisSchemaError(f"results_by_need[{i}] must be a dict")
        if not str(row.get("need_id") or "").strip():
            raise SynthesisSchemaError(f"results_by_need[{i}] missing need_id")
        if "item" not in row:
            raise SynthesisSchemaError(f"results_by_need[{i}] missing item")
        item = row.get("item")
        if item is not None and not isinstance(item, dict):
            raise SynthesisSchemaError(f"results_by_need[{i}].item must be a dict or null")
        warnings = row.get("warnings")
        if not isinstance(warnings, list):
            raise SynthesisSchemaError(f"results_by_need[{i}].warnings must be a list")


def _need_rows(state: RecommendAgentState | dict[str, Any]) -> list[dict[str, Any]]:
    project = state.get("project") or {}
    needs = list(project.get("needs") or [])
    return [n for n in needs if isinstance(n, dict) and n.get("need_id")]


def _price_index(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        asset_id = row.get("asset_id")
        rate = row.get("daily_rate")
        if asset_id is None or rate is None:
            continue
        try:
            if float(rate) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        out[str(asset_id)] = row
    return out


def _pick_item(
    *,
    need: dict[str, Any],
    slice_: dict[str, Any],
    price_rows: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    candidates = [c for c in (slice_.get("candidates") or []) if isinstance(c, dict)]
    if not candidates:
        warnings.append(f"no fleet match for need_id={need.get('need_id')!r}")
        return None, warnings

    priced = _price_index(price_rows)
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        availability = cand.get("availability")
        if availability not in (None, "available"):
            continue
        asset_id = cand.get("asset_id")
        if asset_id is None:
            continue
        price = priced.get(str(asset_id))
        if price is None:
            continue
        row = dict(cand)
        row["pricing"] = {
            "daily_rate": price.get("daily_rate"),
            "total_price": price.get("total_price"),
            "currency": price.get("currency") or "SGD",
            "model_version": price.get("model_version"),
            "explanation": price.get("explanation"),
            "was_clamped": price.get("was_clamped"),
        }
        row["match_score"] = score_need_match(need, row)
        scored.append(row)

    if not scored:
        warnings.append(
            f"pricing unavailable for need_id={need.get('need_id')!r}; "
            "no item without a tool-backed rate"
        )
        return None, warnings

    scored.sort(
        key=lambda c: (float(c.get("match_score") or 0.0), *_tie_break(c)),
        reverse=True,
    )
    cand = scored[0]
    asset_id = cand.get("asset_id")
    price = cand.get("pricing") or {}
    rationale = build_evidence_rationale(need, cand)
    fleet_pk = cand.get("id")
    try:
        fleet_id = int(fleet_pk) if fleet_pk is not None else None
    except (TypeError, ValueError):
        fleet_id = None
    item = {
        "equipment_type": cand.get("equipment_type"),
        "asset_id": str(asset_id),
        "fleet_id": fleet_id,
        "name": cand.get("name"),
        "rank": 1,
        "match_score": cand.get("match_score"),
        "rationale": rationale,
        "pricing": {
            "daily_rate": price.get("daily_rate"),
            "total_price": price.get("total_price"),
            "currency": price.get("currency") or "SGD",
            "model_version": price.get("model_version"),
            "explanation": price.get("explanation"),
            "was_clamped": price.get("was_clamped"),
        },
        "availability": cand.get("availability") or "available",
        "platform_height": cand.get("platform_height"),
    }
    return item, warnings


def synthesize_recommendation(
    state: RecommendAgentState | dict[str, Any],
    *,
    agent_mode: str = "stub",
    rationale_fn: Callable[..., Any] | None = None,
) -> RecommendAgentState:
    """Coordinator [8]: merge fleet + prices into ``results_by_need``.

    ``asset_id`` / rates stay code-first (tool-backed). Optional ``rationale_fn``
    (llm mode) may rewrite rationale text only via ``apply_rationale_only``.
    """
    started = now()
    current = deepcopy(dict(state))
    results: list[dict[str, Any]] = []
    top_warnings: list[str] = list((current.get("recommendation") or {}).get("warnings") or [])

    if not indexing_ok(current):
        top_warnings.append("indexing gate refused: indexing_ok=false; no recommend")
    else:
        fleet = current.get("fleet_by_need") or {}
        prices = current.get("prices_by_need") or {}
        for need in _need_rows(current):
            need_id = str(need["need_id"])
            slice_ = fleet.get(need_id) or {}
            item, warnings = _pick_item(
                need=need,
                slice_=slice_,
                price_rows=prices.get(need_id),
            )
            if (
                item is not None
                and str(agent_mode or "stub").strip().lower() == "llm"
                and rationale_fn is not None
            ):
                try:
                    payload = rationale_fn(
                        description=str(need.get("description") or ""),
                        asset_id=item.get("asset_id"),
                        item=item,
                    )
                    item = apply_rationale_only(item, payload)
                except Exception:
                    logger.exception(
                        "recommend synthesis rationale failed; keeping tool-backed item"
                    )
            results.append({"need_id": need_id, "item": item, "warnings": warnings})

    validate_recommendation_shape(results)

    proposed = deepcopy(current)
    proposed["recommendation"] = {
        "results_by_need": results,
        "warnings": top_warnings,
    }
    proposed["tool_traces"] = append_tool_trace(
        proposed,
        role="coordinator",
        node="synthesis",
        status="ok",
        duration_ms=elapsed_ms(started),
    )
    return apply_partition_write(ROLE_COORDINATOR, current, proposed)
