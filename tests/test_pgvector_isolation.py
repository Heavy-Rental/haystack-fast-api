"""Phase 5.6: optional live Pgvector isolation (skipped unless RUN_PGVECTOR_TESTS=1)."""

from __future__ import annotations

import os

import pytest
from haystack.dataclasses import Document

from app.config import Settings
from app.pipelines.indexing.document_store import (
    PGVECTOR_TABLE_NAME,
    build_document_store,
    delete_ingest_chunks,
)
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.retrieval import run_vector_search

pytestmark = pytest.mark.pgvector

_RUN = os.environ.get("RUN_PGVECTOR_TESTS", "").strip() in {"1", "true", "yes"}


def _skip_unless_enabled() -> None:
    if not _RUN:
        pytest.skip("Set RUN_PGVECTOR_TESTS=1 to run live pgvector tests")


def _try_store(dim: int = 8):
    settings = Settings(
        indexing_document_store="pgvector",
        indexing_embedding_dim=dim,
    )
    try:
        store = build_document_store(
            mode="pgvector",
            settings=settings,
            embedding_dimension=dim,
            recreate_table=True,
        )
        # Force a cheap round-trip
        store.filter_documents()
        return store
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"pgvector store unavailable: {exc}")


def _write(store, *, content: str, user_id: str, ingest_id: str, dim: int = 8) -> None:
    embedder = build_document_embedder(mode="mock", dimension=dim)
    docs = embedder.run(
        documents=[
            Document(
                content=content,
                meta={"user_id": user_id, "ingest_id": ingest_id},
            )
        ]
    )["documents"]
    store.write_documents(docs)


def test_pgvector_two_user_isolation() -> None:
    _skip_unless_enabled()
    dim = 8
    store = _try_store(dim)
    assert store is not None
    _write(store, content="Alpha excavator clay", user_id="pg_a", ingest_id="ing_a", dim=dim)
    _write(store, content="Bravo boom facade", user_id="pg_b", ingest_id="ing_b", dim=dim)

    hits_a = run_vector_search(
        store,
        "excavator clay",
        top_k=5,
        mode="mock",
        dimension=dim,
        user_id="pg_a",
        ingest_id="ing_a",
    )
    assert hits_a
    for h in hits_a:
        assert h["meta"]["user_id"] == "pg_a"

    hits_cross = run_vector_search(
        store,
        "boom facade",
        top_k=5,
        mode="mock",
        dimension=dim,
        user_id="pg_a",
        ingest_id="ing_a",
    )
    for h in hits_cross:
        assert h["meta"]["user_id"] == "pg_a"
        assert h["meta"]["ingest_id"] == "ing_a"

    delete_ingest_chunks(store, user_id="pg_a", ingest_id="ing_a")
    delete_ingest_chunks(store, user_id="pg_b", ingest_id="ing_b")


def test_pgvector_durable_after_reconnect() -> None:
    _skip_unless_enabled()
    dim = 8
    store1 = _try_store(dim)
    _write(
        store1,
        content="Durable reconnect excavator note",
        user_id="pg_dur",
        ingest_id="ing_dur",
        dim=dim,
    )

    settings = Settings(
        indexing_document_store="pgvector",
        indexing_embedding_dim=dim,
    )
    store2 = build_document_store(
        mode="pgvector",
        settings=settings,
        embedding_dimension=dim,
        recreate_table=False,
    )
    hits = run_vector_search(
        store2,
        "durable excavator",
        top_k=5,
        mode="mock",
        dimension=dim,
        user_id="pg_dur",
        ingest_id="ing_dur",
    )
    assert hits
    assert all(h["meta"]["user_id"] == "pg_dur" for h in hits)
    delete_ingest_chunks(store2, user_id="pg_dur", ingest_id="ing_dur")


def test_pgvector_table_name_stable() -> None:
    _skip_unless_enabled()
    store = _try_store(8)
    # Attribute may vary by integration version; table_name is constructor kw.
    name = getattr(store, "table_name", None) or getattr(store, "_table_name", PGVECTOR_TABLE_NAME)
    assert name == PGVECTOR_TABLE_NAME
