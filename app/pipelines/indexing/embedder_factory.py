"""Document embedder factory for the indexing pipeline.

Default: ``MockDocumentEmbedder`` (CI-safe). Optional: OpenAI or
SentenceTransformers (Packt Ch. 4 default model family).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from haystack.components.embedders import MockDocumentEmbedder, OpenAIDocumentEmbedder
from haystack.utils import Secret

EmbedderMode = Literal["mock", "openai", "sentence-transformers"]


class DocumentEmbedder(Protocol):
    """Minimal protocol for pipeline embed components."""

    def run(self, documents: list[Any]) -> dict[str, Any]: ...


def build_document_embedder(
    *,
    mode: EmbedderMode | str = "mock",
    dimension: int = 384,
    model: str = "mock-indexing-embedder",
    openai_api_key: str | None = None,
    openai_model: str = "text-embedding-3-small",
    openai_base_url: str | None = None,
    sentence_transformers_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> Any:
    """Create a document embedder component for the indexing pipeline."""
    normalized = str(mode or "mock").strip().lower()
    if normalized == "mock":
        return MockDocumentEmbedder(
            dimension=dimension,
            model=model,
            progress_bar=False,
        )
    if normalized == "openai":
        kwargs: dict[str, Any] = {
            "model": openai_model,
            "progress_bar": False,
        }
        if openai_api_key:
            kwargs["api_key"] = Secret.from_token(openai_api_key)
        if openai_base_url:
            kwargs["api_base_url"] = openai_base_url
        return OpenAIDocumentEmbedder(**kwargs)
    if normalized in {"sentence-transformers", "st", "minilm"}:
        try:
            from haystack.components.embedders import (  # type: ignore[attr-defined]
                SentenceTransformersDocumentEmbedder,
            )
        except ImportError:
            try:
                from haystack_integrations.components.embedders.sentence_transformers import (  # noqa: E501
                    SentenceTransformersDocumentEmbedder,
                )
            except ImportError as exc:
                raise ImportError(
                    "SentenceTransformersDocumentEmbedder is not available. "
                    "Install sentence-transformers and a Haystack ST integration, "
                    "or use INDEXING_EMBEDDER=mock."
                ) from exc
        return SentenceTransformersDocumentEmbedder(
            model=sentence_transformers_model,
            progress_bar=False,
        )
    raise ValueError(f"unsupported indexing embedder mode: {mode!r}")
