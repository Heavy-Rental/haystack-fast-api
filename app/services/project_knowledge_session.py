"""Process-local registry of project-spec knowledge sessions (Stage 1).

Each successful ingest registers:
- an ingest-scoped DocumentStore (InMemory per ingest, or shared Pgvector)
- an in-memory Ragas Knowledge Graph (KG-1) + optional JSON artifact path

Sessions are keyed by ``(user_id, ingest_id)`` and can be discarded without
affecting other users or (later) equipment KG-2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.exceptions import NotFoundError


def _session_key(user_id: str, ingest_id: str) -> tuple[str, str]:
    return ((user_id or "").strip(), (ingest_id or "").strip())


@dataclass
class ProjectKnowledgeSession:
    """Runtime handle for project DocumentStore + KG-1 after ingest."""

    user_id: str
    ingest_id: str
    document_store: Any
    knowledge_graph: Any | None = None
    kg_artifact_path: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    meta: dict[str, Any] = field(default_factory=dict)


class ProjectKnowledgeSessionRegistry:
    """Thread-safe process-local session map."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[tuple[str, str], ProjectKnowledgeSession] = {}

    def put(self, session: ProjectKnowledgeSession) -> None:
        key = _session_key(session.user_id, session.ingest_id)
        if not key[0] or not key[1]:
            raise ValueError("user_id and ingest_id are required")
        with self._lock:
            self._sessions[key] = session

    def get(self, user_id: str, ingest_id: str) -> ProjectKnowledgeSession:
        key = _session_key(user_id, ingest_id)
        with self._lock:
            session = self._sessions.get(key)
        if session is None:
            raise NotFoundError(
                f"project knowledge session not found for user_id={user_id!r} "
                f"ingest_id={ingest_id!r}"
            )
        return session

    def delete(self, user_id: str, ingest_id: str) -> bool:
        key = _session_key(user_id, ingest_id)
        with self._lock:
            return self._sessions.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)


_registry: ProjectKnowledgeSessionRegistry | None = None
_registry_lock = RLock()


def get_project_knowledge_registry() -> ProjectKnowledgeSessionRegistry:
    """Return the process-local singleton registry."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = ProjectKnowledgeSessionRegistry()
        return _registry


def reset_project_knowledge_registry() -> ProjectKnowledgeSessionRegistry:
    """Replace the singleton (tests)."""
    global _registry
    with _registry_lock:
        _registry = ProjectKnowledgeSessionRegistry()
        return _registry


def load_knowledge_graph_from_artifact(path: str | Path) -> Any:
    """Load a Ragas KnowledgeGraph from a JSON artifact path."""
    from ragas.testset.graph import KnowledgeGraph

    artifact = Path(path)
    if not artifact.is_file():
        raise NotFoundError(f"knowledge graph artifact not found: {path}")
    return KnowledgeGraph.load(artifact)


def get_or_load_session(
    user_id: str,
    ingest_id: str,
    *,
    kg_artifact_path: str | None = None,
    registry: ProjectKnowledgeSessionRegistry | None = None,
    document_store: Any | None = None,
) -> ProjectKnowledgeSession:
    """Return a live session; optionally hydrate KG from artifact on miss.

    When the process-local session is missing:
    - If ``document_store`` is provided (e.g. reconnected Pgvector), use it.
    - Else if only a KG path is provided, create a session with an empty
      InMemory store and loaded KG (vector hits empty until re-ingest).
    Full dual-source Q&A after process restart on ``memory`` mode requires
    re-ingest; on ``pgvector`` pass a factory store so vectors survive.
    """
    reg = registry if registry is not None else get_project_knowledge_registry()
    try:
        return reg.get(user_id, ingest_id)
    except NotFoundError:
        if not kg_artifact_path and document_store is None:
            raise
        kg = None
        if kg_artifact_path:
            kg = load_knowledge_graph_from_artifact(kg_artifact_path)
        if document_store is None:
            from haystack.document_stores.in_memory import InMemoryDocumentStore

            store: Any = InMemoryDocumentStore()
            meta = {"hydrated_from_artifact": True, "vector_store_empty": True}
        else:
            store = document_store
            meta = {
                "hydrated_from_artifact": bool(kg_artifact_path),
                "vector_store_empty": False,
                "vector_store_reconnected": True,
            }
        session = ProjectKnowledgeSession(
            user_id=user_id,
            ingest_id=ingest_id,
            document_store=store,
            knowledge_graph=kg,
            kg_artifact_path=str(kg_artifact_path) if kg_artifact_path else None,
            meta=meta,
        )
        reg.put(session)
        return session
