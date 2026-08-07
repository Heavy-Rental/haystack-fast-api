"""Project-spec indexing ingest: classify → convert → clean → split → embed → write."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from haystack import Pipeline
from haystack.dataclasses import ByteStream, Document

from app.config import get_settings
from app.core.exceptions import BadRequestError
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.mime_map import MIME_TEXT_PLAIN, guess_mime_from_filename
from app.pipelines.indexing.pipeline import build_indexing_pipeline, run_indexing_pipeline
from app.schemas.indexing import IngestDocumentPreview, IngestFromProjectSpecResponse

logger = logging.getLogger(__name__)

PART3_WARNING = (
    "Part 3 indexing complete: documents were cleaned, split, embedded, and written "
    "to the process-local InMemoryDocumentStore (swap store for persistence later)."
)
CONTENT_PREVIEW_CHARS = 500


def byte_stream_from_upload(
    *,
    raw: bytes,
    filename: str | None,
    content_type: str | None = None,
) -> ByteStream:
    """Package upload bytes as a ByteStream with MIME from extension (preferred)."""
    if not raw:
        raise BadRequestError("uploaded file is empty")

    name = (filename or "upload").strip() or "upload"
    mime = guess_mime_from_filename(name)
    if mime is None and content_type:
        mime = content_type.split(";")[0].strip() or None

    return ByteStream(
        data=raw,
        meta={"file_path": name, "filename": name},
        mime_type=mime,
    )


def byte_stream_from_project_text(project_text: str) -> ByteStream:
    """Treat free-text as unstructured plain text."""
    text = project_text.strip()
    if not text:
        raise BadRequestError("project_text must not be empty")
    data = text.encode("utf-8")
    return ByteStream(
        data=data,
        meta={"file_path": "project_text.txt", "filename": "project_text.txt"},
        mime_type=MIME_TEXT_PLAIN,
    )


def _document_preview(doc: Document) -> IngestDocumentPreview:
    content = doc.content or ""
    meta = dict(doc.meta or {})
    slim_meta = {
        k: v
        for k, v in meta.items()
        if k
        in {
            "file_path",
            "filename",
            "mime_type",
            "data_kind",
            "source_id",
            "page_number",
            "split_id",
            "split_idx_start",
            "_split_overlap",
        }
        or not isinstance(v, (dict, list))
    }
    embedding = getattr(doc, "embedding", None)
    return IngestDocumentPreview(
        content_preview=content[:CONTENT_PREVIEW_CHARS],
        content_length=len(content),
        meta=slim_meta,
        data_kind=meta.get("data_kind"),
        has_embedding=bool(embedding),
    )


def _build_default_pipeline() -> Pipeline:
    settings = get_settings()
    mode = str(settings.indexing_embedder or "mock").strip().lower()
    if mode not in {"mock", "openai"}:
        mode = "mock"
    embedder = build_document_embedder(
        mode=mode,  # type: ignore[arg-type]
        dimension=int(settings.indexing_embedding_dim),
        openai_api_key=settings.llm_api_key,
        openai_model=settings.indexing_openai_embedding_model,
        openai_base_url=settings.llm_base_url if mode == "openai" else None,
    )
    return build_indexing_pipeline(
        embedder=embedder,
        split_length=int(settings.indexing_split_length),
        split_overlap=int(settings.indexing_split_overlap),
    )


class IndexingIngestService:
    """Run the full indexing pipeline for project-spec sources (Parts 1–3)."""

    def __init__(self, *, pipeline: Pipeline | None = None) -> None:
        self._pipeline = pipeline or _build_default_pipeline()

    def ingest_from_project_spec(
        self,
        *,
        project_text: str | None = None,
        file_sources: list[ByteStream] | None = None,
    ) -> IngestFromProjectSpecResponse:
        sources: list[ByteStream | str | Path] = []
        if file_sources:
            sources.extend(file_sources)
        if project_text is not None and str(project_text).strip():
            sources.append(byte_stream_from_project_text(str(project_text)))

        if not sources:
            raise BadRequestError(
                "project_text or file must provide at least one non-empty source"
            )

        out = run_indexing_pipeline(self._pipeline, sources=sources)

        unclassified_count = int(out.get("unclassified_count") or 0)
        structured_count = int(out.get("structured_count") or 0)
        unstructured_count = int(out.get("unstructured_count") or 0)
        data_kind = str(out.get("data_kind") or "unclassified")

        if unclassified_count > 0:
            names = out.get("filenames") or []
            raise BadRequestError(
                "unsupported or unclassified file type"
                + (f" ({', '.join(str(n) for n in names)})" if names else "")
                + "; supported unstructured: .txt .md .pdf .docx .html; "
                "structured: .csv .json .xlsx"
            )

        if structured_count == 0 and unstructured_count == 0:
            raise BadRequestError(
                "project_text or file must provide at least one classifiable source"
            )

        if data_kind not in {"structured", "unstructured", "mixed"}:
            raise BadRequestError("could not determine structured vs unstructured kind")

        # Convert-stage counts (pre-split).
        structured_document_count = int(out.get("structured_document_count") or 0)
        unstructured_document_count = int(out.get("unstructured_document_count") or 0)
        convert_document_count = int(
            out.get("document_count")
            or (structured_document_count + unstructured_document_count)
        )
        conversion_warnings = list(out.get("conversion_warnings") or [])

        if convert_document_count == 0:
            detail = (
                "; ".join(conversion_warnings) if conversion_warnings else "no content extracted"
            )
            raise BadRequestError(f"file conversion produced no documents: {detail}")

        chunk_documents: list[Any] = list(
            out.get("chunk_documents") or out.get("documents") or []
        )
        chunk_count = int(out.get("chunk_count") or len(chunk_documents))
        documents_written = int(out.get("documents_written") or 0)

        if chunk_count == 0 or documents_written == 0:
            raise BadRequestError(
                "indexing produced no writable chunks after clean/split/embed"
            )

        previews = [
            _document_preview(d)
            if isinstance(d, Document)
            else IngestDocumentPreview(
                content_preview=str(getattr(d, "content", "") or "")[
                    :CONTENT_PREVIEW_CHARS
                ],
                content_length=len(str(getattr(d, "content", "") or "")),
                meta=dict(getattr(d, "meta", None) or {}),
                data_kind=(getattr(d, "meta", None) or {}).get("data_kind")
                if isinstance(getattr(d, "meta", None), dict)
                else None,
                has_embedding=bool(getattr(d, "embedding", None)),
            )
            for d in chunk_documents
        ]

        warnings = [PART3_WARNING, *conversion_warnings]
        ingest_id = f"ing_{uuid.uuid4().hex}"
        logger.info(
            "indexing_ingest ingest_id=%s data_kind=%s convert_docs=%s "
            "chunks=%s written=%s",
            ingest_id,
            data_kind,
            convert_document_count,
            chunk_count,
            documents_written,
        )

        return IngestFromProjectSpecResponse(
            ingest_id=ingest_id,
            data_kind=data_kind,  # type: ignore[arg-type]
            mime_types_seen=list(out.get("mime_types_seen") or []),
            filenames=list(out.get("filenames") or []),
            structured_count=structured_count,
            unstructured_count=unstructured_count,
            document_count=convert_document_count,
            structured_document_count=structured_document_count,
            unstructured_document_count=unstructured_document_count,
            chunk_count=chunk_count,
            documents_written=documents_written,
            documents=previews,
            warnings=warnings,
        )
