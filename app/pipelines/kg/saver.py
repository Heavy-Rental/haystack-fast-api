"""Persist Ragas KnowledgeGraph JSON under a user-scoped path."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from haystack import component


def safe_user_path_segment(user_id: str) -> str:
    text = (user_id or "").strip() or "unknown"
    return re.sub(r"[^a-zA-Z0-9._-]", "_", text)[:128]


@component
class KnowledgeGraphSaver:
    """Write graph JSON to ``{artifact_dir}/{user_id}/kg_{ingest_id}.json``."""

    def __init__(self, *, artifact_dir: str = "artifacts/kg") -> None:
        self._artifact_dir = artifact_dir

    @component.output_types(artifact_path=str, node_count=int, relationship_count=int)
    def run(
        self,
        knowledge_graph: Any,
        *,
        user_id: str = "unknown",
        ingest_id: str = "ing_unknown",
    ) -> dict[str, Any]:
        if knowledge_graph is None:
            raise ValueError("knowledge_graph is required")

        root = Path(self._artifact_dir)
        user_dir = root / safe_user_path_segment(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        safe_ingest = re.sub(r"[^a-zA-Z0-9._-]", "_", ingest_id or "ing_unknown")
        path = user_dir / f"kg_{safe_ingest}.json"
        knowledge_graph.save(path)

        node_count = len(getattr(knowledge_graph, "nodes", []) or [])
        rel_count = len(getattr(knowledge_graph, "relationships", []) or [])
        return {
            "artifact_path": str(path),
            "node_count": node_count,
            "relationship_count": rel_count,
        }
