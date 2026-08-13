"""Part 3: clean → split → embed → write into DocumentStore."""

import pytest
from haystack.dataclasses import ByteStream
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.pipelines.indexing.document_store import get_document_store, reset_document_store
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.mime_map import guess_mime_from_filename
from app.pipelines.indexing.pipeline import build_indexing_pipeline, run_indexing_pipeline
from app.services.indexing import IndexingIngestService


def _bs(name: str, data: bytes) -> ByteStream:
    return ByteStream(
        data=data,
        meta={"file_path": name, "filename": name},
        mime_type=guess_mime_from_filename(name),
    )


def test_build_mock_embedder_dimension() -> None:
    emb = build_document_embedder(mode="mock", dimension=16)
    from haystack.dataclasses import Document

    out = emb.run(documents=[Document(content="hello excavator")])
    docs = out["documents"]
    assert len(docs) == 1
    assert docs[0].embedding is not None
    assert len(docs[0].embedding) == 16


def test_build_openai_embedder_passes_dimensions() -> None:
    from app.pipelines.indexing.embedder_factory import openai_embedding_dimensions

    assert openai_embedding_dimensions("text-embedding-3-small", 768) == 768
    assert openai_embedding_dimensions("text-embedding-3-large", 384) == 384
    assert openai_embedding_dimensions("text-embedding-ada-002", 384) is None

    emb = build_document_embedder(
        mode="openai",
        dimension=768,
        openai_api_key="sk-test",
        openai_model="text-embedding-3-small",
    )
    assert getattr(emb, "dimensions", None) == 768


def test_ingest_maps_pgvector_dimension_error() -> None:
    from app.core.exceptions import BadRequestError
    from app.services.indexing import _reraise_embedding_dimension_error

    with pytest.raises(BadRequestError, match="Embedding dimension mismatch"):
        _reraise_embedding_dimension_error(
            RuntimeError("expected 384 dimensions, not 768")
        )


def test_pipeline_writes_embedded_chunks() -> None:
    store = InMemoryDocumentStore()
    pipe = build_indexing_pipeline(
        document_store=store,
        embedder=build_document_embedder(mode="mock", dimension=32),
        split_length=50,
        split_overlap=0,
    )
    text = "Need scissors lift. " * 40  # force multiple word-splits
    out = run_indexing_pipeline(pipe, sources=[_bs("long.txt", text.encode("utf-8"))])

    assert out["data_kind"] == "unstructured"
    assert out["documents_written"] >= 1
    assert out["chunk_count"] == out["documents_written"]
    assert store.count_documents() == out["documents_written"]

    chunks = out["chunk_documents"]
    assert chunks
    assert all(c.embedding is not None for c in chunks)


def test_pipeline_short_text_one_chunk() -> None:
    store = InMemoryDocumentStore()
    pipe = build_indexing_pipeline(
        document_store=store,
        embedder=build_document_embedder(mode="mock", dimension=8),
    )
    out = run_indexing_pipeline(
        pipe,
        sources=[_bs("brief.txt", b"Need one forklift for loading bay")],
    )
    assert out["documents_written"] == 1
    assert out["chunk_count"] == 1
    assert store.count_documents() == 1


def test_pipeline_csv_structured_writes() -> None:
    store = InMemoryDocumentStore()
    pipe = build_indexing_pipeline(
        document_store=store,
        embedder=build_document_embedder(mode="mock", dimension=8),
    )
    out = run_indexing_pipeline(
        pipe,
        sources=[_bs("needs.csv", b"type,qty\nBoom Lift,2\n")],
    )
    assert out["data_kind"] == "structured"
    assert out["documents_written"] >= 1
    assert store.count_documents() >= 1


def test_service_returns_write_fields() -> None:
    reset_document_store()
    service = IndexingIngestService(
        pipeline=build_indexing_pipeline(
            document_store=get_document_store(),
            embedder=build_document_embedder(mode="mock", dimension=16),
        )
    )
    result = service.ingest_from_project_spec(
        user_id="u_vec",
        project_text="Indoor elevated work for scissors lift",
    )
    assert result.ingest_id.startswith("ing_")
    assert result.user_id == "u_vec"
    assert "scissors" in result.user_requirement_summary.lower()
    assert get_document_store().count_documents() >= 1


def test_reset_document_store_clears() -> None:
    store = reset_document_store()
    assert store.count_documents() == 0
    pipe = build_indexing_pipeline(
        document_store=store,
        embedder=build_document_embedder(mode="mock", dimension=4),
    )
    run_indexing_pipeline(pipe, sources=[_bs("a.txt", b"hello world excavator")])
    assert store.count_documents() >= 1
    reset_document_store()
    assert get_document_store().count_documents() == 0
