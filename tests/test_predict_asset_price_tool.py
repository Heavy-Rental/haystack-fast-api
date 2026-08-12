"""S6 — In-process agent tool predict_asset_price (Phase 6).

BDD scenarios (implementation-plan Phase 6 / stage S6):

Feature: Pricing Worker tool shares production pricing entrypoint

  Scenario: Golden shape from real production model
    Given valid asset features and per-asset guardrail bounds
    When  predict_asset_price is invoked
    Then  result has daily_rate, total_price, currency, was_clamped,
          model_version, explanation
    And   daily_rate is strictly positive

  Scenario: Single source of truth with pricing_client
    Given the same asset features and bounds
    When  predict_asset_price and predict_price_for_asset both run
    Then  daily_rate, total_price, and model_version match

  Scenario: Clamp metadata pass-through
    Given the underlying pricing path returns was_clamped=True
    When  predict_asset_price runs
    Then  was_clamped is True on the tool result

  Scenario: Silent zero forbidden
    Given the underlying path returns daily_rate=0
    When  predict_asset_price runs
    Then  it fails loud (ValueError), not a zero-priced dict

  Scenario: Tool name is the stable contract
    Then  TOOL_PREDICT_ASSET_PRICE == "predict_asset_price"

  Scenario: Optional asset_id echo
    Given asset_id is provided
    When  predict_asset_price runs
    Then  the result echoes asset_id
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.agents.tools import TOOL_PREDICT_ASSET_PRICE, predict_asset_price
from app.services.pricing_client import predict_price_for_asset


_BASE_KWARGS = {
    "category": "excavator",
    "condition": "GOOD",
    "duration_days": 7.0,
    "capacity": 5000.0,
    "distance_km": 15.0,
    "platform_height": None,
    "min_daily_rate": 250.0,
    "max_daily_rate": 600.0,
}


def test_tool_name_stable_contract() -> None:
    assert TOOL_PREDICT_ASSET_PRICE == "predict_asset_price"


def test_predict_asset_price_golden_shape_real_model() -> None:
    """Given valid features, When tool runs, Then golden keys + daily_rate > 0."""
    result = predict_asset_price(**_BASE_KWARGS)

    assert isinstance(result, dict)
    for key in (
        "daily_rate",
        "total_price",
        "currency",
        "deposit_rate",
        "was_clamped",
        "model_version",
        "explanation",
    ):
        assert key in result, f"missing key: {key}"

    assert result["daily_rate"] > 0
    assert result["total_price"] == round(result["daily_rate"] * 7.0, 2)
    assert result["currency"] == "SGD"
    assert result["deposit_rate"] == 0.30
    assert isinstance(result["was_clamped"], bool)
    assert isinstance(result["model_version"], str)
    assert result["model_version"]  # non-empty
    assert isinstance(result["explanation"], str)
    assert "asset_id" not in result


def test_single_source_of_truth_matches_pricing_client() -> None:
    """Service path and agent tool share pricing_client entrypoint."""
    tool_result = predict_asset_price(**_BASE_KWARGS)
    client_result = predict_price_for_asset(**_BASE_KWARGS)

    assert tool_result["daily_rate"] == client_result.daily_rate
    assert tool_result["total_price"] == client_result.total_price
    assert tool_result["model_version"] == client_result.model_version
    assert tool_result["was_clamped"] == client_result.was_clamped
    assert tool_result["currency"] == client_result.currency
    assert tool_result["deposit_rate"] == client_result.deposit_rate


@dataclass(frozen=True)
class _FakePriceResult:
    daily_rate: float
    total_price: float
    currency: str = "SGD"
    deposit_rate: float = 0.30
    model_version: str = "prod-test"
    explanation: str = "fake"
    was_clamped: bool = False


def test_was_clamped_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agents.tools.predict_price_for_asset",
        lambda **_kwargs: _FakePriceResult(
            daily_rate=200.0,
            total_price=200.0,
            was_clamped=True,
        ),
    )

    result = predict_asset_price(**_BASE_KWARGS)
    assert result["was_clamped"] is True
    assert result["daily_rate"] == 200.0


def test_silent_zero_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given daily_rate=0, When tool runs, Then ValueError (no silent zero)."""
    monkeypatch.setattr(
        "app.agents.tools.predict_price_for_asset",
        lambda **_kwargs: _FakePriceResult(
            daily_rate=0.0,
            total_price=0.0,
        ),
    )

    with pytest.raises(ValueError, match="silent zero|daily_rate"):
        predict_asset_price(**_BASE_KWARGS)


def test_negative_daily_rate_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agents.tools.predict_price_for_asset",
        lambda **_kwargs: _FakePriceResult(
            daily_rate=-10.0,
            total_price=-70.0,
        ),
    )

    with pytest.raises(ValueError, match="silent zero|daily_rate"):
        predict_asset_price(**_BASE_KWARGS)


def test_asset_id_echoed_when_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agents.tools.predict_price_for_asset",
        lambda **_kwargs: _FakePriceResult(
            daily_rate=150.0,
            total_price=1050.0,
        ),
    )

    result = predict_asset_price(**_BASE_KWARGS, asset_id=42)
    assert result["asset_id"] == 42


def test_threads_db_and_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return _FakePriceResult(daily_rate=99.0, total_price=693.0)

    monkeypatch.setattr("app.agents.tools.predict_price_for_asset", _fake)
    fake_db = MagicMock()

    predict_asset_price(
        **_BASE_KWARGS,
        db=fake_db,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert captured["db"] is fake_db
    assert captured["start_date"] == date(2026, 9, 1)
    assert captured["end_date"] == date(2026, 9, 7)
    assert "asset_id" not in captured
