"""Minimal document quality gate (Packt Ch. 4 DocumentSanitizer analogue)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from haystack import component
from haystack.dataclasses import Document


@component
class DocumentSanitizer:
    """Drop empty/null-byte documents before clean/split.

    Lightweight stand-in for the book’s custom sanitizer: keeps the pipeline
    shape without external scripts.
    """

    def __init__(self, *, min_content_length: int = 1) -> None:
        self._min_content_length = max(0, int(min_content_length))

    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document] | None = None) -> dict[str, Any]:
        docs = list(documents or [])
        kept: list[Document] = []
        for doc in docs:
            raw = doc.content or ""
            cleaned = raw.replace("\x00", "").strip()
            if len(cleaned) < self._min_content_length:
                continue
            if cleaned != raw:
                kept.append(replace(doc, content=cleaned))
            else:
                kept.append(doc)
        return {"documents": kept}
