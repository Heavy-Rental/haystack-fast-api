"""Project-spec vector retrieval over an ingest-scoped InMemoryDocumentStore."""

from __future__ import annotations

from typing import Any

from haystack import Pipeline
from haystack.components.embedders import (
    MockTextEmbedder,
    OpenAITextEmbedder,
)
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.utils import Secret

from app.pipelines.indexing.embedder_factory import EmbedderMode


def build_text_embedder(
    *,
    mode: EmbedderMode | str = "mock",
    dimension: int = 384,
    model: str = "mock-indexing-embedder",
    openai_api_key: str | None = None,
    openai_model: str = "text-embedding-3-small",
    openai_base_url: str | None = None,
    sentence_transformers_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> Any:
    """Query-side embedder matching ``build_document_embedder`` modes."""
    normalized = str(mode or "mock").strip().lower()
    if normalized == "mock":
        return MockTextEmbedder(dimension=dimension, model=model)
    if normalized == "openai":
        kwargs: dict[str, Any] = {
            "model": openai_model,
            "progress_bar": False,
        }
        if openai_api_key:
            kwargs["api_key"] = Secret.from_token(openai_api_key)
        if openai_base_url:
            kwargs["api_base_url"] = openai_base_url
        return OpenAITextEmbedder(**kwargs)
    if normalized in {"sentence-transformers", "st", "minilm"}:
        try:
            from haystack.components.embedders import (  # type: ignore[attr-defined]
                SentenceTransformersTextEmbedder,
            )
        except ImportError:
            try:
                from haystack_integrations.components.embedders.sentence_transformers import (  # noqa: E501
                    SentenceTransformersTextEmbedder,
                )
            except ImportError as exc:
                raise ImportError(
                    "SentenceTransformersTextEmbedder is not available. "
                    "Install sentence-transformers or use INDEXING_EMBEDDER=mock."
                ) from exc
        return SentenceTransformersTextEmbedder(
            model=sentence_transformers_model,
            progress_bar=False,
        )
    raise ValueError(f"unsupported indexing embedder mode: {mode!r}")


def build_vector_retrieval_pipeline(
    document_store: InMemoryDocumentStore,
    *,
    text_embedder: Any | None = None,
    top_k: int = 5,
    mode: EmbedderMode | str = "mock",
    dimension: int = 384,
    openai_api_key: str | None = None,
    openai_model: str = "text-embedding-3-small",
    openai_base_url: str | None = None,
    sentence_transformers_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> Pipeline:
    """Haystack pipeline: text embedder → InMemoryEmbeddingRetriever."""
    embedder = text_embedder or build_text_embedder(
        mode=mode,
        dimension=dimension,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        openai_base_url=openai_base_url,
        sentence_transformers_model=sentence_transformers_model,
    )
    pipeline = Pipeline()
    pipeline.add_component("text_embedder", embedder)
    pipeline.add_component(
        "retriever",
        InMemoryEmbeddingRetriever(document_store=document_store, top_k=top_k),
    )
    pipeline.connect("text_embedder.embedding", "retriever.query_embedding")
    return pipeline


def run_vector_search(
    document_store: InMemoryDocumentStore,
    query: str,
    *,
    top_k: int = 5,
    pipeline: Pipeline | None = None,
    mode: EmbedderMode | str = "mock",
    dimension: int = 384,
    openai_api_key: str | None = None,
    openai_model: str = "text-embedding-3-small",
    openai_base_url: str | None = None,
    sentence_transformers_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> list[dict[str, Any]]:
    """Execute dense retrieval; return JSON-serializable hits."""
    text = (query or "").strip()
    if not text:
        return []

    pipe = pipeline or build_vector_retrieval_pipeline(
        document_store,
        top_k=top_k,
        mode=mode,
        dimension=dimension,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        openai_base_url=openai_base_url,
        sentence_transformers_model=sentence_transformers_model,
    )
    # Override top_k on existing pipeline retriever when possible
    retriever = pipe.get_component("retriever")
    if hasattr(retriever, "top_k"):
        retriever.top_k = top_k  # type: ignore[attr-defined]

    result = pipe.run({"text_embedder": {"text": text}})
    docs = list((result.get("retriever") or {}).get("documents") or [])
    hits: list[dict[str, Any]] = []
    for doc in docs:
        hits.append(
            {
                "content": doc.content or "",
                "score": float(doc.score) if doc.score is not None else None,
                "meta": dict(doc.meta or {}),
            }
        )
    return hits
