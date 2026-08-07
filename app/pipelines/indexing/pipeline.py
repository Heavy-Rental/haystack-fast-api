"""Indexing pipeline — Packt Ch. 4 style dual-branch graph.

Reference:
  https://github.com/PacktPublishing/Building-Natural-Language-and-LLM-Pipelines
  ch4 indexing_pipeline (FileTypeRouter → convert branches → join → embed → write)

Graph::

    file_type_router
         ├─ unstructured MIME → converters → unstructured_joiner
         │       → sanitizer → text_cleaner → text_splitter ─┐
         ├─ text/csv → csv_converter → csv_cleaner → csv_splitter ─┤
         └─ (json/xlsx convert into unstructured joiner for clean/split)
                                                              ▼
                                                       final_doc_joiner
                                                              │
                                                         doc_embedder
                                                              │
                                                           writer
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from haystack import Pipeline
from haystack.components.converters import (
    CSVToDocument,
    DOCXToDocument,
    HTMLToDocument,
    MarkdownToDocument,
    PyPDFToDocument,
    TextFileToDocument,
    XLSXToDocument,
)
from haystack.components.joiners import DocumentJoiner
from haystack.components.preprocessors import (
    CSVDocumentCleaner,
    CSVDocumentSplitter,
    DocumentCleaner,
    DocumentSplitter,
)
from haystack.components.routers import FileTypeRouter
from haystack.components.writers import DocumentWriter
from haystack.dataclasses import ByteStream
from haystack.document_stores.types import DocumentStore, DuplicatePolicy

from app.pipelines.indexing.document_sanitizer import DocumentSanitizer
from app.pipelines.indexing.document_store import get_document_store
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.mime_map import (
    ADDITIONAL_MIMETYPES,
    ALL_ROUTED_MIME_TYPES,
    MIME_CSV,
    MIME_DOCX,
    MIME_HTML,
    MIME_JSON,
    MIME_MARKDOWN,
    MIME_PDF,
    MIME_TEXT_PLAIN,
    MIME_XLSX,
    STRUCTURED_MIME_TYPES,
    UNSTRUCTURED_MIME_TYPES,
    data_kind_for_mime,
)


def _source_filename(source: Any) -> str:
    if isinstance(source, ByteStream):
        meta = source.meta or {}
        name = meta.get("file_path") or meta.get("filename") or ""
        return str(name) if name else "upload"
    if isinstance(source, (str, Path)):
        return Path(source).name
    return "upload"


def summarize_router_output(router_out: dict[str, Any]) -> dict[str, Any]:
    """Derive data_kind / counts / filenames from FileTypeRouter outputs."""
    structured_count = 0
    unstructured_count = 0
    unclassified: list[Any] = []
    mime_types_seen: list[str] = []
    filenames: list[str] = []

    for key, items in (router_out or {}).items():
        bucket = list(items or [])
        if not bucket:
            continue
        if key in {"unclassified", "failed"}:
            for src in bucket:
                unclassified.append(src)
                filenames.append(_source_filename(src))
            continue

        if key not in mime_types_seen:
            mime_types_seen.append(key)

        kind = data_kind_for_mime(key)
        for src in bucket:
            filenames.append(_source_filename(src))
            if kind == "structured":
                structured_count += 1
            elif kind == "unstructured":
                unstructured_count += 1
            else:
                unclassified.append(src)

    unclassified_count = len(unclassified)
    if structured_count and unstructured_count:
        data_kind = "mixed"
    elif structured_count:
        data_kind = "structured"
    elif unstructured_count:
        data_kind = "unstructured"
    else:
        data_kind = "unclassified"

    return {
        "data_kind": data_kind,
        "structured_count": structured_count,
        "unstructured_count": unstructured_count,
        "unclassified_count": unclassified_count,
        "mime_types_seen": mime_types_seen,
        "filenames": filenames,
        "structured_sources": [],  # filled only for API parity; sources live in router
        "unstructured_sources": [],
        "unclassified_sources": unclassified,
    }


def build_indexing_pipeline(
    *,
    document_store: DocumentStore | None = None,
    embedder: Any | None = None,
    split_by: str = "word",
    split_length: int = 200,
    split_overlap: int = 20,
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.OVERWRITE,
) -> Pipeline:
    """Build Packt Ch. 4–aligned indexing pipeline with dual preprocess branches."""
    store = document_store if document_store is not None else get_document_store()
    doc_embedder = embedder if embedder is not None else build_document_embedder()

    pipeline = Pipeline()

    # --- Router ---
    pipeline.add_component(
        "file_type_router",
        FileTypeRouter(
            mime_types=list(ALL_ROUTED_MIME_TYPES),
            additional_mimetypes=dict(ADDITIONAL_MIMETYPES),
        ),
    )

    # --- Unstructured converters ---
    pipeline.add_component("text_converter", TextFileToDocument())
    pipeline.add_component("md_converter", MarkdownToDocument(progress_bar=False))
    pipeline.add_component("pdf_converter", PyPDFToDocument())
    pipeline.add_component("html_converter", HTMLToDocument())
    pipeline.add_component("docx_converter", DOCXToDocument())
    # JSON whole-file text (structured kind for API; text preprocess path)
    pipeline.add_component("json_converter", TextFileToDocument())
    pipeline.add_component("xlsx_converter", XLSXToDocument())

    pipeline.add_component(
        "unstructured_doc_joiner",
        DocumentJoiner(join_mode="concatenate", sort_by_score=False),
    )
    pipeline.add_component("sanitizer", DocumentSanitizer())
    pipeline.add_component("text_cleaner", DocumentCleaner())
    pipeline.add_component(
        "text_splitter",
        DocumentSplitter(
            split_by=split_by,  # type: ignore[arg-type]
            split_length=split_length,
            split_overlap=split_overlap,
            skip_empty_documents=True,
        ),
    )

    # --- Structured CSV branch (Packt) ---
    pipeline.add_component("csv_converter", CSVToDocument())
    pipeline.add_component("csv_cleaner", CSVDocumentCleaner())
    pipeline.add_component(
        "csv_splitter",
        CSVDocumentSplitter(split_mode="row-wise"),
    )

    # --- Shared embed + write ---
    pipeline.add_component(
        "final_doc_joiner",
        DocumentJoiner(join_mode="concatenate", sort_by_score=False),
    )
    pipeline.add_component("doc_embedder", doc_embedder)
    pipeline.add_component(
        "writer",
        DocumentWriter(document_store=store, policy=duplicate_policy),
    )

    # Router → converters
    pipeline.connect(f"file_type_router.{MIME_TEXT_PLAIN}", "text_converter.sources")
    pipeline.connect(f"file_type_router.{MIME_MARKDOWN}", "md_converter.sources")
    pipeline.connect(f"file_type_router.{MIME_PDF}", "pdf_converter.sources")
    pipeline.connect(f"file_type_router.{MIME_HTML}", "html_converter.sources")
    pipeline.connect(f"file_type_router.{MIME_DOCX}", "docx_converter.sources")
    pipeline.connect(f"file_type_router.{MIME_JSON}", "json_converter.sources")
    pipeline.connect(f"file_type_router.{MIME_XLSX}", "xlsx_converter.sources")
    pipeline.connect(f"file_type_router.{MIME_CSV}", "csv_converter.sources")

    # Unstructured (+ json/xlsx) → joiner → sanitizer → clean → split
    for conv in (
        "text_converter",
        "md_converter",
        "pdf_converter",
        "html_converter",
        "docx_converter",
        "json_converter",
        "xlsx_converter",
    ):
        pipeline.connect(f"{conv}.documents", "unstructured_doc_joiner.documents")

    pipeline.connect("unstructured_doc_joiner.documents", "sanitizer.documents")
    pipeline.connect("sanitizer.documents", "text_cleaner.documents")
    pipeline.connect("text_cleaner.documents", "text_splitter.documents")
    pipeline.connect("text_splitter.documents", "final_doc_joiner.documents")

    # CSV branch → final joiner
    pipeline.connect("csv_converter.documents", "csv_cleaner.documents")
    pipeline.connect("csv_cleaner.documents", "csv_splitter.documents")
    pipeline.connect("csv_splitter.documents", "final_doc_joiner.documents")

    pipeline.connect("final_doc_joiner.documents", "doc_embedder.documents")
    pipeline.connect("doc_embedder.documents", "writer.documents")

    return pipeline


def run_indexing_pipeline(
    pipeline: Pipeline,
    *,
    sources: list[ByteStream | str | Path],
) -> dict[str, Any]:
    """Execute the indexing pipeline; merge router metadata + write outputs."""
    result = pipeline.run(
        {"file_type_router": {"sources": list(sources)}},
        include_outputs_from={
            "file_type_router",
            "unstructured_doc_joiner",
            "csv_converter",
            "csv_splitter",
            "text_splitter",
            "final_doc_joiner",
            "doc_embedder",
            "writer",
        },
    )

    router_out = dict(result.get("file_type_router") or {})
    summary = summarize_router_output(router_out)

    # Convert-stage counts: one logical document unit per classified source
    # (CSV may expand to many chunks later via row-wise splitter).
    structured_document_count = int(summary["structured_count"])
    unstructured_document_count = int(summary["unstructured_count"])
    convert_document_count = structured_document_count + unstructured_document_count

    embed_out = dict(result.get("doc_embedder") or {})
    final_out = dict(result.get("final_doc_joiner") or {})
    split_text = dict(result.get("text_splitter") or {})
    split_csv = dict(result.get("csv_splitter") or {})
    write_out = dict(result.get("writer") or {})

    chunk_documents = list(
        embed_out.get("documents")
        or final_out.get("documents")
        or (
            list(split_text.get("documents") or [])
            + list(split_csv.get("documents") or [])
        )
        or []
    )
    documents_written = int(write_out.get("documents_written") or 0)

    return {
        **summary,
        "document_count": convert_document_count,
        "structured_document_count": structured_document_count,
        "unstructured_document_count": unstructured_document_count,
        "conversion_warnings": [],
        "chunk_documents": chunk_documents,
        "chunk_count": len(chunk_documents),
        "documents_written": documents_written,
        "documents": chunk_documents,
        # Expose sets used by tests/tools that still import kind names.
        "UNSTRUCTURED_MIME_TYPES": UNSTRUCTURED_MIME_TYPES,
        "STRUCTURED_MIME_TYPES": STRUCTURED_MIME_TYPES,
    }
