from __future__ import annotations

import datetime as dt
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services.pricing import retrain_job, scheduler


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "PRICING_RETRAIN_INTERVAL_DAYS": 30,
        "PRICING_RETRAIN_MISFIRE_GRACE_SECONDS": 3600,
    }
    values.update(overrides)
    return Settings(**values)


def test_compute_next_run_time_fires_promptly_when_never_run(monkeypatch) -> None:
    now = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC)
    monkeypatch.setattr(scheduler, "_utcnow", lambda: now)
    monkeypatch.setattr(
        scheduler.retrain_job,
        "load_state",
        lambda: retrain_job.RetrainState(last_run_at=None, last_outcome=None),
    )

    assert scheduler.compute_next_run_time(_settings()) == now


def test_compute_next_run_time_waits_until_exact_due_time(monkeypatch) -> None:
    now = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC)
    last_run = now - dt.timedelta(days=10)
    monkeypatch.setattr(scheduler, "_utcnow", lambda: now)
    monkeypatch.setattr(
        scheduler.retrain_job,
        "load_state",
        lambda: retrain_job.RetrainState(last_run_at=last_run, last_outcome=None),
    )

    assert scheduler.compute_next_run_time(_settings()) == last_run + dt.timedelta(days=30)


def test_compute_next_run_time_fires_once_when_overdue(monkeypatch) -> None:
    now = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC)
    monkeypatch.setattr(scheduler, "_utcnow", lambda: now)
    monkeypatch.setattr(
        scheduler.retrain_job,
        "load_state",
        lambda: retrain_job.RetrainState(
            last_run_at=now - dt.timedelta(days=31),
            last_outcome=None,
        ),
    )

    assert scheduler.compute_next_run_time(_settings()) == now


def test_build_scheduler_registers_one_coalescing_interval_job(monkeypatch) -> None:
    now = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.UTC)
    monkeypatch.setattr(scheduler, "compute_next_run_time", lambda _settings: now)

    built = scheduler.build_scheduler(_settings())

    jobs = built.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == scheduler.JOB_ID
    assert job.next_run_time == now
    assert job.trigger.interval == dt.timedelta(days=30)
    assert job.coalesce is True
    assert job.max_instances == 1
    assert job.misfire_grace_time == 3600


def test_lifespan_does_not_build_scheduler_when_default_disabled(
    monkeypatch,
) -> None:
    build_scheduler = Mock(side_effect=AssertionError("scheduler must remain disabled"))
    monkeypatch.setattr(scheduler, "build_scheduler", build_scheduler)
    monkeypatch.delenv("PRICING_RETRAIN_ENABLED", raising=False)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        assert client.get("/openapi.json").status_code == 200

    build_scheduler.assert_not_called()


def test_lifespan_starts_and_stops_scheduler_when_enabled(monkeypatch) -> None:
    built = Mock()
    built.start = Mock()
    built.shutdown = Mock()
    build_scheduler = Mock(return_value=built)
    monkeypatch.setattr(scheduler, "build_scheduler", build_scheduler)
    monkeypatch.setenv("PRICING_RETRAIN_ENABLED", "true")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        assert client.get("/openapi.json").status_code == 200
        built.start.assert_called_once_with()
        built.shutdown.assert_not_called()

    build_scheduler.assert_called_once()
    settings = build_scheduler.call_args.args[0]
    assert settings.pricing_retrain_enabled is True
    built.shutdown.assert_called_once_with(wait=False)
