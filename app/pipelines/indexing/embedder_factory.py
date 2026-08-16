"""Document embedder factory for the indexing pipeline.

Default: ``MockDocumentEmbedder`` (CI-safe). Optional: OpenAI or
SentenceTransformers (Packt Ch. 4 default model family).

``INDEXING_EMBEDDING_DIM`` is the configured vector width for every mode:
requested from OpenAI-compatible hosts when the model allows it, then
enforced on the returned vectors so pgvector / retrieval stay aligned.
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Literal, Protocol

from haystack import component
from haystack.components.embedders import MockDocumentEmbedder, OpenAIDocumentEmbedder
from haystack.dataclasses import Document
from haystack.utils import Secret

EmbedderMode = Literal["mock", "openai", "sentence-transformers"]


class DocumentEmbedder(Protocol):
    """Minimal protocol for pipeline embed components."""

    def run(self, documents: list[Any]) -> dict[str, Any]: ...


def openai_embedding_dimensions(model: str, dimension: int) -> int | None:
    """Return the OpenAI-compatible ``dimensions`` kwarg for this model.

    Most current hosts (``text-embedding-3-*``, Qwen3, GTE, BGE) accept or
    ignore the field. Older OpenAI models (ada-002) reject it, so those stay
    native-width and are resized locally via ``resize_embedding``.
    """
    name = (model or "").strip().lower()
    if "ada-002" in name or name.endswith("-ada") or name == "ada":
        return None
    return int(dimension)


def resize_embedding(vector: Sequence[float], dimension: int) -> list[float]:
    """Force a vector to ``INDEXING_EMBEDDING_DIM``.

    Longer vectors are truncated (Matryoshka-safe for Qwen3 / embedding-3)
    and L2-normalized. Shorter vectors cannot be padded meaningfully.
    """
    dim = int(dimension)
    if dim <= 0:
        raise ValueError(f"INDEXING_EMBEDDING_DIM must be a positive int, got {dimension!r}")
    values = [float(item) for item in vector]
    if len(values) == dim:
        return values
    if len(values) < dim:
        raise ValueError(
            f"embedder returned {len(values)} dimensions, but "
            f"INDEXING_EMBEDDING_DIM={dim}; cannot pad a shorter vector. "
            "Use a model that supports this size or lower the configured dim."
        )
    truncated = values[:dim]
    norm = math.sqrt(sum(item * item for item in truncated))
    if norm > 0.0:
        truncated = [item / norm for item in truncated]
    return truncated


def _forward_warm_up(inner: Any) -> None:
    warm_up = getattr(inner, "warm_up", None)
    if callable(warm_up):
        warm_up()


@component
class DimensionEnforcingDocumentEmbedder:
    """Document embedder that always emits ``dimension``-width vectors."""

    def __init__(self, inner: Any, dimension: int) -> None:
        self._inner = inner
        self.dimension = int(dimension)
        self.dimensions = getattr(inner, "dimensions", None)
        if self.dimensions is None:
            self.dimensions = self.dimension

    def warm_up(self) -> None:
        _forward_warm_up(self._inner)

    @component.output_types(documents=list[Document], meta=dict)
    def run(self, documents: list[Document]) -> dict[str, Any]:
        out = self._inner.run(documents=documents)
        resized: list[Document] = []
        for doc in list(out.get("documents") or []):
            embedding = getattr(doc, "embedding", None)
            if embedding is None:
                resized.append(doc)
                continue
            resized.append(
                replace(doc, embedding=resize_embedding(embedding, self.dimension))
            )
        return {"documents": resized, "meta": dict(out.get("meta") or {})}


@component
class DimensionEnforcingTextEmbedder:
    """Query embedder that always emits ``dimension``-width vectors."""

    def __init__(self, inner: Any, dimension: int) -> None:
        self._inner = inner
        self.dimension = int(dimension)
        self.dimensions = getattr(inner, "dimensions", None)
        if self.dimensions is None:
            self.dimensions = self.dimension

    def warm_up(self) -> None:
        _forward_warm_up(self._inner)

    @component.output_types(embedding=list[float], meta=dict)
    def run(self, text: str) -> dict[str, Any]:
        out = self._inner.run(text=text)
        embedding = out.get("embedding")
        if embedding is not None:
            embedding = resize_embedding(embedding, self.dimension)
        return {
            "embedding": list(embedding or []),
            "meta": dict(out.get("meta") or {}),
        }


def _maybe_st_truncate_kwargs(cls: Any, dimension: int) -> dict[str, Any]:
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return {}
    if "truncate_dim" in params:
        return {"truncate_dim": int(dimension)}
    return {}


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
        inner: Any = MockDocumentEmbedder(
            dimension=dimension,
            model=model,
            progress_bar=False,
        )
        return DimensionEnforcingDocumentEmbedder(inner, dimension)
    if normalized == "openai":
        kwargs: dict[str, Any] = {
            "model": openai_model,
            "progress_bar": False,
        }
        dims = openai_embedding_dimensions(openai_model, dimension)
        if dims is not None:
            kwargs["dimensions"] = dims
        if openai_api_key:
            kwargs["api_key"] = Secret.from_token(openai_api_key)
        if openai_base_url:
            kwargs["api_base_url"] = openai_base_url
        inner = OpenAIDocumentEmbedder(**kwargs)
        return DimensionEnforcingDocumentEmbedder(inner, dimension)
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
        st_kwargs: dict[str, Any] = {
            "model": sentence_transformers_model,
            "progress_bar": False,
        }
        st_kwargs.update(
            _maybe_st_truncate_kwargs(SentenceTransformersDocumentEmbedder, dimension)
        )
        inner = SentenceTransformersDocumentEmbedder(**st_kwargs)
        return DimensionEnforcingDocumentEmbedder(inner, dimension)
    raise ValueError(f"unsupported indexing embedder mode: {mode!r}")
