"""Phase 5 / S5-I0: DocumentStore factory + INDEXING_DOCUMENT_STORE flag."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.config import Settings
from app.pipelines.indexing.document_store import (
    PGVECTOR_TABLE_NAME,
    build_document_store,
    create_session_document_store,
    embedding_dimension_mismatch_message,
    get_document_store,
    normalize_document_store_mode,
    parse_pgvector_type,
    reset_document_store,
)


def test_normalize_mode_default_memory() -> None:
    assert normalize_document_store_mode(None) == "memory"
    assert normalize_document_store_mode("memory") == "memory"
    assert normalize_document_store_mode("MEMORY") == "memory"
    assert normalize_document_store_mode("  Memory  ") == "memory"


def test_normalize_mode_pgvector() -> None:
    assert normalize_document_store_mode("pgvector") == "pgvector"
    assert normalize_document_store_mode(" Pgvector ") == "pgvector"
    assert normalize_document_store_mode("PGVECTOR") == "pgvector"


def test_normalize_mode_invalid() -> None:
    with pytest.raises(ValueError, match="unsupported INDEXING_DOCUMENT_STORE"):
        normalize_document_store_mode("redis")
    with pytest.raises(ValueError, match="unsupported INDEXING_DOCUMENT_STORE"):
        normalize_document_store_mode("")
    with pytest.raises(ValueError, match="unsupported INDEXING_DOCUMENT_STORE"):
        normalize_document_store_mode("   ")


def test_build_document_store_default_memory() -> None:
    store = build_document_store(settings=Settings(indexing_document_store="memory"))
    assert isinstance(store, InMemoryDocumentStore)


def test_build_document_store_explicit_memory() -> None:
    store = build_document_store(mode="memory")
    assert isinstance(store, InMemoryDocumentStore)


def test_build_document_store_settings_default_is_memory() -> None:
    settings = Settings()
    assert settings.indexing_document_store == "memory"
    store = build_document_store(settings=settings)
    assert isinstance(store, InMemoryDocumentStore)


def test_build_document_store_invalid_mode() -> None:
    with pytest.raises(ValueError, match="unsupported INDEXING_DOCUMENT_STORE"):
        build_document_store(mode="elasticsearch")


def test_build_document_store_pgvector_mocked() -> None:
    """pgvector branch constructs PgvectorDocumentStore without live Postgres."""
    fake_cls = MagicMock(name="PgvectorDocumentStore")
    fake_instance = MagicMock(name="pgvector_store")
    fake_cls.return_value = fake_instance

    with patch.dict(
        "sys.modules",
        {
            "haystack_integrations.document_stores.pgvector": MagicMock(
                PgvectorDocumentStore=fake_cls
            ),
        },
    ):
        # Re-import path: patch the import target used inside the factory
        with patch(
            "haystack_integrations.document_stores.pgvector.PgvectorDocumentStore",
            fake_cls,
            create=True,
        ):
            store = build_document_store(
                mode="pgvector",
                settings=Settings(
                    indexing_document_store="pgvector",
                    indexing_embedding_dim=384,
                    database_url_override=(
                        "postgresql+psycopg://user:pass@host:5432/heavy_rental"
                    ),
                ),
            )

    assert store is fake_instance
    assert fake_cls.call_count == 1
    kwargs = fake_cls.call_args.kwargs
    assert kwargs["embedding_dimension"] == 384
    assert kwargs["recreate_table"] is False
    assert kwargs["table_name"] == PGVECTOR_TABLE_NAME
    # connection_string is a Haystack Secret; resolve token if available
    secret = kwargs["connection_string"]
    resolved = secret.resolve_value() if hasattr(secret, "resolve_value") else str(secret)
    assert "postgresql://" in resolved
    assert "user:pass@host:5432/heavy_rental" in resolved
    assert "+psycopg" not in resolved


def test_build_document_store_pgvector_import_error() -> None:
    real_import = __import__

    def _block_pgvector(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "haystack_integrations.document_stores.pgvector" or (
            name == "haystack_integrations.document_stores"
            and kwargs.get("fromlist")
            and "pgvector" in str(kwargs.get("fromlist"))
        ):
            raise ImportError("simulated missing pgvector-haystack")
        if name.startswith("haystack_integrations"):
            # Let parent packages fail only for the pgvector leaf
            try:
                return real_import(name, *args, **kwargs)  # type: ignore[arg-type]
            except ImportError:
                if "pgvector" in name:
                    raise ImportError("simulated missing pgvector-haystack")
                raise
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    with patch("builtins.__import__", side_effect=_block_pgvector):
        with pytest.raises(ImportError, match="pgvector-haystack"):
            build_document_store(
                mode="pgvector",
                settings=Settings(indexing_document_store="pgvector"),
            )


def test_build_document_store_pgvector_empty_connection() -> None:
    with patch(
        "app.pipelines.indexing.document_store._connection_string_for_pgvector",
        side_effect=ValueError(
            "pgvector DocumentStore requires a non-empty connection string"
        ),
    ):
        with pytest.raises(ValueError, match="connection string"):
            build_document_store(
                mode="pgvector",
                connection_string="",
                settings=Settings(indexing_document_store="pgvector"),
            )


def test_get_document_store_stays_inmemory_singleton() -> None:
    """Singleton helpers remain process-local InMemory (I0 does not switch them)."""
    reset_document_store()
    a = get_document_store()
    b = get_document_store()
    assert a is b
    assert isinstance(a, InMemoryDocumentStore)


def test_create_session_document_store_memory_is_fresh() -> None:
    """I1 memory mode: each session store is a new InMemory instance."""
    settings = Settings(indexing_document_store="memory")
    a = create_session_document_store(settings=settings)
    b = create_session_document_store(settings=settings)
    assert isinstance(a, InMemoryDocumentStore)
    assert isinstance(b, InMemoryDocumentStore)
    assert a is not b


def test_parse_pgvector_type() -> None:
    assert parse_pgvector_type("vector(384)") == 384
    assert parse_pgvector_type("vector(768)") == 768
    assert parse_pgvector_type("public.vector(768)") == 768
    assert parse_pgvector_type("text") is None
    assert parse_pgvector_type("") is None


def test_embedding_dimension_mismatch_message_mentions_override() -> None:
    msg = embedding_dimension_mismatch_message(existing=384, configured=768)
    assert "vector(384)" in msg
    assert "INDEXING_EMBEDDING_DIM=768" in msg
    assert "INDEXING_EMBEDDING_DIM=384" in msg
    assert PGVECTOR_TABLE_NAME in msg


def test_build_document_store_pgvector_rejects_column_dim_mismatch() -> None:
    fake_cls = MagicMock(name="PgvectorDocumentStore")
    with (
        patch(
            "haystack_integrations.document_stores.pgvector.PgvectorDocumentStore",
            fake_cls,
            create=True,
        ),
        patch(
            "app.pipelines.indexing.document_store.existing_pgvector_embedding_dim",
            return_value=384,
        ),
    ):
        with pytest.raises(ValueError, match="vector\\(384\\)"):
            build_document_store(
                mode="pgvector",
                settings=Settings(
                    indexing_document_store="pgvector",
                    indexing_embedding_dim=768,
                    database_url_override=(
                        "postgresql+psycopg://user:pass@host:5432/heavy_rental"
                    ),
                ),
            )
    fake_cls.assert_not_called()


def test_build_document_store_pgvector_uses_stable_table() -> None:
    fake_cls = MagicMock(name="PgvectorDocumentStore")
    fake_instance = MagicMock(name="pgvector_store")
    fake_cls.return_value = fake_instance
    with patch(
        "haystack_integrations.document_stores.pgvector.PgvectorDocumentStore",
        fake_cls,
        create=True,
    ):
        build_document_store(
            mode="pgvector",
            settings=Settings(
                indexing_document_store="pgvector",
                indexing_embedding_dim=384,
                database_url_override=(
                    "postgresql+psycopg://user:pass@host:5432/heavy_rental"
                ),
            ),
        )
    assert fake_cls.call_args.kwargs["table_name"] == PGVECTOR_TABLE_NAME
