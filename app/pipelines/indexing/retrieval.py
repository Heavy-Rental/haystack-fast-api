"""Project-spec vector retrieval over session DocumentStore (InMemory or Pgvector).

Phase 5 / I1: all retrieval paths MUST filter by ``user_id`` (+ ``ingest_id``)
when those values are provided. Session tools always pass both.
"""

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

from app.pipelines.indexing.embedder_factory import (
    DimensionEnforcingTextEmbedder,
    EmbedderMode,
    _maybe_st_truncate_kwargs,
    openai_embedding_dimensions,
)


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
        inner: Any = MockTextEmbedder(dimension=dimension, model=model)
        return DimensionEnforcingTextEmbedder(inner, dimension)
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
        inner = OpenAITextEmbedder(**kwargs)
        return DimensionEnforcingTextEmbedder(inner, dimension)
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
        st_kwargs: dict[str, Any] = {
            "model": sentence_transformers_model,
            "progress_bar": False,
        }
        st_kwargs.update(
            _maybe_st_truncate_kwargs(SentenceTransformersTextEmbedder, dimension)
        )
        inner = SentenceTransformersTextEmbedder(**st_kwargs)
        return DimensionEnforcingTextEmbedder(inner, dimension)
    raise ValueError(f"unsupported indexing embedder mode: {mode!r}")


def build_tenant_filters(
    *,
    user_id: str | None = None,
    ingest_id: str | None = None,
) -> dict[str, Any] | None:
    """Haystack filter for project-chunk tenant isolation."""
    conditions: list[dict[str, Any]] = []
    uid = (user_id or "").strip()
    iid = (ingest_id or "").strip()
    if uid:
        conditions.append(
            {"field": "meta.user_id", "operator": "==", "value": uid}
        )
    if iid:
        conditions.append(
            {"field": "meta.ingest_id", "operator": "==", "value": iid}
        )
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"operator": "AND", "conditions": conditions}


def _is_pgvector_store(document_store: Any) -> bool:
    cls = type(document_store)
    name = getattr(cls, "__name__", "")
    module = getattr(cls, "__module__", "")
    return name == "PgvectorDocumentStore" or "pgvector" in module


def _build_retriever(
    document_store: Any,
    *,
    top_k: int,
    filters: dict[str, Any] | None,
) -> Any:
    if isinstance(document_store, InMemoryDocumentStore) or not _is_pgvector_store(
        document_store
    ):
        return InMemoryEmbeddingRetriever(
            document_store=document_store,
            top_k=top_k,
            filters=filters,
        )
    from haystack_integrations.components.retrievers.pgvector import (  # type: ignore[import-untyped]
        PgvectorEmbeddingRetriever,
    )

    return PgvectorEmbeddingRetriever(
        document_store=document_store,
        top_k=top_k,
        filters=filters,
    )


def build_vector_retrieval_pipeline(
    document_store: Any,
    *,
    text_embedder: Any | None = None,
    top_k: int = 5,
    mode: EmbedderMode | str = "mock",
    dimension: int = 384,
    openai_api_key: str | None = None,
    openai_model: str = "text-embedding-3-small",
    openai_base_url: str | None = None,
    sentence_transformers_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    user_id: str | None = None,
    ingest_id: str | None = None,
    filters: dict[str, Any] | None = None,
) -> Pipeline:
    """Haystack pipeline: text embedder → store-appropriate embedding retriever."""
    embedder = text_embedder or build_text_embedder(
        mode=mode,
        dimension=dimension,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        openai_base_url=openai_base_url,
        sentence_transformers_model=sentence_transformers_model,
    )
    resolved_filters = (
        filters
        if filters is not None
        else build_tenant_filters(user_id=user_id, ingest_id=ingest_id)
    )
    retriever = _build_retriever(
        document_store, top_k=top_k, filters=resolved_filters
    )
    pipeline = Pipeline()
    pipeline.add_component("text_embedder", embedder)
    pipeline.add_component("retriever", retriever)
    pipeline.connect("text_embedder.embedding", "retriever.query_embedding")
    return pipeline


def _meta_matches_tenant(
    meta: dict[str, Any],
    *,
    user_id: str | None,
    ingest_id: str | None,
) -> bool:
    uid = (user_id or "").strip()
    iid = (ingest_id or "").strip()
    if uid and str(meta.get("user_id") or "").strip() != uid:
        return False
    if iid and str(meta.get("ingest_id") or "").strip() != iid:
        return False
    return True


def run_vector_search(
    document_store: Any,
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
    user_id: str | None = None,
    ingest_id: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Execute dense retrieval; return JSON-serializable hits.

    When ``user_id`` / ``ingest_id`` are set, store filters are applied and a
    post-filter safety net drops any cross-tenant hit.
    """
    text = (query or "").strip()
    if not text:
        return []

    resolved_filters = (
        filters
        if filters is not None
        else build_tenant_filters(user_id=user_id, ingest_id=ingest_id)
    )
    pipe = pipeline or build_vector_retrieval_pipeline(
        document_store,
        top_k=top_k,
        mode=mode,
        dimension=dimension,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        openai_base_url=openai_base_url,
        sentence_transformers_model=sentence_transformers_model,
        filters=resolved_filters,
        user_id=user_id,
        ingest_id=ingest_id,
    )
    # Override top_k / filters on existing pipeline retriever when possible
    retriever = pipe.get_component("retriever")
    if hasattr(retriever, "top_k"):
        retriever.top_k = top_k  # type: ignore[attr-defined]
    if resolved_filters is not None and hasattr(retriever, "filters"):
        retriever.filters = resolved_filters  # type: ignore[attr-defined]

    result = pipe.run({"text_embedder": {"text": text}})
    docs = list((result.get("retriever") or {}).get("documents") or [])
    hits: list[dict[str, Any]] = []
    for doc in docs:
        meta = dict(doc.meta or {})
        if not _meta_matches_tenant(meta, user_id=user_id, ingest_id=ingest_id):
            continue
        hits.append(
            {
                "content": doc.content or "",
                "score": float(doc.score) if doc.score is not None else None,
                "meta": meta,
            }
        )
    return hits
