"""Part 1: FileTypeRouter / DataKindClassifier + indexing pipeline."""

from pathlib import Path

from haystack.dataclasses import ByteStream

from app.pipelines.indexing.data_kind_classifier import DataKindClassifier
from app.pipelines.indexing.mime_map import (
    MIME_CSV,
    MIME_JSON,
    MIME_MARKDOWN,
    MIME_TEXT_PLAIN,
    guess_mime_from_filename,
)
from app.pipelines.indexing.pipeline import build_indexing_pipeline, run_indexing_pipeline
from app.services.indexing import (
    IndexingIngestService,
    byte_stream_from_project_text,
    byte_stream_from_upload,
)


def _bs(name: str, data: bytes = b"payload") -> ByteStream:
    mime = guess_mime_from_filename(name)
    return ByteStream(data=data, meta={"file_path": name, "filename": name}, mime_type=mime)


def test_guess_mime_map() -> None:
    assert guess_mime_from_filename("a.txt") == MIME_TEXT_PLAIN
    assert guess_mime_from_filename("a.md") == MIME_MARKDOWN
    assert guess_mime_from_filename("a.csv") == MIME_CSV
    assert guess_mime_from_filename("a.json") == MIME_JSON
    assert guess_mime_from_filename("a.bin") is None


def test_classifier_unstructured_txt() -> None:
    out = DataKindClassifier().run(sources=[_bs("brief.txt", b"need a scissors lift")])
    assert out["data_kind"] == "unstructured"
    assert out["unstructured_count"] == 1
    assert out["structured_count"] == 0
    assert out["unclassified_count"] == 0
    assert MIME_TEXT_PLAIN in out["mime_types_seen"]


def test_classifier_structured_csv() -> None:
    out = DataKindClassifier().run(sources=[_bs("needs.csv", b"type,qty\nexcavator,1\n")])
    assert out["data_kind"] == "structured"
    assert out["structured_count"] == 1
    assert MIME_CSV in out["mime_types_seen"]


def test_classifier_structured_json() -> None:
    out = DataKindClassifier().run(sources=[_bs("needs.json", b'{"needs":[]}')])
    assert out["data_kind"] == "structured"
    assert out["structured_count"] == 1


def test_classifier_unclassified_bin() -> None:
    out = DataKindClassifier().run(sources=[_bs("payload.bin", b"\x00\x01")])
    assert out["data_kind"] == "unclassified"
    assert out["unclassified_count"] == 1


def test_classifier_mixed() -> None:
    out = DataKindClassifier().run(
        sources=[
            _bs("needs.csv", b"a,b\n1,2\n"),
            _bs("notes.md", b"# notes"),
        ]
    )
    assert out["data_kind"] == "mixed"
    assert out["structured_count"] == 1
    assert out["unstructured_count"] == 1


def test_pipeline_run_with_path(tmp_path: Path) -> None:
    path = tmp_path / "spec.md"
    path.write_text("# project\nneed forklift\n", encoding="utf-8")
    # Path-based sources: FileTypeRouter guesses MIME from extension on disk.
    pipe = build_indexing_pipeline()
    out = run_indexing_pipeline(pipe, sources=[path])
    assert out["data_kind"] == "unstructured"
    assert out["unstructured_count"] == 1


def test_service_project_text_unstructured() -> None:
    service = IndexingIngestService()
    result = service.ingest_from_project_spec(
        user_id="u_svc",
        project_text="Indoor elevated work for scissors lift",
    )
    assert result.ingest_id.startswith("ing_")
    assert result.user_id == "u_svc"
    assert result.data_kind == "unstructured"
    assert result.unstructured_count == 1
    assert result.structured_count == 0
    assert result.documents_written >= 1
    assert result.warnings


def test_service_csv_structured() -> None:
    service = IndexingIngestService()
    src = byte_stream_from_upload(
        raw=b"equipment,qty\nBoom Lift,1\n",
        filename="fleet.csv",
        content_type="text/csv",
    )
    result = service.ingest_from_project_spec(user_id="u_csv", file_sources=[src])
    assert result.data_kind == "structured"
    assert result.structured_count == 1
    assert result.documents_written >= 1
    assert "fleet.csv" in result.filenames


def test_service_unsupported_raises() -> None:
    from app.core.exceptions import BadRequestError
    import pytest

    service = IndexingIngestService()
    src = byte_stream_from_upload(raw=b"MZ", filename="tool.exe", content_type=None)
    with pytest.raises(BadRequestError):
        service.ingest_from_project_spec(user_id="u1", file_sources=[src])


def test_byte_stream_from_project_text() -> None:
    bs = byte_stream_from_project_text("hello")
    assert bs.mime_type == MIME_TEXT_PLAIN
    assert bs.data == b"hello"
