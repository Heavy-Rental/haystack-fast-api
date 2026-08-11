"""Phase 1e — 3-tier read-resilience resolver (SPEC-dynamic-pricing.md §5.3.1).

No real fault-injection setup against postgres-haystack is available (per the
spec's own §6 note), so the session is mocked to raise UndefinedTable on
demand.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from psycopg.errors import UndefinedTable
from sqlalchemy.exc import ProgrammingError

from app.services.pricing.read_resilience import (
    PricingSchemaUnavailable,
    resolve_pricing_schema,
)


def _undefined_table_error() -> ProgrammingError:
    return ProgrammingError("SELECT ...", {}, UndefinedTable("relation does not exist"))


def test_resolve_pricing_schema_healthy_primary() -> None:
    session = MagicMock()
    session.execute.return_value = MagicMock()

    resolution = resolve_pricing_schema(session)

    assert resolution.schema == "primary_snapshot"
    assert resolution.degraded is False
    assert resolution.execution_options == {}
    session.execute.assert_called_once()
    session.rollback.assert_not_called()


def test_resolve_pricing_schema_transient_then_recovers() -> None:
    session = MagicMock()
    session.execute.side_effect = [_undefined_table_error(), MagicMock()]

    resolution = resolve_pricing_schema(session)

    assert resolution.schema == "primary_snapshot"
    assert resolution.degraded is False
    assert session.execute.call_count == 2
    session.rollback.assert_called_once()


def test_resolve_pricing_schema_sustained_degrades_to_public() -> None:
    session = MagicMock()
    # 3 primary attempts fail, then the public probe succeeds.
    session.execute.side_effect = [
        _undefined_table_error(),
        _undefined_table_error(),
        _undefined_table_error(),
        MagicMock(),
    ]

    resolution = resolve_pricing_schema(session)

    assert resolution.schema == "public"
    assert resolution.degraded is True
    assert resolution.execution_options == {
        "schema_translate_map": {"primary_snapshot": "public"}
    }
    assert session.execute.call_count == 4


def test_resolve_pricing_schema_cold_start_raises() -> None:
    session = MagicMock()
    session.execute.side_effect = _undefined_table_error()

    with pytest.raises(PricingSchemaUnavailable):
        resolve_pricing_schema(session)


def test_resolve_pricing_schema_does_not_catch_unrelated_errors() -> None:
    session = MagicMock()
    session.execute.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        resolve_pricing_schema(session)
    session.rollback.assert_not_called()
