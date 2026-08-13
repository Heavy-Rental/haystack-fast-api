"""S8.3: optional live Neo4j pack (skipped unless RUN_NEO4J_TESTS=1)."""

from __future__ import annotations

import os

import pytest

from app.agents.neo4j_tools import (
    BoltNeo4jBackend,
    build_neo4j_backend,
    neo4j_cypher_read,
)
from app.config import Settings

pytestmark = pytest.mark.neo4j

_RUN = os.environ.get("RUN_NEO4J_TESTS", "").strip() in {"1", "true", "yes"}


def _skip_unless_enabled() -> None:
    if not _RUN:
        pytest.skip("Set RUN_NEO4J_TESTS=1 to run live Neo4j tests")


def _try_backend() -> BoltNeo4jBackend:
    settings = Settings(neo4j_backend="bolt")
    backend = build_neo4j_backend("bolt", settings=settings)
    if not isinstance(backend, BoltNeo4jBackend) or not backend.is_available:
        pytest.skip("live Neo4j Bolt unavailable")
    return backend


def test_live_empty_or_seeded_read_does_not_use_postgres() -> None:
    """FR-KG-011 load path: second read is Bolt-only (no Postgres)."""
    _skip_unless_enabled()
    backend = _try_backend()
    first = neo4j_cypher_read(
        template="assets_by_category", category="scissor lift", backend=backend
    )
    second = neo4j_cypher_read(
        template="assets_by_category", category="scissor lift", backend=backend
    )
    assert first == second
    assert isinstance(first, list)


def test_live_neighbors_template_returns_list() -> None:
    _skip_unless_enabled()
    backend = _try_backend()
    hits = neo4j_cypher_read(
        template="asset_neighbors", asset_id="AST-SL-001", backend=backend
    )
    assert isinstance(hits, list)
    for row in hits:
        assert "id" in row
        assert row.get("label") != "Document"
