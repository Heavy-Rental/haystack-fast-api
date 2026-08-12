"""S2a / C1 — X-Correlation-Id / traceparent middleware tests."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient


def test_correlation_header_echoed_when_provided(client: TestClient) -> None:
    cid = "corr-client-123"
    response = client.get("/health", headers={"X-Correlation-Id": cid})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-Id") == cid


def test_correlation_header_minted_when_missing(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    echoed = response.headers.get("X-Correlation-Id")
    assert echoed
    assert len(echoed) >= 8


def test_correlation_logged_on_ingest(
    client: TestClient, caplog: object
) -> None:
    cid = "corr-ingest-xyz"
    with caplog.at_level(logging.INFO, logger="app.request"):  # type: ignore[attr-defined]
        response = client.post(
            "/internal/v1/recommendations/submitprojectspecification",
            json={
                "user_id": "user_corr",
                "project_text": "Need scissors lift for indoor work",
            },
            headers={"X-Correlation-Id": cid},
        )
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-Id") == cid
    # Request path logged; correlation_id bound on LogRecord (FR-IX-025)
    records = list(caplog.records)  # type: ignore[attr-defined]
    messages = [r.getMessage() for r in records]
    assert any("submitprojectspecification" in m for m in messages)
    request_records = [r for r in records if r.name == "app.request"]
    assert request_records
    assert any(
        getattr(r, "correlation_id", None) == cid for r in request_records
    )


def test_traceparent_accepted_without_error(client: TestClient) -> None:
    response = client.get(
        "/health",
        headers={
            "X-Correlation-Id": "corr-tp",
            "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-Id") == "corr-tp"


def test_qa_route_echoes_correlation(client: TestClient) -> None:
    # Seed a session via ingest first
    ingest = client.post(
        "/internal/v1/recommendations/submitprojectspecification",
        json={
            "user_id": "user_qa_corr",
            "project_text": "Need excavator for soft clay site",
        },
        headers={"X-Correlation-Id": "corr-ingest-qa"},
    )
    assert ingest.status_code == 200
    body = ingest.json()
    cid = "corr-qa-456"
    qa = client.post(
        "/internal/v1/recommendations/project-knowledge/getassetrecommendations",
        json={
            "user_id": body["user_id"],
            "ingest_id": body["ingest_id"],
            "query": "What equipment is needed?",
        },
        headers={"X-Correlation-Id": cid},
    )
    assert qa.status_code == 200
    assert qa.headers.get("X-Correlation-Id") == cid
