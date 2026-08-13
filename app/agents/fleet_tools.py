"""In-process recommend tool catalog for fleet / needs (S7.1 / Phase 7).

Allowlisted tools only — no free-form SQL/Cypher, no MCP server.
Fake backend uses seed fleet; ``sql`` is either injected DTOs or
``LiveSqlFleetBackend`` (S4 allowlisted ORM reads).

Tool names are stable contracts for LangGraph traces and Delegator allowlists.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.pipelines.catalog import infer_model_categories, is_approved_display_type
from app.pipelines.seed_fleet import get_seed_assets, get_seed_bookings
from app.repositories.fleet_repository import FleetRepository
from app.services.need_decomposer import NeedDecomposer, StubNeedDecomposer
from app.services.pricing.read_resilience import PricingSchemaResolution

# ---------------------------------------------------------------------------
# Stable tool names (Delegator allowlist / traces)
# ---------------------------------------------------------------------------

TOOL_DECOMPOSE_PROJECT_NEEDS = "decompose_project_needs"
TOOL_RETRIEVE_FLEET_ASSETS = "retrieve_fleet_assets"
TOOL_FILTER_FLEET_CANDIDATES = "filter_fleet_candidates"
TOOL_CHECK_BOOKING_AVAILABILITY = "check_booking_availability"

RECOMMEND_FLEET_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_DECOMPOSE_PROJECT_NEEDS,
        TOOL_RETRIEVE_FLEET_ASSETS,
        TOOL_FILTER_FLEET_CANDIDATES,
        TOOL_CHECK_BOOKING_AVAILABILITY,
    }
)

TOOL_DESCRIPTIONS: dict[str, str] = {
    TOOL_DECOMPOSE_PROJECT_NEEDS: (
        "Project Worker [5]: decompose unstructured project text into "
        "internal equipment needs (need_id, description, hints, quantity)."
    ),
    TOOL_RETRIEVE_FLEET_ASSETS: (
        "Fleet Worker [6]: read-only list of fleet assets from the "
        "Postgres-Haystack mirror (or fake seed). Optional category filter."
    ),
    TOOL_FILTER_FLEET_CANDIDATES: (
        "Fleet Worker [6]: filter assets by unit-need category/size/height "
        "constraints. Never invents asset_id."
    ),
    TOOL_CHECK_BOOKING_AVAILABILITY: (
        "Fleet Worker [6]: drop candidates with overlapping bookings for the "
        "rental window. Returns available + unavailable lists."
    ),
}


class UnknownToolError(ValueError):
    """Tool name is not on the recommend allowlist."""


class FreeFormSqlRejected(ValueError):
    """Agents must not pass free-form SQL to fleet tools."""


# ---------------------------------------------------------------------------
# Fleet data backends
# ---------------------------------------------------------------------------


@runtime_checkable
class FleetBackend(Protocol):
    """Read-only fleet data source (fake seed or SQL mirror DTOs)."""

    def list_assets(self) -> list[dict[str, Any]]:
        ...

    def list_bookings(self) -> list[dict[str, Any]]:
        ...


class FakeFleetBackend:
    """In-memory seed fleet (default CI / local)."""

    def __init__(
        self,
        assets: list[dict[str, Any]] | None = None,
        bookings: list[dict[str, Any]] | None = None,
    ) -> None:
        self._assets = (
            deepcopy(assets) if assets is not None else get_seed_assets()
        )
        self._bookings = (
            deepcopy(bookings) if bookings is not None else get_seed_bookings()
        )

    def list_assets(self) -> list[dict[str, Any]]:
        return deepcopy(self._assets)

    def list_bookings(self) -> list[dict[str, Any]]:
        return deepcopy(self._bookings)


class LiveSqlFleetBackend:
    """Read-only fleet from Postgres-Haystack via allowlisted ORM selects."""

    def __init__(
        self,
        session: Session,
        *,
        repository: FleetRepository | None = None,
        resolution: PricingSchemaResolution | None = None,
    ) -> None:
        self._session = session
        self._repo = repository if repository is not None else FleetRepository()
        self._resolution = resolution

    def list_assets(self) -> list[dict[str, Any]]:
        return self._repo.list_assets(self._session, resolution=self._resolution)

    def list_bookings(self) -> list[dict[str, Any]]:
        return self._repo.list_bookings(self._session, resolution=self._resolution)


class SqlFleetBackend:
    """SQL-mirror backend using pre-loaded row DTOs (no free-form SQL).

    Callers inject rows already projected from allowlisted repository queries.
    This class never executes SQL strings.
    """

    def __init__(
        self,
        assets: list[dict[str, Any]] | None = None,
        bookings: list[dict[str, Any]] | None = None,
    ) -> None:
        self._assets = list(assets or [])
        self._bookings = list(bookings or [])

    def list_assets(self) -> list[dict[str, Any]]:
        return deepcopy(self._assets)

    def list_bookings(self) -> list[dict[str, Any]]:
        return deepcopy(self._bookings)


def _reject_freeform_sql(**kwargs: Any) -> None:
    """Hard reject free-form SQL/Cypher kwargs on tool entrypoints."""
    for key in ("sql", "query_sql", "cypher", "raw_sql", "statement"):
        if key in kwargs and kwargs[key] is not None:
            raise FreeFormSqlRejected(
                f"free-form SQL/Cypher rejected (got {key!r}); "
                "use allowlisted fleet tools only"
            )


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _ranges_overlap(
    a_start: date, a_end: date, b_start: date, b_end: date
) -> bool:
    return a_start <= b_end and b_start <= a_end


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def decompose_project_needs(
    source_text: str,
    *,
    decomposer: NeedDecomposer | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Decompose project text → list of need DTOs.

    Stub decomposer returns a single fixed need for CI.
    """
    _reject_freeform_sql(**kwargs)
    text = (source_text or "").strip()
    if not text:
        return []
    dec = decomposer if decomposer is not None else StubNeedDecomposer()
    needs = dec.decompose(text)
    return [
        {
            "need_id": n.need_id,
            "description": n.description,
            "equipment_hints": list(n.equipment_hints or []),
            "quantity": int(n.quantity),
        }
        for n in needs
    ]


def retrieve_fleet_assets(
    *,
    backend: FleetBackend | None = None,
    category: str | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Return fleet assets (optionally filtered by model category).

    Empty fleet → []. Never invents assets.
    """
    _reject_freeform_sql(**kwargs)
    be = backend if backend is not None else FakeFleetBackend()
    assets = be.list_assets()
    if not assets:
        return []
    if category is None or not str(category).strip():
        return assets
    cat = str(category).strip().lower()
    return [
        a
        for a in assets
        if str(a.get("category") or "").strip().lower() == cat
    ]


def filter_fleet_candidates(
    assets: list[dict[str, Any]] | None = None,
    *,
    unit_need: dict[str, Any] | None = None,
    category: str | None = None,
    min_platform_height: float | None = None,
    backend: FleetBackend | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Filter assets by unit-need category / height constraints.

    If ``assets`` is None, loads from ``backend`` (default fake seed).
    Unrecognized equipment signal → [].
    """
    _reject_freeform_sql(**kwargs)
    pool = list(assets) if assets is not None else retrieve_fleet_assets(
        backend=backend
    )
    if not pool:
        return []

    need = dict(unit_need or {})
    if category is not None and str(category).strip():
        need.setdefault("equipment_hints", [])
        # Prefer explicit category over infer when provided.
        cat = str(category).strip().lower()
        categories = [cat]
    else:
        hints = [
            str(h).strip()
            for h in (need.get("equipment_hints") or [])
            if str(h).strip()
        ]
        if hints:
            # Hints win: do not let a shared description pull extra types.
            categories = infer_model_categories(
                {"equipment_hints": hints, "description": ""}
            ) or [h.lower() for h in hints]
        else:
            categories = infer_model_categories(need)

    if not categories:
        return []

    out: list[dict[str, Any]] = []
    for asset in pool:
        equipment_type = str(asset.get("equipment_type") or "")
        if equipment_type and not is_approved_display_type(equipment_type):
            continue
        asset_cat = str(asset.get("category") or "").strip().lower()
        if asset_cat not in categories:
            continue
        if min_platform_height is not None:
            height = asset.get("platform_height")
            if height is None or float(height) < float(min_platform_height):
                continue
        # Also honour constraints on unit_need.
        constraints = need.get("constraints") or {}
        min_h = constraints.get("platform_height_m") or constraints.get(
            "min_platform_height"
        )
        if min_h is not None:
            height = asset.get("platform_height")
            if height is None or float(height) < float(min_h):
                continue
        out.append(dict(asset))
    return out


def check_booking_availability(
    candidates: list[dict[str, Any]] | None = None,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    backend: FleetBackend | None = None,
    bookings: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Split candidates into available / unavailable by booking overlap.

    If start or end is missing, all candidates are available (same as FR-013
    pipeline behaviour). Empty candidates → empty lists.
    """
    _reject_freeform_sql(**kwargs)
    pool = [dict(c) for c in (candidates or [])]
    if not pool:
        return {"available": [], "unavailable": []}

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is None or end is None:
        for c in pool:
            c["availability"] = "available"
        return {"available": pool, "unavailable": []}

    if bookings is not None:
        booking_rows = list(bookings)
    else:
        be = backend if backend is not None else FakeFleetBackend()
        booking_rows = be.list_bookings()

    busy: set[str] = set()
    for booking in booking_rows:
        b_start = _parse_date(booking.get("start_date"))
        b_end = _parse_date(booking.get("end_date"))
        asset_id = str(booking.get("asset_id") or "")
        if not asset_id or b_start is None or b_end is None:
            continue
        if _ranges_overlap(start, end, b_start, b_end):
            busy.add(asset_id)

    available: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for c in pool:
        aid = str(c.get("asset_id") or "")
        row = dict(c)
        if aid and aid in busy:
            row["availability"] = "unavailable"
            unavailable.append(row)
        else:
            row["availability"] = "available"
            available.append(row)
    return {"available": available, "unavailable": unavailable}
