"""Phase 3d application-lifespan scheduler for dynamic-pricing retraining."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import Settings
from app.services.pricing import retrain_job

logger = logging.getLogger(__name__)

JOB_ID = "pricing-scheduled-retrain"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def compute_next_run_time(settings: Settings) -> dt.datetime:
    """Return now for a never-run/overdue job, otherwise its exact due time."""
    state = retrain_job.load_state()
    now = _utcnow()
    if state.last_run_at is None:
        return now

    next_due = state.last_run_at.astimezone(dt.UTC) + dt.timedelta(
        days=settings.pricing_retrain_interval_days
    )
    return max(now, next_due)


async def _run_scheduled_retrain() -> None:
    """Keep synchronous model fitting and database reads off the event loop."""
    outcome = await asyncio.to_thread(retrain_job.run_scheduled_retrain)
    logger.info(
        "Pricing scheduled retrain completed (status=%s message=%s)",
        outcome.status,
        outcome.message,
    )


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    """Build the single-instance, coalescing monthly retrain scheduler."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _run_scheduled_retrain,
        trigger=IntervalTrigger(
            days=settings.pricing_retrain_interval_days,
            timezone="UTC",
        ),
        id=JOB_ID,
        next_run_time=compute_next_run_time(settings),
        coalesce=True,
        max_instances=1,
        misfire_grace_time=settings.pricing_retrain_misfire_grace_seconds,
        replace_existing=True,
    )
    return scheduler
