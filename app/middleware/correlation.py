"""Request correlation for end-to-end log tracing (S2a / resilience C1).

Reads ``X-Correlation-Id`` when present; otherwise generates a UUID.
Also captures W3C ``traceparent`` when provided (logged; not required).

Correlation is **logging-only** in C1: the response echoes ``X-Correlation-Id``
so Spring/ops can join logs. Does not change business payloads.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar, Token

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

CORRELATION_HEADER = "X-Correlation-Id"
TRACEPARENT_HEADER = "traceparent"

correlation_id_ctx: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None
)
traceparent_ctx: ContextVar[str | None] = ContextVar("traceparent", default=None)

logger = logging.getLogger("app.request")


def get_correlation_id() -> str | None:
    """Return the correlation id bound to the current request context, if any."""
    return correlation_id_ctx.get()


def get_traceparent() -> str | None:
    """Return the W3C traceparent bound to the current request context, if any."""
    return traceparent_ctx.get()


class CorrelationIdFilter(logging.Filter):
    """Inject ``correlation_id`` onto every log record (for format strings)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get() or "-"  # type: ignore[attr-defined]
        return True


def bind_correlation_id(correlation_id: str) -> Token:
    """Bind correlation id into the current context (tests / nested work)."""
    return correlation_id_ctx.set(correlation_id)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or mint correlation id; echo on response; bind logging context."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = (request.headers.get(CORRELATION_HEADER) or "").strip()
        correlation_id = incoming or str(uuid.uuid4())
        traceparent = (request.headers.get(TRACEPARENT_HEADER) or "").strip() or None

        token_c = correlation_id_ctx.set(correlation_id)
        token_t = traceparent_ctx.set(traceparent)
        request.state.correlation_id = correlation_id
        request.state.traceparent = traceparent

        try:
            logger.info(
                "%s %s",
                request.method,
                request.url.path,
                extra={
                    "correlation_id": correlation_id,
                    "traceparent": traceparent or "",
                },
            )
            response = await call_next(request)
            response.headers[CORRELATION_HEADER] = correlation_id
            return response
        finally:
            correlation_id_ctx.reset(token_c)
            traceparent_ctx.reset(token_t)
