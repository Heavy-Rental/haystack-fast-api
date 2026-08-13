"""S7.5 — HTTP Call 2 multi-agent enrich (same quote DTO).

BDD scenarios (implementation-plan Stage S7.5):

Feature: Call 2 getassetrecommendations can run the C/W/D graph

  Scenario: Flag on happy path
    Given a Call 1 session and RECOMMEND_VIA_AGENT_GRAPH=true
    When  POST .../getassetrecommendations
    Then  200 quote envelope (quoteRef, items[], no answer)
    And   equipment.id is a catalog asset_id only

  Scenario: Flag off uses MVP service
    Given a session and via_agent_graph false
    When  recommend runs
    Then  run_recommend_graph is not invoked

  Scenario: Gate fail
    Given a session with meta.indexing_ok=false and flag on
    When  POST getassetrecommendations
    Then  400 shared error JSON
    And   no invented items

  Scenario: Multi-need golden
    Given injected two-need decomposer + fleet/price fixtures
    When  SessionRecommendService runs the graph path
    Then  items match fixture asset_id and daily_rate

  Scenario: Missing session
    Given no registry entry and flag on
    When  POST getassetrecommendations
    Then  404 not_found
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.config import get_settings
from app.main import create_app
from app.schemas.recommendations import DecomposedNeed
from app.services.project_knowledge_session import (
    ProjectKnowledgeSession,
    get_project_knowledge_registry,
)
from app.services.session_recommend import SessionRecommendService

FIXTURES = Path(__file__).parent / "fixtures" / "recommend"

CALL2 = "/internal/v1/recommendations/project-knowledge/getassetrecommendations"


class FixtureTwoNeedDecomposer:
    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        del source_text
        return [
            DecomposedNeed(
                need_id="need_access",
                description="Need scissors lift for indoor elevated work ~8m",
                equipment_hints=["scissor lift"],
                quantity=1,
            ),
            DecomposedNeed(
                need_id="need_earthwork",
                description="Need excavator for site prep",
                equipment_hints=["excavator"],
                quantity=1,
            ),
        ]


def _seed() -> tuple[list[dict], list[dict]]:
    data = json.loads((FIXTURES / "fleet_seed.json").read_text(encoding="utf-8"))
    return data["assets"], data["bookings"]


def _price_fn(**kwargs):
    return {
        "asset_id": kwargs.get("asset_id"),
        "daily_rate": 185.0,
        "total_price": 2590.0,
        "currency": "SGD",
        "model_version": "test-fixture",
        "was_clamped": False,
        "explanation": "fixture",
    }


def _put_session(
    *,
    user_id: str = "u-s75",
    ingest_id: str = "ing_s75",
    meta: dict | None = None,
) -> None:
    get_project_knowledge_registry().put(
        ProjectKnowledgeSession(
            user_id=user_id,
            ingest_id=ingest_id,
            document_store=InMemoryDocumentStore(),
            meta=meta
            or {
                "user_requirement_summary": "Need scissors lift and excavator",
                "tentative_start_date": "2026-09-01",
                "tentative_end_date": "2026-09-14",
            },
        )
    )


def _graph_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    get_settings.cache_clear()
    monkeypatch.setenv("RECOMMEND_VIA_AGENT_GRAPH", "true")
    get_settings.cache_clear()
    app = create_app()
    return TestClient(app)


def test_flag_on_http_quote_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Flag on happy path returns the same quote DTO."""
    _put_session()
    with _graph_client(monkeypatch) as client:
        resp = client.post(
            CALL2,
            json={
                "user_id": "u-s75",
                "ingest_id": "ing_s75",
                "query": "Need excavator for site prep",
            },
        )
    assert resp.status_code == 200, resp.text
    quote = resp.json()
    assert quote["user_id"] == "u-s75"
    assert quote["ingest_id"] == "ing_s75"
    assert quote["quoteRef"].startswith("QUO-")
    assert "items" in quote
    assert "answer" not in quote
    assert "tool_traces" not in quote
    assert quote["items"], "graph path should return at least one catalog item"
    assert quote.get("rationale") and "Stub merge:" in quote["rationale"]
    for item in quote["items"]:
        asset_id = item["equipment"]["id"]
        assert asset_id
        assert str(asset_id).startswith("AST-")
        predicted = item.get("mlPredictedPrice")
        assert predicted is not None and float(predicted) > 0
        assert item["equipment"]["baseDailyRate"] == predicted
        assert str(item["equipment"].get("extra", {}).get("model_version") or "").startswith(
            "prod-"
        )


def test_flag_off_does_not_invoke_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Flag off uses MVP service."""
    _put_session()
    boom = MagicMock(side_effect=AssertionError("graph should not run"))
    monkeypatch.setattr(
        "app.services.session_recommend.run_recommend_graph", boom
    )
    quote = SessionRecommendService(via_agent_graph=False).recommend(
        user_id="u-s75",
        ingest_id="ing_s75",
        query="Need excavator",
    )
    boom.assert_not_called()
    assert quote.quoteRef.startswith("QUO-")
    assert "answer" not in quote.model_dump()


def test_gate_fail_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Gate fail → 400 shared error JSON."""
    _put_session(meta={"indexing_ok": False, "user_requirement_summary": "x"})
    with _graph_client(monkeypatch) as client:
        resp = client.post(
            CALL2,
            json={"user_id": "u-s75", "ingest_id": "ing_s75"},
        )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"] == "bad_request"
    assert "index" in body["message"].lower() or "gate" in body["message"].lower()
    assert "items" not in body


def test_multi_need_golden_asset_ids_and_rates() -> None:
    """Scenario: Multi-need body matches golden asset_id / rates."""
    from app.agents.tool_factory import build_recommend_tool_catalog

    _put_session()
    assets, bookings = _seed()
    catalog = build_recommend_tool_catalog(
        backend="fake", assets=assets, bookings=bookings
    )
    quote = SessionRecommendService(
        via_agent_graph=True,
        catalog=catalog,
        decomposer=FixtureTwoNeedDecomposer(),
        price_fn=_price_fn,
        fanout_cap=2,
    ).recommend(user_id="u-s75", ingest_id="ing_s75")

    golden = json.loads(
        (FIXTURES / "golden_call2_quote.json").read_text(encoding="utf-8")
    )["items"]
    by_need = {item.needId: item for item in quote.items}
    assert set(by_need) == {row["needId"] for row in golden}
    for row in golden:
        item = by_need[row["needId"]]
        assert item.equipment.id == row["equipment"]["id"]
        assert item.equipment.name == row["equipment"]["name"]
        assert item.equipment.baseDailyRate == row["equipment"]["baseDailyRate"]
        assert item.mlPredictedPrice == row["equipment"]["baseDailyRate"]
        assert item.mlPredictedPrice is not None and item.mlPredictedPrice > 0


def test_missing_session_404_with_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Missing session → 404 with flag on."""
    with _graph_client(monkeypatch) as client:
        resp = client.post(
            CALL2,
            json={"user_id": "nobody", "ingest_id": "ing_missing"},
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"
