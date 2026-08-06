"""MVP Intake: POST /api/v1/recommendations/from-project-spec."""

from fastapi.testclient import TestClient

from app.schemas.recommendations import DecomposedNeed
from app.services.recommendations import RecommendationService

ENDPOINT = "/api/v1/recommendations/from-project-spec"


class _FixedDecomposer:
    """Test double that returns a fixed internal need list."""

    def __init__(self, needs: list[DecomposedNeed]) -> None:
        self._needs = needs

    def decompose(self, source_text: str) -> list[DecomposedNeed]:
        assert source_text  # source must be non-empty when we get here
        return list(self._needs)


def test_from_project_spec_happy_path_free_text(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={
            "start_date": "2026-09-01",
            "end_date": "2026-09-12",
            "project_text": "Indoor elevated work ~8m for scissors lift",
            "options": {"include_pricing": True},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommendation_id"].startswith("rec_")
    assert body["start_date"] == "2026-09-01"
    assert body["end_date"] == "2026-09-12"
    assert len(body["results_by_need"]) == 1
    row = body["results_by_need"][0]
    assert row["need_id"] == "need_1"
    assert "item" in row
    assert "items" not in row
    # Full FR-010 path: seed fleet match → singular RecommendationItem
    assert row["item"] is not None
    assert row["item"]["equipment_type"] == "Scissors Lift"
    assert row["item"]["rank"] == 1
    assert row["item"]["rationale"]


def test_empty_project_text_returns_400(client: TestClient) -> None:
    response = client.post(ENDPOINT, json={"project_text": "   "})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"
    assert body["message"]


def test_missing_project_text_returns_400(client: TestClient) -> None:
    response = client.post(ENDPOINT, json={})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"


def test_invalid_date_window_returns_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={
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
        json={"project_text": "Fork lift for warehouse loading"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["start_date"] is None
    assert body["end_date"] is None
    assert len(body["results_by_need"]) == 1
    assert "item" in body["results_by_need"][0]


def test_quantity_expansion_two_unit_needs() -> None:
    """quantity=2 → two unit-need rows; RecommendationItem has no quantity."""
    service = RecommendationService(
        decomposer=_FixedDecomposer(
            [
                DecomposedNeed(
                    need_id="need_1",
                    description="Scissors lift indoor",
                    equipment_hints=["scissors lift"],
                    quantity=2,
                )
            ]
        )
    )
    result = service.recommend_from_project_spec(
        project_text="two scissors lifts for indoor work"
    )
    assert len(result.results_by_need) == 2
    assert result.results_by_need[0].need_id == "need_1__u1"
    assert result.results_by_need[1].need_id == "need_1__u2"
    for row in result.results_by_need:
        assert row.item is not None
        assert "quantity" not in row.item.model_dump()


def test_multi_need_from_decomposer_independent_rows() -> None:
    service = RecommendationService(
        decomposer=_FixedDecomposer(
            [
                DecomposedNeed(
                    need_id="need_1",
                    description="Scissors lift",
                    quantity=1,
                ),
                DecomposedNeed(
                    need_id="need_2",
                    description="Excavator for trench",
                    equipment_hints=["excavator"],
                    quantity=1,
                ),
            ]
        )
    )
    result = service.recommend_from_project_spec(project_text="scissors and excavator")
    assert len(result.results_by_need) == 2
    assert [r.need_id for r in result.results_by_need] == ["need_1", "need_2"]
    for row in result.results_by_need:
        assert row.item is not None
        dumped = row.model_dump()
        assert "item" in dumped
        assert "items" not in dumped


def test_singular_item_shape_in_json(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        json={"project_text": "Boom lift for facade work"},
    )
    assert response.status_code == 200
    row = response.json()["results_by_need"][0]
    assert set(row.keys()) >= {"need_id", "item", "warnings"}
    assert "items" not in row


def test_multipart_text_file(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={
            "start_date": "2026-09-01",
            "end_date": "2026-09-12",
        },
        files={
            "file": ("project.txt", b"Need one forklift for loading bay", "text/plain"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommendation_id"].startswith("rec_")
    assert len(body["results_by_need"]) >= 1
    assert "item" in body["results_by_need"][0]


def test_multipart_empty_returns_400(client: TestClient) -> None:
    response = client.post(
        ENDPOINT,
        data={},
        files={},
    )
    # No file and no project_text
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "bad_request"


def test_recommendation_item_schema_has_no_quantity() -> None:
    from app.schemas.recommendations import RecommendationItem

    fields = RecommendationItem.model_fields
    assert "quantity" not in fields
