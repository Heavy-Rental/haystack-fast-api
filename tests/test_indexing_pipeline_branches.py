"""Packt Ch.4 dual-branch indexing: unstructured vs CSV paths."""

from haystack.dataclasses import ByteStream, Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.pipelines.indexing.document_sanitizer import DocumentSanitizer
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.mime_map import guess_mime_from_filename
from app.pipelines.indexing.pipeline import build_indexing_pipeline, run_indexing_pipeline


def _bs(name: str, data: bytes) -> ByteStream:
    return ByteStream(
        data=data,
        meta={"file_path": name, "filename": name},
        mime_type=guess_mime_from_filename(name),
    )


def test_sanitizer_drops_empty() -> None:
    out = DocumentSanitizer().run(
        documents=[
            Document(content="  "),
            Document(content="keep me"),
            Document(content="\x00nullish"),
        ]
    )
    contents = [d.content for d in out["documents"]]
    assert contents == ["keep me", "nullish"]


def test_unstructured_branch_txt() -> None:
    store = InMemoryDocumentStore()
    pipe = build_indexing_pipeline(
        document_store=store,
        embedder=build_document_embedder(mode="mock", dimension=8),
    )
    assert "file_type_router" in pipe.graph.nodes
    assert "csv_splitter" in pipe.graph.nodes
    assert "text_splitter" in pipe.graph.nodes
    assert "sanitizer" in pipe.graph.nodes

    out = run_indexing_pipeline(
        pipe,
        sources=[_bs("brief.txt", b"Need one forklift for loading bay")],
    )
    assert out["data_kind"] == "unstructured"
    assert out["unstructured_count"] == 1
    assert out["structured_count"] == 0
    assert out["documents_written"] >= 1
    assert all(d.embedding is not None for d in out["chunk_documents"])


def test_csv_branch_row_wise_chunks() -> None:
    store = InMemoryDocumentStore()
    pipe = build_indexing_pipeline(
        document_store=store,
        embedder=build_document_embedder(mode="mock", dimension=8),
    )
    raw = b"type,qty\nBoom Lift,1\nScissors Lift,2\n"
    out = run_indexing_pipeline(pipe, sources=[_bs("needs.csv", raw)])
    assert out["data_kind"] == "structured"
    assert out["structured_count"] == 1
    # Row-wise splitter → one doc per row (incl. header)
    assert out["chunk_count"] >= 2
    assert out["documents_written"] == out["chunk_count"]
    joined = " ".join(d.content or "" for d in out["chunk_documents"])
    assert "Boom Lift" in joined
    assert "Scissors Lift" in joined


def test_mixed_txt_and_csv() -> None:
    store = InMemoryDocumentStore()
    pipe = build_indexing_pipeline(
        document_store=store,
        embedder=build_document_embedder(mode="mock", dimension=8),
    )
    out = run_indexing_pipeline(
        pipe,
        sources=[
            _bs("notes.txt", b"Also need excavator"),
            _bs("fleet.csv", b"type,qty\nExcavator,1\n"),
        ],
    )
    assert out["data_kind"] == "mixed"
    assert out["structured_count"] == 1
    assert out["unstructured_count"] == 1
    assert out["documents_written"] >= 2
