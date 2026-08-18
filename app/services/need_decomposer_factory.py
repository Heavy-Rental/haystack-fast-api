"""Build the configured NeedDecomposer (stub or LLM)."""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.services.llm_need_decomposer import LlmNeedDecomposer
from app.services.need_decomposer import NeedDecomposer, StubNeedDecomposer

logger = logging.getLogger(__name__)


def create_need_decomposer(settings: Settings | None = None) -> NeedDecomposer:
    """Return stub (default) or LLM decomposer from settings.

    LLM mode uses an OpenAI-compatible endpoint (DigitalOcean Inference Router
    supported via base URL + ``router:<name>`` model id).
    """
    cfg = settings or get_settings()
    mode = (cfg.need_decomposer or "stub").strip().lower()

    if mode in {"", "stub"}:
        logger.debug("Need decomposer mode=stub")
        return StubNeedDecomposer()

    if mode != "llm":
        logger.warning("Unknown NEED_DECOMPOSER=%r; falling back to stub", mode)
        return StubNeedDecomposer()

    api_key = (cfg.llm_api_key or "").strip()
    if not api_key:
        raise RuntimeError(
            "NEED_DECOMPOSER=llm requires LLM_API_KEY "
            "(e.g. DigitalOcean API token for inference.do-ai.run)"
        )

    model = (cfg.llm_model or "").strip()
    if not model:
        raise RuntimeError("NEED_DECOMPOSER=llm requires LLM_MODEL")

    base_url = (cfg.llm_base_url or "https://inference.do-ai.run/v1").strip()
    logger.info(
        "Need decomposer mode=llm base_url=%s model=%s",
        base_url,
        model,
    )
    return LlmNeedDecomposer(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=cfg.llm_timeout_seconds,
        temperature=cfg.llm_temperature,
    )
