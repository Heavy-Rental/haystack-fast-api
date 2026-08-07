"""Bridge Haystack Documents → LangChain Documents (Ch. 5 pattern)."""

from __future__ import annotations

from typing import Any

from haystack import component
from haystack.dataclasses import Document


@component
class DocumentToLangChainConverter:
    """Convert Haystack Documents to LangChain-style dicts / objects."""

    @component.output_types(langchain_documents=list)
    def run(self, documents: list[Document] | None = None) -> dict[str, Any]:
        docs = list(documents or [])
        try:
            from langchain_core.documents import Document as LCDocument
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "langchain-core is required for DocumentToLangChainConverter"
            ) from exc

        out: list[Any] = []
        for doc in docs:
            meta = dict(doc.meta or {})
            out.append(
                LCDocument(
                    page_content=doc.content or "",
                    metadata=meta,
                )
            )
        return {"langchain_documents": out}
