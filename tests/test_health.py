"""Health endpoint tests (uses shared PostgreSQL when reachable)."""

from fastapi.testclient import TestClient


def test_health_endpoint_shape(client: TestClient) -> None:
    """GET /health returns the documented schema fields."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "database" in body
    assert body["status"] in {"ok", "degraded"}
    assert body["database"] in {"up", "down"}


def test_health_ok_when_db_up(client: TestClient) -> None:
    """When Postgres is reachable, health reports ok / up."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    if body["database"] == "up":
        assert body["status"] == "ok"
    else:
        # Shared DB may be temporarily unavailable in some environments.
        assert body["status"] == "degraded"
