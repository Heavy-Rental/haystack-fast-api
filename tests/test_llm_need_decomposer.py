"""Unit tests for LLM need decomposer (mocked HTTP; no live DigitalOcean)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.config import Settings
from app.services.llm_need_decomposer import LlmNeedDecomposer, parse_needs_json
from app.services.need_decomposer import StubNeedDecomposer
from app.services.need_decomposer_factory import create_need_decomposer
from app.services.recommendations import RecommendationService


def test_parse_needs_json_plain_array() -> None:
    raw = json.dumps(
        [
            {
                "need_id": "need_1",
                "description": "Scissors lift indoor",
                "equipment_hints": ["scissors lift"],
                "quantity": 2,
            }
        ]
    )
    needs = parse_needs_json(raw)
    assert len(needs) == 1
    assert needs[0].quantity == 2
    assert needs[0].need_id == "need_1"


def test_parse_needs_json_markdown_fence() -> None:
    raw = """```json
[{"need_id": "need_1", "description": "Fork lift", "quantity": 1}]
```"""
    needs = parse_needs_json(raw)
    assert len(needs) == 1
    assert needs[0].description == "Fork lift"


def test_parse_needs_json_invalid_returns_empty() -> None:
    assert parse_needs_json("not json") == []
    assert parse_needs_json("") == []


def test_llm_decomposer_uses_chat_completions() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        [
                            {
                                "need_id": "need_1",
                                "description": "Boom lift facade",
                                "equipment_hints": ["boom lift"],
                                "quantity": 1,
                            },
                            {
                                "need_id": "need_2",
                                "description": "Excavator trench",
                                "quantity": 1,
                            },
                        ]
                    )
                }
            }
        ]
    }
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.return_value = mock_response

    decomposer = LlmNeedDecomposer(
        base_url="https://inference.do-ai.run/v1",
        api_key="test-key",
        model="router:demo",
        client=mock_client,
    )
    needs = decomposer.decompose("Need boom lift and excavator")
    assert len(needs) == 2
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == "/chat/completions"
    assert kwargs["json"]["model"] == "router:demo"


def test_llm_decomposer_http_error_returns_empty() -> None:
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.side_effect = httpx.ConnectError("down")
    decomposer = LlmNeedDecomposer(
        base_url="https://inference.do-ai.run/v1",
        api_key="test-key",
        model="router:demo",
        client=mock_client,
    )
    assert decomposer.decompose("anything") == []
    mock_client.post.assert_called_once()


def test_llm_decomposer_retries_once_on_read_timeout() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        [
                            {
                                "need_id": "need_1",
                                "description": "Scissors lift indoor",
                                "equipment_hints": ["scissor lift"],
                                "quantity": 1,
                            }
                        ]
                    )
                }
            }
        ]
    }
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.side_effect = [
        httpx.ReadTimeout("timed out"),
        mock_response,
    ]
    decomposer = LlmNeedDecomposer(
        base_url="https://inference.do-ai.run/v1",
        api_key="test-key",
        model="router:demo",
        client=mock_client,
    )
    needs = decomposer.decompose("Need a scissors lift")
    assert len(needs) == 1
    assert needs[0].need_id == "need_1"
    assert mock_client.post.call_count == 2


def test_llm_decomposer_timeout_falls_back_to_keyword_split() -> None:
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.side_effect = httpx.ReadTimeout("timed out")
    decomposer = LlmNeedDecomposer(
        base_url="https://inference.do-ai.run/v1",
        api_key="test-key",
        model="router:demo",
        client=mock_client,
    )
    needs = decomposer.decompose("Need a scissors lift for indoor work")
    assert len(needs) == 1
    assert needs[0].need_id == "need_1"
    assert any("scissor" in hint.lower() for hint in needs[0].equipment_hints)
    assert mock_client.post.call_count == 2


def test_factory_default_stub() -> None:
    settings = Settings(NEED_DECOMPOSER="stub")
    assert isinstance(create_need_decomposer(settings), StubNeedDecomposer)


def test_factory_llm_requires_api_key() -> None:
    settings = Settings(NEED_DECOMPOSER="llm", LLM_API_KEY=None)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        create_need_decomposer(settings)


def test_factory_llm_builds_llm_decomposer() -> None:
    settings = Settings(
        NEED_DECOMPOSER="llm",
        LLM_API_KEY="secret",
        LLM_MODEL="router:my-router",
        LLM_BASE_URL="https://inference.do-ai.run/v1",
    )
    decomposer = create_need_decomposer(settings)
    assert isinstance(decomposer, LlmNeedDecomposer)


def test_service_with_llm_decomposer_expands_quantity() -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        [
                            {
                                "need_id": "need_1",
                                "description": "Scissors lift",
                                "quantity": 2,
                            }
                        ]
                    )
                }
            }
        ]
    }
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.return_value = mock_response
    decomposer = LlmNeedDecomposer(
        base_url="https://inference.do-ai.run/v1",
        api_key="k",
        model="router:x",
        client=mock_client,
    )
    result = RecommendationService(decomposer=decomposer).recommend_from_project_spec(
        project_text="two scissors lifts for indoor work"
    )
    assert len(result.results_by_need) == 2
    assert result.results_by_need[0].need_id == "need_1__u1"
    assert result.results_by_need[1].need_id == "need_1__u2"
