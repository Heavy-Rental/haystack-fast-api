"""Indexing pipeline factory — classify → convert → clean → split → embed → write."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from haystack import Pipeline
from haystack.components.preprocessors import DocumentCleaner, DocumentSplitter
from haystack.components.writers import DocumentWriter
from haystack.dataclasses import ByteStream
from haystack.document_stores.types import DocumentStore, DuplicatePolicy

from app.pipelines.indexing.data_kind_classifier import DataKindClassifier
from app.pipelines.indexing.document_converter import SourceDocumentConverter
from app.pipelines.indexing.document_store import get_document_store
from app.pipelines.indexing.embedder_factory import build_document_embedder


def build_indexing_pipeline(
    *,
    document_store: DocumentStore | None = None,
    embedder: Any | None = None,
    split_by: str = "word",
    split_length: int = 200,
    split_overlap: int = 20,
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.OVERWRITE,
) -> Pipeline:
    """Build the indexing subgraph for Parts 1–3.

    Graph::

        classify → convert → clean → split → embed → write
    """
    store = document_store if document_store is not None else get_document_store()
    doc_embedder = embedder if embedder is not None else build_document_embedder()

    pipeline = Pipeline()
    pipeline.add_component("classify", DataKindClassifier())
    pipeline.add_component("convert", SourceDocumentConverter())
    pipeline.add_component("clean", DocumentCleaner())
    pipeline.add_component(
        "split",
        DocumentSplitter(
            split_by=split_by,  # type: ignore[arg-type]
            split_length=split_length,
            split_overlap=split_overlap,
            skip_empty_documents=True,
        ),
    )
    pipeline.add_component("embed", doc_embedder)
    pipeline.add_component(
        "write",
        DocumentWriter(document_store=store, policy=duplicate_policy),
    )

    pipeline.connect("classify.structured_sources", "convert.structured_sources")
    pipeline.connect("classify.unstructured_sources", "convert.unstructured_sources")
    pipeline.connect("convert.documents", "clean.documents")
    pipeline.connect("clean.documents", "split.documents")
    pipeline.connect("split.documents", "embed.documents")
    pipeline.connect("embed.documents", "write.documents")
    return pipeline


def run_indexing_pipeline(
    pipeline: Pipeline,
    *,
    sources: list[ByteStream | str | Path],
) -> dict[str, Any]:
    """Execute the indexing pipeline; merge classify / convert / split / write outputs."""
    result = pipeline.run(
        {"classify": {"sources": list(sources)}},
        include_outputs_from={"classify", "convert", "split", "embed", "write"},
    )
    classify_out = dict(result.get("classify") or {})
    convert_out = dict(result.get("convert") or {})
    split_out = dict(result.get("split") or {})
    embed_out = dict(result.get("embed") or {})
    write_out = dict(result.get("write") or {})

    # Prefer later-stage document lists for previews (chunked + embedded).
    chunk_documents = list(
        embed_out.get("documents")
        or split_out.get("documents")
        or convert_out.get("documents")
        or []
    )
    documents_written = int(write_out.get("documents_written") or 0)

    merged: dict[str, Any] = {
        **classify_out,
        **convert_out,
        "chunk_documents": chunk_documents,
        "chunk_count": len(chunk_documents),
        "documents_written": documents_written,
        # Keep convert-level documents list for callers that still read "documents".
        "documents": chunk_documents or list(convert_out.get("documents") or []),
    }
    return merged
