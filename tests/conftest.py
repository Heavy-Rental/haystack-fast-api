"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """HTTP client bound to a fresh application instance."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
