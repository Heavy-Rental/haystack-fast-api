"""Factory for recommend-mode in-process tools (S7.1 / Phase 7).

Builds an allowlisted name → callable map. Fake backend is the default for CI;
SQL backend accepts pre-projected row DTOs only (no free-form SQL execution).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from app.agents.fleet_tools import (
    RECOMMEND_FLEET_TOOL_NAMES,
    TOOL_CHECK_BOOKING_AVAILABILITY,
    TOOL_DECOMPOSE_PROJECT_NEEDS,
    TOOL_DESCRIPTIONS,
    TOOL_FILTER_FLEET_CANDIDATES,
    TOOL_RETRIEVE_FLEET_ASSETS,
    FakeFleetBackend,
    FleetBackend,
    SqlFleetBackend,
    UnknownToolError,
    check_booking_availability,
    decompose_project_needs,
    filter_fleet_candidates,
    retrieve_fleet_assets,
)
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

# Full recommend-mode allowlist (fleet tools + already-shipped tools).
RECOMMEND_TOOL_ALLOWLIST: frozenset[str] = frozenset(
    RECOMMEND_FLEET_TOOL_NAMES
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
    desc = description or TOOL_DESCRIPTIONS.get(name, name)

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
) -> FleetBackend:
    """Construct a read-only fleet backend (fake seed or injected SQL DTOs)."""
    if kind == "fake":
        return FakeFleetBackend(assets=assets, bookings=bookings)
    if kind == "sql":
        return SqlFleetBackend(assets=assets, bookings=bookings)
    raise ValueError(f"unknown fleet backend kind: {kind!r}")


def build_recommend_tool_catalog(
    *,
    backend: BackendKind | FleetBackend = "fake",
    assets: list[dict[str, Any]] | None = None,
    bookings: list[dict[str, Any]] | None = None,
    decomposer: NeedDecomposer | None = None,
    include_pricing_tool: bool = True,
) -> RecommendToolCatalog:
    """Build the in-process recommend tool map (DI-friendly).

    Args:
        backend: ``"fake"`` (seed), ``"sql"`` (injected DTOs), or a custom
            ``FleetBackend`` instance.
        assets / bookings: optional row overrides for fake/sql backends.
        decomposer: optional NeedDecomposer (default stub).
        include_pricing_tool: register ``predict_asset_price`` (S6).
    """
    if isinstance(backend, str):
        kind: BackendKind = backend
        be = build_fleet_backend(kind, assets=assets, bookings=bookings)
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

    return RecommendToolCatalog(tools=tools, backend_kind=kind, backend=be)


def get_recommend_tool(
    catalog: RecommendToolCatalog,
    name: str,
) -> ProjectTool:
    """Lookup helper that enforces the allowlist (rejects unknown names)."""
    return catalog.get(name)
