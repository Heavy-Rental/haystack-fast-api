"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.api.internal_pricing import router as internal_pricing_router
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.middleware.correlation import CorrelationIdFilter, CorrelationIdMiddleware


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Ensure correlation_id is always present for the format string
    cid_filter = CorrelationIdFilter()
    if not any(isinstance(f, CorrelationIdFilter) for f in root.filters):
        root.addFilter(cid_filter)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] [cid=%(correlation_id)s] %(message)s"
            )
        )
        handler.addFilter(cid_filter)
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            if not any(isinstance(f, CorrelationIdFilter) for f in handler.filters):
                handler.addFilter(cid_filter)


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

    pricing_retrain_scheduler = None
    if settings.pricing_retrain_enabled:
        from app.services.pricing.scheduler import build_scheduler

        pricing_retrain_scheduler = build_scheduler(settings)
        pricing_retrain_scheduler.start()
        log.info(
            "Pricing retrain scheduler started (interval_days=%s)",
            settings.pricing_retrain_interval_days,
        )

    try:
        yield
    finally:
        if pricing_retrain_scheduler is not None:
            pricing_retrain_scheduler.shutdown(wait=False)
            log.info("Pricing retrain scheduler stopped")
        if decomposer is not None and hasattr(decomposer, "close"):
            decomposer.close()


def create_app() -> FastAPI:
    """Application factory used by Uvicorn and tests."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )
    # Correlation first so every request (incl. health / Q&A) is traceable.
    app.add_middleware(CorrelationIdMiddleware)
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
