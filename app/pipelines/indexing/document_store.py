"""Process-local DocumentStore for the indexing pipeline (Part 3).

Default is Haystack ``InMemoryDocumentStore`` so vectorized chunks can be written
without external infra. Swap via ``build_indexing_pipeline(document_store=...)``
when a persistent store is configured later.
"""

from __future__ import annotations

from haystack.document_stores.in_memory import InMemoryDocumentStore

_document_store: InMemoryDocumentStore | None = None


def get_document_store() -> InMemoryDocumentStore:
    """Return the shared in-memory document store (lazy singleton)."""
    global _document_store
    if _document_store is None:
        _document_store = InMemoryDocumentStore()
    return _document_store


def reset_document_store() -> InMemoryDocumentStore:
    """Replace the shared store (tests / explicit flush)."""
    global _document_store
    _document_store = InMemoryDocumentStore()
    return _document_store
