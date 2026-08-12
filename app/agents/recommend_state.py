"""Recommend-mode LangGraph state + F-2 partition validation (S7.0 / Phase 7).

Workers write only their partition. Illegal transitions raise
``StateTransitionError`` (no partial corrupt write).

See Feasibility_Study multi-agent C/W/D §10.0.3 / §10.0.5 F-2 and
implementation-plan Stage S7.0.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, TypedDict

# ---------------------------------------------------------------------------
# Roles (C/W/D alias layer)
# ---------------------------------------------------------------------------

AgentRole = Literal[
    "coordinator",
    "delegator",
    "project_worker",
    "fleet_worker",
    "pricing_worker",
]

ROLE_COORDINATOR: AgentRole = "coordinator"
ROLE_DELEGATOR: AgentRole = "delegator"
ROLE_PROJECT_WORKER: AgentRole = "project_worker"
ROLE_FLEET_WORKER: AgentRole = "fleet_worker"
ROLE_PRICING_WORKER: AgentRole = "pricing_worker"

ALL_ROLES: frozenset[str] = frozenset(
    {
        ROLE_COORDINATOR,
        ROLE_DELEGATOR,
        ROLE_PROJECT_WORKER,
        ROLE_FLEET_WORKER,
        ROLE_PRICING_WORKER,
    }
)

# Top-level partition keys each role may write (exclusive ownership).
ROLE_WRITE_PARTITIONS: dict[str, frozenset[str]] = {
    ROLE_COORDINATOR: frozenset({"recommendation", "tool_traces", "persistence"}),
    ROLE_DELEGATOR: frozenset({"work_plan", "tool_traces"}),
    ROLE_PROJECT_WORKER: frozenset({"project", "tool_traces"}),
    ROLE_FLEET_WORKER: frozenset({"fleet_by_need", "tool_traces"}),
    ROLE_PRICING_WORKER: frozenset({"prices_by_need", "tool_traces"}),
}

# Partitions that any role may append traces to (shared audit bus).
TRACE_PARTITION = "tool_traces"

# Top-level keys that form the recommend state schema.
STATE_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "run",
        "project",
        "work_plan",
        "fleet_by_need",
        "prices_by_need",
        "recommendation",
        "tool_traces",
        "persistence",
    }
)


# ---------------------------------------------------------------------------
# TypedDict schemas (illustrative partitions from C/W/D §10.0.3)
# ---------------------------------------------------------------------------


class RunState(TypedDict, total=False):
    mode: str
    user_id: str
    ingest_id: str
    indexing_ok: bool
    start_date: str | None
    end_date: str | None
    include_pricing: bool


class ProjectNeed(TypedDict, total=False):
    need_id: str
    description: str
    equipment_type_hint: str
    equipment_hints: list[str]
    quantity: int
    constraints: dict[str, Any]


class ProjectState(TypedDict, total=False):
    research_notes: str
    graph_notes: str
    needs: list[ProjectNeed]


class WorkPlanItem(TypedDict, total=False):
    worker_kind: str
    need_id: str
    tool_allowlist: list[str]


class FleetCandidate(TypedDict, total=False):
    asset_id: str
    category: str
    equipment_type: str
    condition: str
    capacity: float | None
    platform_height: float | None
    min_daily_rate: float
    max_daily_rate: float


class FleetSlice(TypedDict, total=False):
    candidates: list[FleetCandidate]
    unavailable: list[FleetCandidate]
    source_tables: list[str]


class PriceRow(TypedDict, total=False):
    asset_id: str
    daily_rate: float
    total_price: float
    currency: str
    was_clamped: bool
    model_version: str
    explanation: str


class RecommendationState(TypedDict, total=False):
    results_by_need: list[dict[str, Any]]
    warnings: list[str]


class PersistenceState(TypedDict, total=False):
    ai_recommendation_id: str | None
    recommendation_item_ids: list[str]


class RecommendAgentState(TypedDict, total=False):
    """Shared STM for one recommend graph run (Phase 7)."""

    run: RunState
    project: ProjectState
    work_plan: list[WorkPlanItem]
    fleet_by_need: dict[str, FleetSlice]
    prices_by_need: dict[str, list[PriceRow]]
    recommendation: RecommendationState
    tool_traces: list[dict[str, Any]]
    persistence: PersistenceState


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StateTransitionError(ValueError):
    """Illegal state write rejected by F-2 validation."""


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def empty_recommend_state(
    *,
    user_id: str = "",
    ingest_id: str = "",
    indexing_ok: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    include_pricing: bool = True,
) -> RecommendAgentState:
    """Return a fresh recommend state with empty partitions."""
    return {
        "run": {
            "mode": "recommend",
            "user_id": user_id,
            "ingest_id": ingest_id,
            "indexing_ok": indexing_ok,
            "start_date": start_date,
            "end_date": end_date,
            "include_pricing": include_pricing,
        },
        "project": {
            "research_notes": "",
            "graph_notes": "",
            "needs": [],
        },
        "work_plan": [],
        "fleet_by_need": {},
        "prices_by_need": {},
        "recommendation": {
            "results_by_need": [],
            "warnings": [],
        },
        "tool_traces": [],
        "persistence": {
            "ai_recommendation_id": None,
            "recommendation_item_ids": [],
        },
    }


# ---------------------------------------------------------------------------
# Partition helpers
# ---------------------------------------------------------------------------


def _as_dict(state: RecommendAgentState | dict[str, Any]) -> dict[str, Any]:
    return dict(state)


def changed_top_level_keys(
    current: RecommendAgentState | dict[str, Any],
    proposed: RecommendAgentState | dict[str, Any],
) -> set[str]:
    """Return top-level keys whose values differ between current and proposed."""
    cur = _as_dict(current)
    prop = _as_dict(proposed)
    keys = set(cur) | set(prop)
    changed: set[str] = set()
    for key in keys:
        if cur.get(key) != prop.get(key):
            changed.add(key)
    return changed


def candidate_asset_ids(
    state: RecommendAgentState | dict[str, Any],
    need_id: str,
) -> set[str]:
    """Asset ids currently listed as candidates for ``need_id``."""
    fleet = _as_dict(state).get("fleet_by_need") or {}
    slice_ = fleet.get(need_id) or {}
    candidates = slice_.get("candidates") or []
    return {
        str(c.get("asset_id"))
        for c in candidates
        if isinstance(c, dict) and c.get("asset_id") is not None
    }


def indexing_ok(state: RecommendAgentState | dict[str, Any]) -> bool:
    run = _as_dict(state).get("run") or {}
    return bool(run.get("indexing_ok"))


# ---------------------------------------------------------------------------
# F-2 validation
# ---------------------------------------------------------------------------


def validate_state_transition(
    role: str,
    current: RecommendAgentState | dict[str, Any],
    proposed: RecommendAgentState | dict[str, Any],
    *,
    need_id: str | None = None,
) -> None:
    """Validate a proposed state write for ``role``.

    Checks (F-2):
    1. Partition ownership — role may only change its write partitions.
    2. Dependencies — pricing asset_ids must be in fleet candidates.
    3. Business rules — indexing_ok required before fleet writes; no silent-zero rates.

    Raises:
        StateTransitionError: on any illegal transition.
    """
    if role not in ALL_ROLES:
        raise StateTransitionError(f"unknown role: {role!r}")

    allowed = ROLE_WRITE_PARTITIONS[role]
    changed = changed_top_level_keys(current, proposed)

    # Unknown top-level keys are never allowed.
    unknown = changed - STATE_TOP_LEVEL_KEYS
    if unknown:
        raise StateTransitionError(
            f"role={role!r} proposed unknown state keys: {sorted(unknown)}"
        )

    illegal = changed - allowed
    if illegal:
        raise StateTransitionError(
            f"role={role!r} cannot write partitions {sorted(illegal)}; "
            f"allowed={sorted(allowed)}"
        )

    # --- Fleet Worker rules ---
    if role == ROLE_FLEET_WORKER and "fleet_by_need" in changed:
        if not indexing_ok(current):
            raise StateTransitionError(
                "fleet_worker cannot write fleet_by_need when run.indexing_ok is false"
            )
        if need_id is not None:
            prop_fleet = _as_dict(proposed).get("fleet_by_need") or {}
            cur_fleet = _as_dict(current).get("fleet_by_need") or {}
            # Only the assigned need_id slice may change.
            for other_id in set(prop_fleet) | set(cur_fleet):
                if other_id == need_id:
                    continue
                if prop_fleet.get(other_id) != cur_fleet.get(other_id):
                    raise StateTransitionError(
                        f"fleet_worker need_id={need_id!r} cannot write "
                        f"fleet_by_need[{other_id!r}]"
                    )

    # --- Pricing Worker rules ---
    if role == ROLE_PRICING_WORKER and "prices_by_need" in changed:
        if not indexing_ok(current):
            raise StateTransitionError(
                "pricing_worker cannot write prices_by_need when run.indexing_ok is false"
            )
        prop_prices = _as_dict(proposed).get("prices_by_need") or {}
        cur_prices = _as_dict(current).get("prices_by_need") or {}
        for nid, rows in prop_prices.items():
            if need_id is not None and nid != need_id:
                if rows != cur_prices.get(nid):
                    raise StateTransitionError(
                        f"pricing_worker need_id={need_id!r} cannot write "
                        f"prices_by_need[{nid!r}]"
                    )
                continue
            known = candidate_asset_ids(current, nid)
            # Prefer proposed fleet if present (same-run merge rare); source of
            # truth for candidates is current after fleet worker completed.
            if not known:
                known = candidate_asset_ids(proposed, nid)
            for row in rows or []:
                if not isinstance(row, dict):
                    raise StateTransitionError("price row must be a dict")
                asset_id = row.get("asset_id")
                if asset_id is None or str(asset_id) not in known:
                    raise StateTransitionError(
                        f"price for unknown asset_id={asset_id!r} "
                        f"(need_id={nid!r}; known={sorted(known)})"
                    )
                rate = row.get("daily_rate")
                if rate is not None and float(rate) <= 0:
                    raise StateTransitionError(
                        f"silent zero forbidden: daily_rate={rate!r} "
                        f"asset_id={asset_id!r}"
                    )

    # --- Coordinator: no invent asset_id outside fleet candidates ---
    if role == ROLE_COORDINATOR and "recommendation" in changed:
        prop_rec = _as_dict(proposed).get("recommendation") or {}
        results = prop_rec.get("results_by_need") or []
        fleet = _as_dict(proposed).get("fleet_by_need") or _as_dict(current).get(
            "fleet_by_need"
        ) or {}
        all_candidate_ids: set[str] = set()
        for slice_ in fleet.values():
            for c in (slice_ or {}).get("candidates") or []:
                if isinstance(c, dict) and c.get("asset_id") is not None:
                    all_candidate_ids.add(str(c["asset_id"]))
        for row in results:
            if not isinstance(row, dict):
                continue
            item = row.get("item")
            if not isinstance(item, dict):
                continue
            asset_id = item.get("asset_id")
            if asset_id is not None and str(asset_id) not in all_candidate_ids:
                raise StateTransitionError(
                    f"coordinator cannot invent asset_id={asset_id!r} "
                    f"not present in fleet_by_need candidates"
                )


def apply_partition_write(
    role: str,
    current: RecommendAgentState | dict[str, Any],
    proposed: RecommendAgentState | dict[str, Any],
    *,
    need_id: str | None = None,
) -> RecommendAgentState:
    """Validate then return a deep-copied merged state.

    Only partitions the role is allowed to write are taken from ``proposed``;
    all other keys remain from ``current``.
    """
    validate_state_transition(role, current, proposed, need_id=need_id)

    allowed = ROLE_WRITE_PARTITIONS[role]
    result: dict[str, Any] = deepcopy(_as_dict(current))
    prop = _as_dict(proposed)
    for key in allowed:
        if key in prop:
            result[key] = deepcopy(prop[key])
    return result  # type: ignore[return-value]


def write_fleet_slice(
    current: RecommendAgentState | dict[str, Any],
    need_id: str,
    *,
    candidates: list[dict[str, Any]] | None = None,
    unavailable: list[dict[str, Any]] | None = None,
    source_tables: list[str] | None = None,
) -> RecommendAgentState:
    """Convenience: legal Fleet Worker write for one need_id."""
    proposed = deepcopy(_as_dict(current))
    fleet = dict(proposed.get("fleet_by_need") or {})
    fleet[need_id] = {
        "candidates": list(candidates or []),
        "unavailable": list(unavailable or []),
        "source_tables": list(source_tables or ["assets", "bookings"]),
    }
    proposed["fleet_by_need"] = fleet
    return apply_partition_write(
        ROLE_FLEET_WORKER, current, proposed, need_id=need_id
    )


def write_price_rows(
    current: RecommendAgentState | dict[str, Any],
    need_id: str,
    rows: list[dict[str, Any]],
) -> RecommendAgentState:
    """Convenience: legal Pricing Worker write for one need_id."""
    proposed = deepcopy(_as_dict(current))
    prices = dict(proposed.get("prices_by_need") or {})
    prices[need_id] = list(rows)
    proposed["prices_by_need"] = prices
    return apply_partition_write(
        ROLE_PRICING_WORKER, current, proposed, need_id=need_id
    )
