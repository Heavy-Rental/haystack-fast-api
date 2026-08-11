"""Shared 3-tier read-resilience resolver for pricing DB reads.

Relocated from ``app/repositories/pricing_read_resilience.py`` (Phase 1e) into
this package (Phase 2a, 2026-08-11) per
openspec/specs/dynamic-pricing/spec.md's implementation task -- relocated,
not rebuilt; behavior unchanged.

openspec/specs/dynamic-pricing/spec.md "Requirement: Tiered read resilience
against primary_snapshot". Every pricing read against ``primary_snapshot``
shares this one resolution, decided once per ``predict_price(...)`` call and
applied to every read in that call -- a single prediction must not mix
``primary_snapshot`` and ``public`` across its reads.

Three tiers, attempted in order:

1. Transient (mid-recreate). Retry a short, bounded number of times.
2. Sustained (a failed sync cycle). Degrade to reading ``public`` instead -- a
   real value, at most one sync cycle stale, not a fabricated default.
3. Cold start (neither schema has the relation). Raise
   ``PricingSchemaUnavailable`` rather than returning a price -- what the
   caller does with that is the recommendation pipeline's call, not
   pricing's.

Only ``UndefinedTable`` (relation-missing) errors are treated as a schema
outage and retried/degraded -- any other exception propagates immediately, so
a real bug doesn't get silently reinterpreted as a schema outage.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from psycopg.errors import UndefinedTable
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.asset_category import AssetCategory

logger = logging.getLogger(__name__)

# Seconds-scale total, exact schedule TBD (non-blocking open item carried
# forward from Phase 1e).
_TRANSIENT_RETRY_BACKOFF_SECONDS: tuple[float, ...] = (0.0, 0.3, 0.6)

PRIMARY_SCHEMA = "primary_snapshot"
DEGRADED_SCHEMA = "public"


class PricingSchemaUnavailable(RuntimeError):
    """Neither primary_snapshot nor public has the relations pricing needs.

    A container that has never completed a sync (both schemas are populated
    by the same external job), not a recoverable read failure.
    """


@dataclass(frozen=True)
class PricingSchemaResolution:
    """One schema decision, reused across every read in a single predict_price() call."""

    schema: str  # PRIMARY_SCHEMA or DEGRADED_SCHEMA
    degraded: bool

    @property
    def execution_options(self) -> dict:
        if self.schema == PRIMARY_SCHEMA:
            return {}
        return {"schema_translate_map": {PRIMARY_SCHEMA: self.schema}}


def _is_undefined_table(exc: Exception) -> bool:
    if isinstance(exc, UndefinedTable):
        return True
    return isinstance(getattr(exc, "orig", None), UndefinedTable)


def _probe(session: Session, schema: str) -> None:
    options = {} if schema == PRIMARY_SCHEMA else {"schema_translate_map": {PRIMARY_SCHEMA: schema}}
    session.execute(
        select(func.count()).select_from(AssetCategory),
        execution_options=options,
    )


def resolve_pricing_schema(session: Session) -> PricingSchemaResolution:
    """Resolve which schema this predict_price() call should read from.

    Not per-query -- call once and thread the result through every read.
    """
    last_exc: Exception | None = None
    for backoff in _TRANSIENT_RETRY_BACKOFF_SECONDS:
        if backoff:
            time.sleep(backoff)
        try:
            _probe(session, PRIMARY_SCHEMA)
            return PricingSchemaResolution(schema=PRIMARY_SCHEMA, degraded=False)
        except Exception as exc:
            if not _is_undefined_table(exc):
                raise
            last_exc = exc
            session.rollback()

    try:
        _probe(session, DEGRADED_SCHEMA)
    except Exception as exc:
        if not _is_undefined_table(exc):
            raise
        session.rollback()
        raise PricingSchemaUnavailable(
            "Neither primary_snapshot nor public has the pricing schema/relations "
            "(cold start -- container has never completed a sync)."
        ) from exc

    logger.warning(
        "primary_snapshot unavailable after %d retries (%s); degrading to public",
        len(_TRANSIENT_RETRY_BACKOFF_SECONDS),
        last_exc,
    )
    return PricingSchemaResolution(schema=DEGRADED_SCHEMA, degraded=True)
