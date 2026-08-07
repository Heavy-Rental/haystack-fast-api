"""HTTP intake: POST /api/v1/recommendations/from-project-spec (indexing + HR-76 user)."""

from fastapi.testclient import TestClient

ENDPOINT = "/api/v1/recommendations/from-project-spec"


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
    assert body["ingest_id"].startswith("ing_")
    assert body["user_id"] == "user_demo"
    assert body["user_name"] == "Demo User"
    assert body["data_kind"] == "unstructured"
    assert body["unstructured_count"] == 1
    assert body["structured_count"] == 0
    assert body["document_count"] == 1
    assert body["unstructured_document_count"] == 1
    assert body["chunk_count"] >= 1
    assert body["documents_written"] >= 1
    assert body["documents"]
    assert "scissors" in body["documents"][0]["content_preview"].lower()
    assert body["documents"][0]["has_embedding"] is True
    assert body["documents"][0]["meta"].get("user_id") == "user_demo"
    assert "results_by_need" not in body
    assert body["kg_built"] is True
    assert body["kg_node_count"] and body["kg_node_count"] >= 1
    assert body["kg_artifact_path"]
    assert body["kg_transform_applied"] is False
    assert body["warnings"]


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
    assert body["data_kind"] == "unstructured"
    assert body["ingest_id"].startswith("ing_")
    assert body["user_id"] == "u1"


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
    assert body["ingest_id"].startswith("ing_")
    assert body["user_id"] == "u_mp"
    assert body["data_kind"] == "unstructured"
    assert body["unstructured_count"] == 1
    assert body["document_count"] == 1
    assert body["documents_written"] >= 1
    assert "forklift" in body["documents"][0]["content_preview"].lower()
    assert body["documents"][0]["has_embedding"] is True
    assert "project.txt" in body["filenames"]


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
    assert body["data_kind"] == "structured"
    assert body["structured_count"] == 1
    assert body["document_count"] == 1
    assert body["structured_document_count"] == 1
    assert body["documents_written"] >= 1
    joined = " ".join(d["content_preview"] for d in body["documents"])
    assert "Scissors" in joined
    assert all(d["has_embedding"] for d in body["documents"])
    assert "text/csv" in body["mime_types_seen"] or body["mime_types_seen"]


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
    assert body["data_kind"] == "structured"
    assert body["document_count"] >= 1
    assert body["documents_written"] >= 1
    joined = " ".join(d["content_preview"] for d in body["documents"]).lower()
    assert "excavator" in joined


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
    assert body["data_kind"] == "unstructured"
    assert body["document_count"] == 1
    preview = body["documents"][0]["content_preview"].lower()
    assert "boom" in preview or "project" in preview


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
