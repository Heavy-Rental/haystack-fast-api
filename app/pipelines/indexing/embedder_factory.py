"""Document embedder factory for the indexing pipeline (Part 3).

Default embedder is Haystack ``MockDocumentEmbedder``: deterministic, no network,
CI-safe. Production can switch to OpenAI (or a local ST model later) via settings.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from haystack.components.embedders import MockDocumentEmbedder, OpenAIDocumentEmbedder
from haystack.utils import Secret

EmbedderMode = Literal["mock", "openai"]


class DocumentEmbedder(Protocol):
    """Minimal protocol for pipeline embed components."""

    def run(self, documents: list[Any]) -> dict[str, Any]: ...


def build_document_embedder(
    *,
    mode: EmbedderMode = "mock",
    dimension: int = 384,
    model: str = "mock-indexing-embedder",
    openai_api_key: str | None = None,
    openai_model: str = "text-embedding-3-small",
    openai_base_url: str | None = None,
) -> Any:
    """Create a document embedder component for the indexing pipeline."""
    if mode == "mock":
        return MockDocumentEmbedder(
            dimension=dimension,
            model=model,
            progress_bar=False,
        )
    if mode == "openai":
        kwargs: dict[str, Any] = {
            "model": openai_model,
            "progress_bar": False,
        }
        if openai_api_key:
            kwargs["api_key"] = Secret.from_token(openai_api_key)
        if openai_base_url:
            kwargs["api_base_url"] = openai_base_url
        return OpenAIDocumentEmbedder(**kwargs)
    raise ValueError(f"unsupported indexing embedder mode: {mode!r}")
