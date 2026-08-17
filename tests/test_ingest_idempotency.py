"""S2a / C1 — Call 1 Idempotency-Key (TDD/BDD).

BDD:
  Scenario: Idempotent ingest replay
    Given a successful Call 1 with Idempotency-Key "k1"
    When  the same request is POSTed again with Idempotency-Key "k1"
    Then  the response ingest_id equals the first response
    And   a second full index+KG is not required

  Scenario: Missing key is not idempotent
    Given no Idempotency-Key header
    When  two identical successful ingests run
    Then  two different ingest_ids are returned
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi.testclient import TestClient

from app.schemas.indexing import IngestFromProjectSpecResponse
from app.services.indexing import IndexingIngestService
from app.services.ingest_idempotency import (
    InMemoryIdempotencyStore,
    normalize_idempotency_key,
)

ENDPOINT = "/internal/v1/recommendations/submitprojectspecification"

LEAN_KEYS = {
    "ingest_id",
    "user_id",
    "user_requirement_summary",
    "tentative_start_date",
    "tentative_end_date",
    "needs_summary",
    "expected_budget",
    "warnings",
}


def _json_payload(user_id: str = "user_idem", text: str = "Need scissors lift") -> dict:
    return {
        "user_id": user_id,
        "project_text": text,
        "start_date": "2026-09-01",
        "end_date": "2026-09-12",
    }


def test_same_idempotency_key_returns_same_ingest_id(client: TestClient) -> None:
    headers = {"Idempotency-Key": "k1-same"}
    r1 = client.post(ENDPOINT, json=_json_payload(), headers=headers)
    r2 = client.post(ENDPOINT, json=_json_payload(), headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    b1, b2 = r1.json(), r2.json()
    assert b1["ingest_id"] == b2["ingest_id"]
    assert b1["user_id"] == b2["user_id"] == "user_idem"
    assert set(b1.keys()) <= LEAN_KEYS
    assert set(b2.keys()) <= LEAN_KEYS


def test_same_key_does_not_re_run_ingest_service(
    client: TestClient, monkeypatch: object
) -> None:
    calls = {"n": 0}
    original = IndexingIngestService.ingest_from_project_spec

    def counting(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        IndexingIngestService, "ingest_from_project_spec", counting
    )
    headers = {"Idempotency-Key": "k1-count"}
    r1 = client.post(ENDPOINT, json=_json_payload("user_count"), headers=headers)
    r2 = client.post(ENDPOINT, json=_json_payload("user_count"), headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["ingest_id"] == r2.json()["ingest_id"]
    assert calls["n"] == 1


def test_different_keys_yield_distinct_ingest_ids(client: TestClient) -> None:
    payload = _json_payload("user_diff")
    r1 = client.post(ENDPOINT, json=payload, headers={"Idempotency-Key": "key-a"})
    r2 = client.post(ENDPOINT, json=payload, headers={"Idempotency-Key": "key-b"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["ingest_id"] != r2.json()["ingest_id"]


def test_missing_key_always_new_ingest(client: TestClient) -> None:
    payload = _json_payload("user_nokey")
    r1 = client.post(ENDPOINT, json=payload)
    r2 = client.post(ENDPOINT, json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["ingest_id"] != r2.json()["ingest_id"]


def test_multipart_honors_idempotency_key(client: TestClient) -> None:
    headers = {"Idempotency-Key": "mp-key-1"}
    data = {
        "user_id": "user_mp_idem",
        "start_date": "2026-09-01",
        "end_date": "2026-09-12",
    }
    files = {
        "file": ("project.txt", b"Need one forklift for loading bay", "text/plain"),
    }
    r1 = client.post(ENDPOINT, data=data, files=files, headers=headers)
    # re-open file bytes for second post
    files2 = {
        "file": ("project.txt", b"Need one forklift for loading bay", "text/plain"),
    }
    r2 = client.post(ENDPOINT, data=data, files=files2, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["ingest_id"] == r2.json()["ingest_id"]
    assert "forklift" in r1.json()["user_requirement_summary"].lower()


def test_failed_request_not_cached_as_success(client: TestClient) -> None:
    headers = {"Idempotency-Key": "fail-then-ok"}
    bad = client.post(
        ENDPOINT,
        json={"user_id": "user_fail", "project_text": "   "},
        headers=headers,
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "bad_request"
    assert "message" in bad.json()

    good = client.post(
        ENDPOINT,
        json=_json_payload("user_fail", "Need excavator after fix"),
        headers=headers,
    )
    assert good.status_code == 200
    replay = client.post(
        ENDPOINT,
        json=_json_payload("user_fail", "Need excavator after fix"),
        headers=headers,
    )
    assert replay.status_code == 200
    assert good.json()["ingest_id"] == replay.json()["ingest_id"]


def test_idempotency_scoped_by_user_id(client: TestClient) -> None:
    headers = {"Idempotency-Key": "shared-key"}
    r1 = client.post(ENDPOINT, json=_json_payload("user_a"), headers=headers)
    r2 = client.post(ENDPOINT, json=_json_payload("user_b"), headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["ingest_id"] != r2.json()["ingest_id"]


def test_error_body_shape_regression_with_key(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={"user_id": "u1"},  # missing project_text
        headers={"Idempotency-Key": "err-shape"},
    )
    assert response.status_code == 400
    body = response.json()
    assert set(body.keys()) == {"error", "message"}
    assert body["error"] == "bad_request"
    assert body["message"]


def test_success_keeps_fr_ix_023_fields_with_key(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={
            "user_id": "user_fr",
            "project_text": (
                "Need scissors lifts. Budget SGD 15000. "
                "From 2026-09-01 to 2026-09-14."
            ),
        },
        headers={"Idempotency-Key": "fr-ix-023"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) <= LEAN_KEYS
    assert body["ingest_id"].startswith("ing_")
    assert body["user_requirement_summary"]
    assert body["needs_summary"]
    assert body["expected_budget"] is not None
    assert body["expected_budget"]["amount"] == 15000.0
    assert body["tentative_start_date"] == "2026-09-01"
    assert body["tentative_end_date"] == "2026-09-14"
    assert "results_by_need" not in body


def test_blank_idempotency_key_treated_as_missing(client: TestClient) -> None:
    """Whitespace-only Idempotency-Key MUST behave like a missing key."""
    payload = _json_payload("user_blank")
    r1 = client.post(ENDPOINT, json=payload, headers={"Idempotency-Key": "   "})
    r2 = client.post(ENDPOINT, json=payload, headers={"Idempotency-Key": "\t"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["ingest_id"] != r2.json()["ingest_id"]
    assert normalize_idempotency_key("   ") is None
    assert normalize_idempotency_key("") is None
    assert normalize_idempotency_key(None) is None


def test_concurrent_same_key_single_flight(
    client: TestClient, monkeypatch: object
) -> None:
    """Concurrent POSTs with the same scoped key run the producer once."""
    calls = {"n": 0}
    original = IndexingIngestService.ingest_from_project_spec
    release = threading.Event()
    entered = threading.Event()

    def slow_counting(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        entered.set()
        # Hold the first producer so the second request joins single-flight.
        release.wait(timeout=5.0)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        IndexingIngestService, "ingest_from_project_spec", slow_counting
    )
    headers = {"Idempotency-Key": "concurrent-k1"}
    payload = _json_payload("user_concurrent")

    def _post() -> tuple[int, str]:
        response = client.post(ENDPOINT, json=payload, headers=headers)
        return response.status_code, response.json()["ingest_id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_post)
        assert entered.wait(timeout=5.0)
        f2 = pool.submit(_post)
        # Give waiter a moment to join inflight before producer finishes.
        time.sleep(0.05)
        release.set()
        s1, id1 = f1.result(timeout=30.0)
        s2, id2 = f2.result(timeout=30.0)

    assert s1 == 200
    assert s2 == 200
    assert id1 == id2
    assert calls["n"] == 1


def test_store_ttl_expires_entry() -> None:
    """Process-local store drops entries after TTL (unit, no HTTP)."""
    store = InMemoryIdempotencyStore(ttl_seconds=0.05)
    body = IngestFromProjectSpecResponse(
        ingest_id="ing_ttl_test",
        user_id="u_ttl",
        user_requirement_summary="Need scissors lift",
        tentative_start_date=date(2026, 9, 1),
        tentative_end_date=date(2026, 9, 12),
        needs_summary=[],
        expected_budget=None,
        warnings=[],
    )
    store.put("u_ttl:k-ttl", body)
    assert store.get("u_ttl:k-ttl") is not None
    time.sleep(0.08)
    assert store.get("u_ttl:k-ttl") is None
