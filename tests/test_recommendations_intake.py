"""HTTP intake: POST /internal/v1/recommendations/submitprojectspecification (S1 lean body)."""

from fastapi.testclient import TestClient

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
TECHNICAL_KEYS = {
    "documents",
    "kg_built",
    "kg_node_count",
    "kg_artifact_path",
    "chunk_count",
    "documents_written",
    "data_kind",
}


def _assert_lean_body(body: dict) -> None:
    assert set(body.keys()) <= LEAN_KEYS
    for key in TECHNICAL_KEYS:
        assert key not in body
    assert body["ingest_id"].startswith("ing_")
    assert body["user_id"]
    assert isinstance(body["user_requirement_summary"], str)
    assert body["user_requirement_summary"].strip()
    assert isinstance(body["warnings"], list)
    assert "tentative_start_date" in body
    assert "tentative_end_date" in body
    assert isinstance(body.get("needs_summary"), list)
    assert "expected_budget" in body


def test_from_project_spec_json_unstructured(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={
            "user_id": "user_demo",
            "user_name": "Demo User",
            "start_date": "2026-09-01",
            "end_date": "2026-09-12",
            "project_text": "Indoor elevated work ~8m for scissors lift",
            "options": {"include_pricing": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    _assert_lean_body(body)
    assert body["user_id"] == "user_demo"
    assert "scissors" in body["user_requirement_summary"].lower()
    assert body["tentative_start_date"] == "2026-09-01"
    assert body["tentative_end_date"] == "2026-09-12"
    assert body["needs_summary"]
    assert body["needs_summary"][0]["need_id"] == "need_1"
    assert "scissors" in body["needs_summary"][0]["description"].lower()
    assert body["needs_summary"][0]["quantity"] == 1
    assert body["expected_budget"] is None
    assert any("expected_budget not found" in w for w in body["warnings"])
    assert "results_by_need" not in body


def test_tentative_dates_extracted_from_text_when_request_omits(
    client: TestClient,
) -> None:
    response = client.post(
        ENDPOINT,
        json={
            "user_id": "user_dates",
            "project_text": (
                "Need scissors lifts for fit-out. "
                "Rental period from 2026-09-01 to 2026-09-14. "
                "Budget SGD 10,000."
            ),
        },
    )
    assert response.status_code == 200
    body = response.json()
    _assert_lean_body(body)
    assert body["tentative_start_date"] == "2026-09-01"
    assert body["tentative_end_date"] == "2026-09-14"
    assert body["expected_budget"] is not None
    assert body["expected_budget"]["amount"] == 10000.0


def test_request_dates_override_text_extract(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={
            "user_id": "user_override",
            "start_date": "2026-10-01",
            "end_date": "2026-10-20",
            "project_text": (
                "Hire from 2026-09-01 to 2026-09-12 for earthworks."
            ),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tentative_start_date"] == "2026-10-01"
    assert body["tentative_end_date"] == "2026-10-20"


def test_expected_budget_extracted_when_present(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={
            "user_id": "user_budget",
            "project_text": (
                "Need two scissors lifts for fit-out. "
                "Project budget SGD 15,000 for rental equipment."
            ),
            "options": {"include_pricing": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    _assert_lean_body(body)
    assert body["expected_budget"] is not None
    assert body["expected_budget"]["amount"] == 15000.0
    assert body["expected_budget"]["currency"] == "SGD"
    assert body["expected_budget"]["source"] == "extracted"
    # include_pricing must not invent a budget by itself
    assert body["expected_budget"]["amount"] != 1


def test_missing_user_id_returns_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={"project_text": "Need excavator"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"


def test_empty_project_text_returns_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT, json={"user_id": "u1", "project_text": "   "}
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"
    assert body["message"]


def test_missing_project_text_returns_400(client: TestClient) -> None:
    response = client.post(ENDPOINT, json={"user_id": "u1"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"


def test_invalid_date_window_returns_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={
            "user_id": "u1",
            "start_date": "2026-09-12",
            "end_date": "2026-09-01",
            "project_text": "Need an excavator",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"
    assert "end_date" in body["message"].lower() or "start_date" in body["message"].lower()


def test_optional_dates_omitted(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={"user_id": "u1", "project_text": "Fork lift for warehouse loading"},
    )
    assert response.status_code == 200
    body = response.json()
    _assert_lean_body(body)
    assert body["user_id"] == "u1"
    assert "fork" in body["user_requirement_summary"].lower()
    assert body["tentative_start_date"] is None
    assert body["tentative_end_date"] is None


def test_multipart_text_file_unstructured(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={
            "user_id": "u_mp",
            "start_date": "2026-09-01",
            "end_date": "2026-09-12",
        },
        files={
            "file": ("project.txt", b"Need one forklift for loading bay", "text/plain"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    _assert_lean_body(body)
    assert body["user_id"] == "u_mp"
    assert "forklift" in body["user_requirement_summary"].lower()
    assert body["tentative_start_date"] == "2026-09-01"
    assert body["tentative_end_date"] == "2026-09-12"
    assert body["needs_summary"]
    assert "forklift" in body["needs_summary"][0]["description"].lower()


def test_needs_summary_empty_when_decomposer_returns_none(
    client: TestClient, monkeypatch: object
) -> None:
    """Inject empty decomposer via service factory path is harder on HTTP;
    assert stub path still produces needs — empty path covered in unit-style service test.
    """
    from app.pipelines.indexing.embedder_factory import build_document_embedder
    from app.pipelines.indexing.pipeline import build_indexing_pipeline
    from app.services.indexing import IndexingIngestService
    from haystack.document_stores.in_memory import InMemoryDocumentStore

    class _EmptyDecomposer:
        def decompose(self, source_text: str) -> list:
            return []

    store = InMemoryDocumentStore()
    result = IndexingIngestService(
        pipeline=build_indexing_pipeline(
            document_store=store,
            embedder=build_document_embedder(mode="mock", dimension=8),
        ),
        document_store=store,
        need_decomposer=_EmptyDecomposer(),
    ).ingest_from_project_spec(
        user_id="u_empty",
        project_text="Some project text about equipment",
    )
    assert result.needs_summary == []
    assert any("needs_summary empty" in w for w in result.warnings)


def test_multipart_invalid_date_window_returns_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={
            "user_id": "u1",
            "start_date": "2026-09-12",
            "end_date": "2026-09-01",
        },
        files={
            "file": ("project.txt", b"Need excavator", "text/plain"),
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"
    assert "end_date" in body["message"].lower() or "start_date" in body["message"].lower()


def test_multipart_csv_structured(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={"user_id": "u_csv"},
        files={
            "file": ("needs.csv", b"type,qty\nScissors Lift,2\n", "text/csv"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    _assert_lean_body(body)
    assert "scissors" in body["user_requirement_summary"].lower()


def test_multipart_json_file_structured(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={"user_id": "u_json"},
        files={
            "file": ("needs.json", b'{"equipment":"excavator"}', "application/json"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    _assert_lean_body(body)
    assert "excavator" in body["user_requirement_summary"].lower()


def test_multipart_markdown_converts(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={"user_id": "u_md"},
        files={
            "file": ("brief.md", b"# Project\n\nNeed boom lift at facade", "text/markdown"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    _assert_lean_body(body)
    summary = body["user_requirement_summary"].lower()
    assert "boom" in summary or "project" in summary


def test_multipart_unsupported_type_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={"user_id": "u1"},
        files={
            "file": ("malware.exe", b"MZ\x90", "application/octet-stream"),
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"
    assert "unsupported" in body["message"].lower() or "unclassified" in body["message"].lower()


def test_multipart_empty_returns_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={"user_id": "u1"},
        files={},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"


def test_multipart_empty_file_returns_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={"user_id": "u1"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"


def test_multipart_missing_user_id_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={},
        files={
            "file": ("project.txt", b"Need forklift", "text/plain"),
        },
    )
    assert response.status_code == 400
