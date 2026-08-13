"""Factory for recommend-mode in-process tools (S7.1 + S7.2 + S7.7 / Phase 7).

Builds an allowlisted name → callable map. Fake backend is the default for CI;
SQL backend accepts pre-projected row DTOs only (no free-form SQL execution).
S7.2 adds fake Neo4j / KG-2 tools (templates only; no-op until S8).

S7.7 adds role-scoped DI: worker_kind allowlists, work_plan validation,
and ``build_recommend_runtime`` so tests inject fake tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from sqlalchemy.orm import Session

from app.agents.fleet_tools import (
    RECOMMEND_FLEET_TOOL_NAMES,
    TOOL_CHECK_BOOKING_AVAILABILITY,
    TOOL_DECOMPOSE_PROJECT_NEEDS,
    TOOL_DESCRIPTIONS,
    TOOL_FILTER_FLEET_CANDIDATES,
    TOOL_RETRIEVE_FLEET_ASSETS,
    FakeFleetBackend,
    FleetBackend,
    LiveSqlFleetBackend,
    SqlFleetBackend,
    UnknownToolError,
    check_booking_availability,
    decompose_project_needs,
    filter_fleet_candidates,
    retrieve_fleet_assets,
)
from app.agents.neo4j_tools import (
    RECOMMEND_NEO4J_TOOL_NAMES,
    TOOL_NEO4J_CYPHER_READ,
    TOOL_TRIGGER_NEO4J_POPULATE,
    FakeNeo4jBackend,
    Neo4jBackend,
    neo4j_cypher_read,
    trigger_neo4j_populate,
)
from app.agents.neo4j_tools import TOOL_DESCRIPTIONS as NEO4J_TOOL_DESCRIPTIONS
from app.agents.tools import (
    TOOL_PREDICT_ASSET_PRICE,
    TOOL_PROJECT_KG_QUERY,
    TOOL_PROJECT_VECTOR_SEARCH,
    TOOL_RUN_INDEXING,
    ProjectTool,
    predict_asset_price,
)
from app.services.need_decomposer import NeedDecomposer, StubNeedDecomposer

BackendKind = Literal["fake", "sql"]
AgentMode = Literal["stub", "llm"]

WORKER_KIND_FLEET = "fleet_worker"
WORKER_KIND_PRICING = "pricing_worker"

ALLOWED_WORKER_KINDS: frozenset[str] = frozenset(
    {WORKER_KIND_FLEET, WORKER_KIND_PRICING}
)

WORKER_TOOL_ALLOWLISTS: dict[str, tuple[str, ...]] = {
    WORKER_KIND_FLEET: (
        TOOL_RETRIEVE_FLEET_ASSETS,
        TOOL_FILTER_FLEET_CANDIDATES,
        TOOL_CHECK_BOOKING_AVAILABILITY,
    ),
    WORKER_KIND_PRICING: (TOOL_PREDICT_ASSET_PRICE,),
}


class UnknownWorkerKindError(ValueError):
    """Delegator / execute_needs rejected a worker_kind outside the allowlist."""

# Full recommend-mode allowlist (fleet tools + already-shipped tools).
RECOMMEND_TOOL_ALLOWLIST: frozenset[str] = frozenset(
    RECOMMEND_FLEET_TOOL_NAMES
    | RECOMMEND_NEO4J_TOOL_NAMES
    | {
        TOOL_PREDICT_ASSET_PRICE,
        TOOL_PROJECT_VECTOR_SEARCH,
        TOOL_PROJECT_KG_QUERY,
        TOOL_RUN_INDEXING,
    }
)


@dataclass(frozen=True)
class RecommendToolCatalog:
    """Allowlisted recommend tools + backend metadata."""

    tools: dict[str, ProjectTool]
    backend_kind: BackendKind
    backend: FleetBackend
    neo4j: Neo4jBackend = field(default_factory=FakeNeo4jBackend)

    def get(self, name: str) -> ProjectTool:
        """Return a tool by stable name; reject unknown names."""
        if name not in RECOMMEND_TOOL_ALLOWLIST:
            raise UnknownToolError(
                f"tool {name!r} is not on the recommend allowlist; "
                f"allowed={sorted(RECOMMEND_TOOL_ALLOWLIST)}"
            )
        if name not in self.tools:
            raise UnknownToolError(
                f"tool {name!r} is allowlisted but not registered in this catalog"
            )
        return self.tools[name]

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self.tools

    def names(self) -> frozenset[str]:
        return frozenset(self.tools)


def _wrap(
    name: str,
    func: Callable[..., Any],
    description: str | None = None,
) -> ProjectTool:
    desc = description or TOOL_DESCRIPTIONS.get(name) or NEO4J_TOOL_DESCRIPTIONS.get(
        name, name
    )

    def _run(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    # ProjectTool.func is typed as list[dict] for Stage-1 tools; recommend
    # tools return list or dict. Use a thin adapter and cast via ProjectTool.
    return ProjectTool(name=name, description=desc, func=_run)  # type: ignore[arg-type]


def build_fleet_backend(
    kind: BackendKind = "fake",
    *,
    assets: list[dict[str, Any]] | None = None,
    bookings: list[dict[str, Any]] | None = None,
    session: Session | None = None,
) -> FleetBackend:
    """Construct a read-only fleet backend (fake seed, DTO sql, or live ORM)."""
    if kind == "fake":
        return FakeFleetBackend(assets=assets, bookings=bookings)
    if kind == "sql":
        if session is not None:
            return LiveSqlFleetBackend(session)
        return SqlFleetBackend(assets=assets, bookings=bookings)
    raise ValueError(f"unknown fleet backend kind: {kind!r}")


def neo4j_available(catalog: RecommendToolCatalog | None) -> bool:
    """K-3: skip Neo4j tools when the backend is missing or empty."""
    if catalog is None:
        return False
    graph = catalog.neo4j
    return not graph.is_empty


def build_recommend_tool_catalog(
    *,
    backend: BackendKind | FleetBackend = "fake",
    assets: list[dict[str, Any]] | None = None,
    bookings: list[dict[str, Any]] | None = None,
    decomposer: NeedDecomposer | None = None,
    include_pricing_tool: bool = True,
    neo4j: Neo4jBackend | None = None,
    include_neo4j_tools: bool = True,
    session: Session | None = None,
) -> RecommendToolCatalog:
    """Build the in-process recommend tool map (DI-friendly).

    Args:
        backend: ``"fake"`` (seed), ``"sql"`` (injected DTOs or live ORM when
            ``session`` is passed), or a custom ``FleetBackend`` instance.
        assets / bookings: optional row overrides for fake/sql DTO backends.
        decomposer: optional NeedDecomposer (default stub).
        include_pricing_tool: register ``predict_asset_price`` (S6).
        neo4j: optional KG-2 backend (default empty fake).
        include_neo4j_tools: register ``neo4j_cypher_read`` / populate (S7.2).
        session: live SQLAlchemy session for ``backend="sql"`` (S4).
    """
    if isinstance(backend, str):
        kind: BackendKind = backend
        be = build_fleet_backend(
            kind, assets=assets, bookings=bookings, session=session
        )
    else:
        kind = "fake" if isinstance(backend, FakeFleetBackend) else "sql"
        be = backend

    dec = decomposer if decomposer is not None else StubNeedDecomposer()

    tools: dict[str, ProjectTool] = {
        TOOL_DECOMPOSE_PROJECT_NEEDS: _wrap(
            TOOL_DECOMPOSE_PROJECT_NEEDS,
            lambda source_text, **kw: decompose_project_needs(
                source_text, decomposer=dec, **kw
            ),
        ),
        TOOL_RETRIEVE_FLEET_ASSETS: _wrap(
            TOOL_RETRIEVE_FLEET_ASSETS,
            lambda **kw: retrieve_fleet_assets(backend=be, **kw),
        ),
        TOOL_FILTER_FLEET_CANDIDATES: _wrap(
            TOOL_FILTER_FLEET_CANDIDATES,
            lambda assets=None, **kw: filter_fleet_candidates(
                assets, backend=be, **kw
            ),
        ),
        TOOL_CHECK_BOOKING_AVAILABILITY: _wrap(
            TOOL_CHECK_BOOKING_AVAILABILITY,
            lambda candidates=None, **kw: check_booking_availability(
                candidates, backend=be, **kw
            ),
        ),
    }

    if include_pricing_tool:
        tools[TOOL_PREDICT_ASSET_PRICE] = ProjectTool(
            name=TOOL_PREDICT_ASSET_PRICE,
            description=(
                "Pricing Worker [7]: in-process ML daily rate via "
                "pricing_client (never invents rates; never silent zeros)."
            ),
            func=predict_asset_price,  # type: ignore[arg-type]
        )

    graph = neo4j if neo4j is not None else FakeNeo4jBackend()
    if include_neo4j_tools:
        tools[TOOL_NEO4J_CYPHER_READ] = _wrap(
            TOOL_NEO4J_CYPHER_READ,
            lambda **kw: neo4j_cypher_read(backend=graph, **kw),
        )
        tools[TOOL_TRIGGER_NEO4J_POPULATE] = _wrap(
            TOOL_TRIGGER_NEO4J_POPULATE,
            lambda **kw: trigger_neo4j_populate(backend=graph, **kw),
        )

    return RecommendToolCatalog(
        tools=tools, backend_kind=kind, backend=be, neo4j=graph
    )


def get_recommend_tool(
    catalog: RecommendToolCatalog,
    name: str,
) -> ProjectTool:
    """Lookup helper that enforces the allowlist (rejects unknown names)."""
    return catalog.get(name)


def tools_for_worker(kind: str) -> tuple[str, ...]:
    """Return the Delegator tool allowlist for an allowlisted worker_kind."""
    name = str(kind or "").strip()
    if name not in ALLOWED_WORKER_KINDS:
        raise UnknownWorkerKindError(
            f"unknown worker_kind={name!r}; "
            f"allowed={sorted(ALLOWED_WORKER_KINDS)}"
        )
    return WORKER_TOOL_ALLOWLISTS[name]


def validate_work_plan(plan: Any) -> None:
    """Fail closed if any work_plan item has an unknown worker_kind."""
    items = list(plan or [])
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise UnknownWorkerKindError(
                f"work_plan[{i}] must be a dict, got {type(item).__name__}"
            )
        kind = str(item.get("worker_kind") or "").strip()
        if kind not in ALLOWED_WORKER_KINDS:
            raise UnknownWorkerKindError(
                f"unknown worker_kind={kind!r}; "
                f"allowed={sorted(ALLOWED_WORKER_KINDS)}"
            )


@dataclass(frozen=True)
class RecommendRuntime:
    """Injected recommend-mode tools + stub/llm mode (S7.7)."""

    catalog: RecommendToolCatalog
    agent_mode: AgentMode
    worker_kinds: frozenset[str] = ALLOWED_WORKER_KINDS


def build_recommend_runtime(
    *,
    backend: BackendKind | FleetBackend = "fake",
    assets: list[dict[str, Any]] | None = None,
    bookings: list[dict[str, Any]] | None = None,
    decomposer: NeedDecomposer | None = None,
    include_pricing_tool: bool = True,
    neo4j: Neo4jBackend | None = None,
    include_neo4j_tools: bool = True,
    catalog: RecommendToolCatalog | None = None,
    agent_mode: AgentMode | str = "stub",
    session: Session | None = None,
) -> RecommendRuntime:
    """Build a DI-friendly recommend runtime (fake catalog by default)."""
    mode = str(agent_mode or "stub").strip().lower()
    if mode not in {"stub", "llm"}:
        mode = "stub"
    tools = catalog if catalog is not None else build_recommend_tool_catalog(
        backend=backend,
        assets=assets,
        bookings=bookings,
        decomposer=decomposer,
        include_pricing_tool=include_pricing_tool,
        neo4j=neo4j,
        include_neo4j_tools=include_neo4j_tools,
        session=session,
    )
    return RecommendRuntime(catalog=tools, agent_mode=mode)  # type: ignore[arg-type]
