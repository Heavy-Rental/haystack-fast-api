"""Part 2: convert classified ByteStreams into Haystack Documents by MIME type."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import replace
from typing import Any

from haystack import component
from haystack.components.converters import (
    CSVToDocument,
    DOCXToDocument,
    HTMLToDocument,
    MarkdownToDocument,
    PyPDFToDocument,
    TextFileToDocument,
    XLSXToDocument,
)
from haystack.dataclasses import ByteStream, Document

from app.pipelines.indexing.mime_map import (
    MIME_CSV,
    MIME_DOCX,
    MIME_HTML,
    MIME_JSON,
    MIME_MARKDOWN,
    MIME_PDF,
    MIME_TEXT_PLAIN,
    MIME_XLSX,
)

logger = logging.getLogger(__name__)


def _group_by_mime(sources: list[ByteStream]) -> dict[str | None, list[ByteStream]]:
    groups: dict[str | None, list[ByteStream]] = defaultdict(list)
    for src in sources:
        groups[src.mime_type].append(src)
    return groups


def _safe_convert(
    *,
    converter: Any,
    sources: list[ByteStream],
    label: str,
) -> tuple[list[Document], list[str]]:
    if not sources:
        return [], []
    try:
        # MarkdownToDocument accepts progress_bar=False at init; others ignore kwargs.
        out = converter.run(sources=sources)
        docs = list(out.get("documents") or [])
        return docs, []
    except Exception as exc:  # noqa: BLE001 — surface as pipeline warning, not crash
        names = [
            str((s.meta or {}).get("file_path") or (s.meta or {}).get("filename") or "upload")
            for s in sources
        ]
        msg = f"failed to convert {label} ({', '.join(names)}): {exc}"
        logger.warning(msg)
        return [], [msg]


@component
class SourceDocumentConverter:
    """Convert structured and unstructured ByteStreams to Documents.

    MIME → converter map (Part 2)::

        text/plain, application/json → TextFileToDocument
        text/markdown → MarkdownToDocument
        text/html → HTMLToDocument
        application/pdf → PyPDFToDocument
        DOCX → DOCXToDocument
        text/csv → CSVToDocument
        XLSX → XLSXToDocument
    """

    def __init__(self) -> None:
        self._text = TextFileToDocument()
        self._markdown = MarkdownToDocument(progress_bar=False)
        self._html = HTMLToDocument()
        self._pdf = PyPDFToDocument()
        self._docx = DOCXToDocument()
        self._csv = CSVToDocument()
        self._xlsx = XLSXToDocument()

    @component.output_types(
        documents=list[Document],
        structured_documents=list[Document],
        unstructured_documents=list[Document],
        document_count=int,
        structured_document_count=int,
        unstructured_document_count=int,
        conversion_warnings=list[str],
    )
    def run(
        self,
        structured_sources: list[ByteStream] | None = None,
        unstructured_sources: list[ByteStream] | None = None,
    ) -> dict[str, Any]:
        structured_sources = list(structured_sources or [])
        unstructured_sources = list(unstructured_sources or [])
        warnings: list[str] = []

        structured_docs, w1 = self._convert_structured(structured_sources)
        unstructured_docs, w2 = self._convert_unstructured(unstructured_sources)
        warnings.extend(w1)
        warnings.extend(w2)

        documents = structured_docs + unstructured_docs
        return {
            "documents": documents,
            "structured_documents": structured_docs,
            "unstructured_documents": unstructured_docs,
            "document_count": len(documents),
            "structured_document_count": len(structured_docs),
            "unstructured_document_count": len(unstructured_docs),
            "conversion_warnings": warnings,
        }

    def _convert_structured(self, sources: list[ByteStream]) -> tuple[list[Document], list[str]]:
        docs: list[Document] = []
        warnings: list[str] = []
        for mime, group in _group_by_mime(sources).items():
            if mime == MIME_CSV:
                d, w = _safe_convert(converter=self._csv, sources=group, label="csv")
            elif mime == MIME_JSON:
                # Whole-file JSON text is suitable for later chunk/embed.
                d, w = _safe_convert(converter=self._text, sources=group, label="json")
            elif mime == MIME_XLSX:
                d, w = _safe_convert(converter=self._xlsx, sources=group, label="xlsx")
            else:
                names = [str((s.meta or {}).get("file_path") or "upload") for s in group]
                w = [f"no structured converter for mime={mime!r} ({', '.join(names)})"]
                d = []
            docs.extend(self._with_kind_meta(d, data_kind="structured", mime=mime))
            warnings.extend(w)
        return docs, warnings

    def _convert_unstructured(self, sources: list[ByteStream]) -> tuple[list[Document], list[str]]:
        docs: list[Document] = []
        warnings: list[str] = []
        for mime, group in _group_by_mime(sources).items():
            if mime in {MIME_TEXT_PLAIN, None}:
                d, w = _safe_convert(converter=self._text, sources=group, label="text")
            elif mime == MIME_MARKDOWN:
                d, w = _safe_convert(converter=self._markdown, sources=group, label="markdown")
            elif mime == MIME_HTML:
                d, w = _safe_convert(converter=self._html, sources=group, label="html")
            elif mime == MIME_PDF:
                d, w = _safe_convert(converter=self._pdf, sources=group, label="pdf")
            elif mime == MIME_DOCX:
                d, w = _safe_convert(converter=self._docx, sources=group, label="docx")
            else:
                names = [str((s.meta or {}).get("file_path") or "upload") for s in group]
                w = [f"no unstructured converter for mime={mime!r} ({', '.join(names)})"]
                d = []
            docs.extend(self._with_kind_meta(d, data_kind="unstructured", mime=mime))
            warnings.extend(w)
        return docs, warnings

    @staticmethod
    def _with_kind_meta(
        documents: list[Document],
        *,
        data_kind: str,
        mime: str | None,
    ) -> list[Document]:
        enriched: list[Document] = []
        for doc in documents:
            meta = dict(doc.meta or {})
            meta.setdefault("data_kind", data_kind)
            if mime:
                meta.setdefault("mime_type", mime)
            enriched.append(replace(doc, meta=meta))
        return enriched
