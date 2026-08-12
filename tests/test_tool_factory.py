"""S7.1 — Recommend tool factory + allowlist (Phase 7).

BDD scenarios:

Feature: Tool factory injects fake vs SQL backends

  Scenario: Allowlist rejects unknown tool name
    Given a recommend tool catalog
    When  get is called with an unknown tool name
    Then  UnknownToolError is raised

  Scenario: Fake catalog exposes fleet tools
    Given backend=fake
    When  catalog is built
    Then  decompose / retrieve / filter / availability are registered

  Scenario: SQL backend uses injected DTOs only
    Given backend=sql with empty assets
    When  retrieve_fleet_assets runs via catalog
    Then  result is []
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.fleet_tools import (
    TOOL_CHECK_BOOKING_AVAILABILITY,
    TOOL_DECOMPOSE_PROJECT_NEEDS,
    TOOL_FILTER_FLEET_CANDIDATES,
    TOOL_RETRIEVE_FLEET_ASSETS,
    UnknownToolError,
)
from app.agents.tool_factory import (
    RECOMMEND_TOOL_ALLOWLIST,
    build_recommend_tool_catalog,
    get_recommend_tool,
)
from app.agents.tools import TOOL_PREDICT_ASSET_PRICE

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"


def _seed() -> tuple[list[dict], list[dict]]:
    data = json.loads((FIXTURES / "fleet_seed.json").read_text(encoding="utf-8"))
    return data["assets"], data["bookings"]


def test_allowlist_rejects_unknown_tool_name() -> None:
    """Scenario: allowlist rejects unknown tool name."""
    catalog = build_recommend_tool_catalog(backend="fake")
    with pytest.raises(UnknownToolError, match="not on the recommend allowlist"):
        catalog.get("recommend_everything")

    with pytest.raises(UnknownToolError):
        get_recommend_tool(catalog, "run_arbitrary_sql")

    assert "recommend_everything" not in RECOMMEND_TOOL_ALLOWLIST


def test_fake_catalog_exposes_fleet_tools() -> None:
    """Scenario: Fake catalog exposes fleet tools."""
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(
        backend="fake", assets=assets, bookings=bookings
    )

    for name in (
        TOOL_DECOMPOSE_PROJECT_NEEDS,
        TOOL_RETRIEVE_FLEET_ASSETS,
        TOOL_FILTER_FLEET_CANDIDATES,
        TOOL_CHECK_BOOKING_AVAILABILITY,
        TOOL_PREDICT_ASSET_PRICE,
    ):
        assert name in catalog
        tool = catalog.get(name)
        assert tool.name == name

    fleet = catalog.get(TOOL_RETRIEVE_FLEET_ASSETS)(category="scissor lift")
    assert {a["asset_id"] for a in fleet} == {"AST-SL-001", "AST-SL-002"}

    needs = catalog.get(TOOL_DECOMPOSE_PROJECT_NEEDS)("Need excavator for trench")
    assert len(needs) == 1
    assert needs[0]["need_id"] == "need_1"


def test_sql_backend_empty_dtos() -> None:
    """Scenario: SQL backend uses injected DTOs only (empty → [])."""
    catalog = build_recommend_tool_catalog(
        backend="sql", assets=[], bookings=[]
    )
    assert catalog.backend_kind == "sql"
    result = catalog.get(TOOL_RETRIEVE_FLEET_ASSETS)()
    assert result == []


def test_sql_backend_with_injected_rows() -> None:
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(
        backend="sql", assets=assets, bookings=bookings
    )
    result = catalog.get(TOOL_RETRIEVE_FLEET_ASSETS)(category="excavator")
    assert {a["asset_id"] for a in result} == {"AST-EX-001", "AST-EX-002"}

    avail = catalog.get(TOOL_CHECK_BOOKING_AVAILABILITY)(
        result,
        start_date="2026-09-01",
        end_date="2026-09-14",
    )
    unavailable_ids = {a["asset_id"] for a in avail["unavailable"]}
    assert "AST-EX-002" in unavailable_ids


def test_catalog_without_pricing_tool() -> None:
    catalog = build_recommend_tool_catalog(
        backend="fake", include_pricing_tool=False
    )
    assert TOOL_PREDICT_ASSET_PRICE not in catalog
    # Still allowlisted globally, but not registered → specific error
    with pytest.raises(UnknownToolError, match="not registered"):
        catalog.get(TOOL_PREDICT_ASSET_PRICE)
