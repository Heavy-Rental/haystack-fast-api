"""Project-spec indexing + mandatory post-join knowledge graph (HR-76).

After a successful index write + KG-1 build, registers a
``ProjectKnowledgeSession`` so Stage-1 multi-agent tools can address both
the ingest-scoped ``InMemoryDocumentStore`` and the project knowledge graph.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from haystack import Pipeline
from haystack.dataclasses import ByteStream, Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.config import get_settings
from app.core.exceptions import BadRequestError
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.mime_map import MIME_TEXT_PLAIN, guess_mime_from_filename
from app.pipelines.indexing.pipeline import build_indexing_pipeline, run_indexing_pipeline
from app.schemas.indexing import IngestFromProjectSpecResponse
from app.services.project_knowledge_session import (
    ProjectKnowledgeSession,
    get_project_knowledge_registry,
)

logger = logging.getLogger(__name__)

USER_REQUIREMENT_SUMMARY_MAX_CHARS = 1000


def byte_stream_from_upload(
    *,
    raw: bytes,
    filename: str | None,
    content_type: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    ingest_id: str | None = None,
) -> ByteStream:
    """Package upload bytes as a ByteStream with MIME from extension (preferred)."""
    if not raw:
        raise BadRequestError("uploaded file is empty")

    name = (filename or "upload").strip() or "upload"
    mime = guess_mime_from_filename(name)
    if mime is None and content_type:
        mime = content_type.split(";")[0].strip() or None

    meta: dict[str, Any] = {"file_path": name, "filename": name}
    if user_id:
        meta["user_id"] = user_id
    if user_name:
        meta["user_name"] = user_name
    if ingest_id:
        meta["ingest_id"] = ingest_id

    return ByteStream(data=raw, meta=meta, mime_type=mime)


def byte_stream_from_project_text(
    project_text: str,
    *,
    user_id: str | None = None,
    user_name: str | None = None,
    ingest_id: str | None = None,
) -> ByteStream:
    """Treat free-text as unstructured plain text."""
    text = project_text.strip()
    if not text:
        raise BadRequestError("project_text must not be empty")
    data = text.encode("utf-8")
    meta: dict[str, Any] = {
        "file_path": "project_text.txt",
        "filename": "project_text.txt",
    }
    if user_id:
        meta["user_id"] = user_id
    if user_name:
        meta["user_name"] = user_name
    if ingest_id:
        meta["ingest_id"] = ingest_id
    return ByteStream(data=data, meta=meta, mime_type=MIME_TEXT_PLAIN)


def _stamp_documents(
    documents: list[Document],
    *,
    user_id: str,
    user_name: str | None,
    ingest_id: str,
) -> list[Document]:
    stamped: list[Document] = []
    for doc in documents:
        meta = dict(doc.meta or {})
        meta["user_id"] = user_id
        meta["ingest_id"] = ingest_id
        if user_name:
            meta["user_name"] = user_name
        stamped.append(replace(doc, meta=meta))
    return stamped


def _normalize_requirement_text(text: str) -> str:
    """Collapse whitespace for a stable client-facing summary string."""
    lines = [" ".join(line.split()) for line in text.replace("\r\n", "\n").split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def _build_user_requirement_summary(
    text: str,
    *,
    max_chars: int = USER_REQUIREMENT_SUMMARY_MAX_CHARS,
) -> tuple[str, list[str]]:
    """Deterministic summary from project_text or extracted document content."""
    warnings: list[str] = []
    normalized = _normalize_requirement_text(text or "")
    if not normalized:
        warnings.append("user_requirement_summary empty after extraction")
        return "", warnings
    if len(normalized) <= max_chars:
        return normalized, warnings
    truncated = normalized[: max_chars - 1].rstrip() + "…"
    warnings.append("user_requirement_summary truncated")
    return truncated, warnings


def _extract_text_from_documents(documents: list[Document]) -> str:
    parts: list[str] = []
    for doc in documents:
        content = (doc.content or "").strip()
        if content:
            parts.append(content)
    return "\n\n".join(parts)


def _build_pipeline_for_store(document_store: InMemoryDocumentStore) -> Pipeline:
    settings = get_settings()
    mode = str(settings.indexing_embedder or "mock").strip().lower()
    if mode not in {"mock", "openai", "sentence-transformers", "st", "minilm"}:
        mode = "mock"
    embedder = build_document_embedder(
        mode=mode,
        dimension=int(settings.indexing_embedding_dim),
        openai_api_key=settings.llm_api_key,
        openai_model=settings.indexing_openai_embedding_model,
        openai_base_url=settings.llm_base_url if mode == "openai" else None,
        sentence_transformers_model=settings.indexing_st_model,
    )
    return build_indexing_pipeline(
        document_store=document_store,
        embedder=embedder,
        split_length=int(settings.indexing_split_length),
        split_overlap=int(settings.indexing_split_overlap),
    )


def _document_store_from_pipeline(pipeline: Pipeline) -> InMemoryDocumentStore | None:
    """Best-effort extract of the writer-backed store (test pipelines)."""
    try:
        writer = pipeline.get_component("writer")
    except Exception:  # noqa: BLE001
        return None
    store = getattr(writer, "document_store", None)
    return store if isinstance(store, InMemoryDocumentStore) else None


class IndexingIngestService:
    """Index project-spec sources; always build KG after final_doc_joiner chunks."""

    def __init__(
        self,
        *,
        pipeline: Pipeline | None = None,
        document_store: InMemoryDocumentStore | None = None,
    ) -> None:
        # Prefer an explicit pipeline (tests). Otherwise build per-ingest store.
        self._pipeline = pipeline
        self._document_store = document_store

    def ingest_from_project_spec(
        self,
        *,
        user_id: str,
        user_name: str | None = None,
        project_text: str | None = None,
        file_sources: list[ByteStream] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> IngestFromProjectSpecResponse:
        uid = (user_id or "").strip()
        if not uid:
            raise BadRequestError("user_id is required")
        uname = user_name.strip() if isinstance(user_name, str) and user_name.strip() else None
        ingest_id = f"ing_{uuid.uuid4().hex}"

        # Per-ingest DocumentStore for multi-user isolation (Stage 1 multi-agent).
        # When tests inject a pipeline, reuse its writer store so registry matches writes.
        if self._document_store is not None:
            session_store = self._document_store
            pipeline = self._pipeline or _build_pipeline_for_store(session_store)
        elif self._pipeline is not None:
            pipeline = self._pipeline
            session_store = (
                _document_store_from_pipeline(pipeline) or InMemoryDocumentStore()
            )
        else:
            session_store = InMemoryDocumentStore()
            pipeline = _build_pipeline_for_store(session_store)

        sources: list[ByteStream | str | Path] = []
        if file_sources:
            for src in file_sources:
                meta = dict(src.meta or {})
                meta["user_id"] = uid
                meta["ingest_id"] = ingest_id
                if uname:
                    meta["user_name"] = uname
                sources.append(
                    ByteStream(data=src.data, meta=meta, mime_type=src.mime_type)
                )
        if project_text is not None and str(project_text).strip():
            sources.append(
                byte_stream_from_project_text(
                    str(project_text),
                    user_id=uid,
                    user_name=uname,
                    ingest_id=ingest_id,
                )
            )

        if not sources:
            raise BadRequestError(
                "project_text or file must provide at least one non-empty source"
            )

        out = run_indexing_pipeline(pipeline, sources=sources)

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

        # Embedded chunks for store previews; joiner output is KG input (post-split).
        embedded_raw = list(out.get("chunk_documents") or out.get("documents") or [])
        joiner_raw = list(
            out.get("final_doc_joiner_documents") or embedded_raw
        )
        embedded_docs = _stamp_documents(
            [d for d in embedded_raw if isinstance(d, Document)],
            user_id=uid,
            user_name=uname,
            ingest_id=ingest_id,
        )
        joiner_docs = _stamp_documents(
            [d for d in joiner_raw if isinstance(d, Document)],
            user_id=uid,
            user_name=uname,
            ingest_id=ingest_id,
        )
        chunk_count = int(out.get("chunk_count") or len(embedded_docs) or len(joiner_docs))
        documents_written = int(out.get("documents_written") or 0)

        if chunk_count == 0 or documents_written == 0:
            raise BadRequestError(
                "indexing produced no writable chunks after clean/split/embed"
            )

        public_warnings = list(conversion_warnings)

        settings = get_settings()
        from app.pipelines.kg.runner import run_knowledge_graph

        # Mandatory KG: post-final_doc_joiner chunks; full Ragas transforms only in generator.
        try:
            kg_result = run_knowledge_graph(
                joiner_docs or embedded_docs,
                user_id=uid,
                ingest_id=ingest_id,
                artifact_dir=settings.kg_artifact_dir,
                apply_transforms=bool(settings.kg_apply_transforms),
            )
        except BadRequestError:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = f"knowledge graph step failed: {exc}"
            logger.warning(msg)
            raise BadRequestError(msg) from exc

        if not kg_result.kg_built:
            raise BadRequestError(
                "; ".join(kg_result.warnings) or "knowledge graph build failed"
            )

        kg_built = kg_result.kg_built
        kg_node_count = kg_result.kg_node_count
        kg_relationship_count = kg_result.kg_relationship_count
        kg_artifact_path = kg_result.kg_artifact_path
        kg_transform_applied = kg_result.kg_transform_applied
        # KG soft warnings stay internal/log; hard-fail already handled above.

        # Prefer request project_text; else extracted document content (not raw bytes).
        summary_source = ""
        if project_text is not None and str(project_text).strip():
            summary_source = str(project_text)
        else:
            summary_source = _extract_text_from_documents(
                joiner_docs or embedded_docs
            )
        user_requirement_summary, summary_warnings = _build_user_requirement_summary(
            summary_source
        )
        public_warnings.extend(summary_warnings)

        # Register dual knowledge sources for Stage-1 multi-agent tools.
        get_project_knowledge_registry().put(
            ProjectKnowledgeSession(
                user_id=uid,
                ingest_id=ingest_id,
                document_store=session_store,
                knowledge_graph=kg_result.knowledge_graph,
                kg_artifact_path=kg_artifact_path,
                meta={
                    "user_name": uname,
                    "data_kind": data_kind,
                    "chunk_count": chunk_count,
                    "documents_written": documents_written,
                    "filenames": list(out.get("filenames") or []),
                    "kg_node_count": kg_node_count,
                    "kg_relationship_count": kg_relationship_count,
                    "kg_transform_applied": kg_transform_applied,
                    "user_requirement_summary": user_requirement_summary,
                    "tentative_start_date": (
                        start_date.isoformat() if start_date is not None else None
                    ),
                    "tentative_end_date": (
                        end_date.isoformat() if end_date is not None else None
                    ),
                },
            )
        )

        logger.info(
            "indexing_ingest ingest_id=%s user_id=%s data_kind=%s chunks=%s "
            "written=%s kg_built=%s",
            ingest_id,
            uid,
            data_kind,
            chunk_count,
            documents_written,
            kg_built,
        )

        return IngestFromProjectSpecResponse(
            ingest_id=ingest_id,
            user_id=uid,
            user_requirement_summary=user_requirement_summary,
            tentative_start_date=start_date,
            tentative_end_date=end_date,
            warnings=public_warnings,
        )
