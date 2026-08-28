"""LLM-backed need decomposer (OpenAI-compatible APIs, e.g. DigitalOcean Inference).

Implements ``NeedDecomposer`` for FR-010.2. Default CI path remains
``StubNeedDecomposer``; enable with ``NEED_DECOMPOSER=llm``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.schemas.recommendations import DecomposedNeed
from app.services.need_decomposer import split_needs_from_text

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SECONDS = 10.0
_TIMEOUT_ATTEMPTS = 2  # initial POST + one retry on read/connect timeout

_SYSTEM_PROMPT = """You extract equipment rental needs from unstructured project text.

Return ONLY a JSON array (no markdown fences, no commentary). Each element:
{
  "need_id": "need_1",
  "description": "clear equipment need description",
  "equipment_hints": ["scissor lift"],
  "quantity": 1
}

Rules:
- Emit ONE array element per distinct equipment type. Do not collapse a forklift
  and a scissors lift into a single need.
- equipment_hints must use these slugs only: "forklift", "scissor lift",
  "boom lift", "excavator".
- quantity is the number of units requested for that type (integer >= 1).
- Use distinct need_id values: need_1, need_2, ...
- Ignore placeholder captions such as "Optional caption alongside file".
- If the text is not about equipment rental, return [].
- Do not invent needs that are not implied by the text.
"""


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def parse_needs_json(raw: str) -> list[DecomposedNeed]:
    """Parse model output into DecomposedNeed list; invalid/empty → []."""
    if not raw or not raw.strip():
        return []
    text = _strip_code_fences(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            logger.warning("LLM need decompose: no JSON array in model output")
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("LLM need decompose: failed to parse JSON array")
            return []

    if not isinstance(data, list):
        logger.warning("LLM need decompose: expected JSON array, got %s", type(data))
        return []

    needs: list[DecomposedNeed] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        payload = {
            "need_id": str(item.get("need_id") or f"need_{index}").strip() or f"need_{index}",
            "description": str(item.get("description") or "").strip(),
            "equipment_hints": item.get("equipment_hints") or [],
            "quantity": item.get("quantity", 1),
        }
        if not payload["description"]:
            continue
        try:
            needs.append(DecomposedNeed.model_validate(payload))
        except ValidationError as exc:
            logger.warning("LLM need decompose: skip invalid item %s: %s", index, exc)
            continue
    return needs


class LlmNeedDecomposer:
    """Call an OpenAI-compatible chat completions API to extract needs.

    DigitalOcean Inference / Inference Router::

        LLM_BASE_URL=https://inference.do-ai.run/v1
        LLM_API_KEY=<token>
        LLM_MODEL=router:<your-router-name>
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
        temperature: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._temperature = temperature
        self._client = client
        self._owns_client = client is None

    def _http_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=_CONNECT_TIMEOUT_SECONDS,
            read=self._timeout,
            write=_CONNECT_TIMEOUT_SECONDS,
            pool=_CONNECT_TIMEOUT_SECONDS,
        )

    def warm_up(self) -> None:
        """Create HTTP client once (call from app lifespan when mode=llm)."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self._http_timeout(),
            )
            logger.info(
                "LlmNeedDecomposer warmed up base_url=%s model=%s",
                self._base_url,
                self._model,
            )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        text = (source_text or "").strip()
        if not text:
            return []

        if self._client is None:
            self.warm_up()
        assert self._client is not None

        body: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Project text:\n\n{text}\n\nReturn the JSON array only.",
                },
            ],
        }

        payload: dict[str, Any] | None = None
        for attempt in range(1, _TIMEOUT_ATTEMPTS + 1):
            try:
                response = self._client.post("/chat/completions", json=body)
                response.raise_for_status()
                payload = response.json()
                break
            except httpx.TimeoutException as exc:
                logger.warning(
                    "LLM need decompose timeout attempt=%s/%s "
                    "read_timeout_s=%s: %s",
                    attempt,
                    _TIMEOUT_ATTEMPTS,
                    self._timeout,
                    exc,
                )
                if attempt >= _TIMEOUT_ATTEMPTS:
                    return split_needs_from_text(text)
            except httpx.HTTPError:
                logger.exception("LLM need decompose HTTP error")
                return split_needs_from_text(text)

        if payload is None:
            return split_needs_from_text(text)

        content = _extract_message_content(payload)
        needs = parse_needs_json(content)
        if needs:
            return needs
        return split_needs_from_text(text)


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [str(part.get("text", "")) for part in content if isinstance(part, dict)]
        return "".join(parts)
    return ""
