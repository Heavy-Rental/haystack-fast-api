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
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """HTTP client bound to a fresh application instance."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
