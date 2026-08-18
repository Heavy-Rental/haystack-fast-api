"""app/api/internal_pricing.py -- POST /internal/v1/pricing/quote (US-4).

Mocks app.api.internal_pricing's three collaborators (resolve_pricing_schema,
get_asset_for_pricing, predict_price) at the API boundary -- an HTTP
shape/wiring test, not a re-test of predict_price's own guardrail-clamping
math (test_pricing_model.py) or compute_period_utilization's own SQL
(test_pricing_repository.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import internal_pricing
from app.core.db import get_db
from app.main import create_app
from app.services.pricing.model import PricePrediction
from app.services.pricing.repository import AssetPricingRow


def _prediction(**overrides) -> PricePrediction:
    defaults = {
        "raw_price": 150.0,
        "clamped_price": 150.0,
        "was_clamped": False,
        "min_daily_rate": 100.0,
        "max_daily_rate": 200.0,
        "duration_days": 7.0,
        "period_utilization": 0.5,
        "lead_time_days": 10.0,
        "degraded": False,
        "model_version": "prod-2026-08-11",
    }
    defaults.update(overrides)
    return PricePrediction(**defaults)


def _asset(**overrides) -> AssetPricingRow:
    defaults = {
        "id": 1,
        "category": "excavator",
        "condition": "GOOD",
        "capacity": 5000.0,
        "platform_height": None,
        "min_daily_rate": 100.0,
        "max_daily_rate": 200.0,
    }
    defaults.update(overrides)
    return AssetPricingRow(**defaults)


def _request_body(**overrides) -> dict:
    body = {
        "rental_plan_id": "plan_123",
        "start_date": "2026-09-01",
        "end_date": "2026-09-08",
        "distance_km": 18.4,
        "items": [
            {"item_id": "item_1", "asset_id": 1},
            {"item_id": "item_2", "asset_id": 2},
        ],
    }
    body.update(overrides)
    return body


@pytest.fixture
def api_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_multi_item_quote_shape(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        internal_pricing,
        "resolve_pricing_schema",
        lambda db: MagicMock(degraded=False, execution_options={}),
    )
    monkeypatch.setattr(
        internal_pricing,
        "get_asset_for_pricing",
        lambda db, resolution, asset_id: _asset(id=asset_id),
    )
    monkeypatch.setattr(internal_pricing, "predict_price", lambda **kwargs: _prediction())

    response = api_client.post("/internal/v1/pricing/quote", json=_request_body())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rental_plan_id"] == "plan_123"
    assert body["currency"] == "SGD"
    assert body["deposit_rate"] == 0.30
    assert body["degraded"] is False
    assert len(body["results"]) == 2
    for result, item in zip(body["results"], _request_body()["items"], strict=True):
        assert result["item_id"] == item["item_id"]
        assert result["asset_id"] == item["asset_id"]
        assert result["daily_rate"] == 150.0
        assert result["total_price"] == 1050.0  # 150.0 * duration_days(7.0)
        assert result["was_clamped"] is False
        assert result["min_daily_rate"] == 100.0
        assert result["max_daily_rate"] == 200.0
        assert result["model_version"] == "prod-2026-08-11"
        assert result["degraded"] is False
        assert result["error"] is None


def test_per_item_guardrail_bounds_from_real_asset_row(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        internal_pricing,
        "resolve_pricing_schema",
        lambda db: MagicMock(degraded=False, execution_options={}),
    )
    assets = {
        1: _asset(id=1, category="excavator", min_daily_rate=100.0, max_daily_rate=200.0),
        2: _asset(id=2, category="forklift", min_daily_rate=50.0, max_daily_rate=90.0),
    }
    monkeypatch.setattr(
        internal_pricing,
        "get_asset_for_pricing",
        lambda db, resolution, asset_id: assets[asset_id],
    )

    captured_kwargs: list[dict] = []

    def fake_predict_price(**kwargs):
        captured_kwargs.append(kwargs)
        return _prediction(
            min_daily_rate=kwargs["min_daily_rate"], max_daily_rate=kwargs["max_daily_rate"]
        )

    monkeypatch.setattr(internal_pricing, "predict_price", fake_predict_price)

    response = api_client.post("/internal/v1/pricing/quote", json=_request_body())

    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results[0]["min_daily_rate"] == 100.0
    assert results[0]["max_daily_rate"] == 200.0
    assert results[1]["min_daily_rate"] == 50.0
    assert results[1]["max_daily_rate"] == 90.0
    # category/condition/capacity/platform_height/guardrails are never in the
    # request -- confirm they were resolved server-side from the Asset row.
    assert "category" not in _request_body()["items"][0]
    assert captured_kwargs[0]["category"] == "excavator"
    assert captured_kwargs[1]["category"] == "forklift"


def test_per_item_degraded_independence(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolutions = [
        MagicMock(degraded=False, execution_options={}),
        MagicMock(degraded=True, execution_options={}),
    ]
    monkeypatch.setattr(internal_pricing, "resolve_pricing_schema", lambda db: resolutions.pop(0))
    monkeypatch.setattr(
        internal_pricing,
        "get_asset_for_pricing",
        lambda db, resolution, asset_id: _asset(id=asset_id),
    )
    monkeypatch.setattr(
        internal_pricing, "predict_price", lambda **kwargs: _prediction(degraded=False)
    )

    response = api_client.post("/internal/v1/pricing/quote", json=_request_body())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["results"][0]["degraded"] is False
    assert body["results"][1]["degraded"] is True
    # Top-level degraded is a convenience OR of all items, not a shared resolution.
    assert body["degraded"] is True


def test_unresolvable_asset_id_returns_per_item_error(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        internal_pricing,
        "resolve_pricing_schema",
        lambda db: MagicMock(degraded=False, execution_options={}),
    )

    def fake_get_asset(db, resolution, asset_id):
        return None if asset_id == 2 else _asset(id=asset_id)

    monkeypatch.setattr(internal_pricing, "get_asset_for_pricing", fake_get_asset)
    monkeypatch.setattr(internal_pricing, "predict_price", lambda **kwargs: _prediction())

    response = api_client.post("/internal/v1/pricing/quote", json=_request_body())

    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results[0]["error"] is None
    assert results[0]["daily_rate"] == 150.0
    assert results[1]["error"] == "asset_not_found"
    assert results[1]["daily_rate"] is None
    assert results[1]["min_daily_rate"] is None


def test_not_registered_under_public_api_v1_router() -> None:
    # OpenAPI schema paths, not app.routes -- FastAPI wraps app.include_router()
    # results in an internal _IncludedRouter with no stable public .path
    # attribute to introspect directly; the schema is the documented surface.
    app = create_app()
    paths = app.openapi()["paths"].keys()

    assert "/internal/v1/pricing/quote" in paths
    assert not any(p.startswith("/api/v1") and "pricing" in p for p in paths)
