"""Shared pytest fixtures."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _isolate_kg_artifact_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep mandatory KG writes out of the repo artifacts/ tree during tests."""
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path / "kg"))
    monkeypatch.setenv("PROJECT_AGENT_MODE", "stub")
    # CI-safe indexing defaults; host .env may set openai/ST or a non-default dim.
    monkeypatch.setenv("INDEXING_EMBEDDER", "mock")
    monkeypatch.setenv("INDEXING_EMBEDDING_DIM", "384")
    get_settings.cache_clear()
    from app.services.ingest_idempotency import reset_ingest_idempotency_store
    from app.services.project_knowledge_session import reset_project_knowledge_registry

    reset_project_knowledge_registry()
    reset_ingest_idempotency_store()
    yield
    reset_project_knowledge_registry()
    reset_ingest_idempotency_store()
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """HTTP client bound to a fresh application instance."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
