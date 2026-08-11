"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.api.internal_pricing import router as internal_pricing_router
from app.config import get_settings
from app.core.errors import register_exception_handlers


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log = logging.getLogger(__name__)
    log.info("Starting %s (env=%s)", settings.app_name, settings.app_env)

    # Warm LLM decomposer client when enabled (DigitalOcean / OpenAI-compatible).
    decomposer = None
    if (settings.need_decomposer or "stub").strip().lower() == "llm":
        from app.services.llm_need_decomposer import LlmNeedDecomposer
        from app.services.need_decomposer_factory import create_need_decomposer

        decomposer = create_need_decomposer(settings)
        if isinstance(decomposer, LlmNeedDecomposer):
            decomposer.warm_up()
            log.info("LLM need decomposer warmed (model=%s)", settings.llm_model)

    yield

    if decomposer is not None and hasattr(decomposer, "close"):
        decomposer.close()


def create_app() -> FastAPI:
    """Application factory used by Uvicorn and tests."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    # Deliberately NOT part of api_router: internal, service-to-service only
    # (Spring Boot -> Haystack), never renter-facing -- see
    # app/api/internal_pricing.py's module docstring and
    # openspec/specs/dynamic-pricing/spec.md "Requirement: No renter-facing
    # predict route".
    app.include_router(internal_pricing_router)
    return app


app = create_app()
