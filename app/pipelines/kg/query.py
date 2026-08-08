"""Query helpers for project Knowledge Graph (KG-1)."""

from __future__ import annotations

import json
from typing import Any


def _node_type_name(node: Any) -> str:
    ntype = getattr(node, "type", None)
    if ntype is None:
        return "unknown"
    return str(getattr(ntype, "name", None) or ntype)


def _node_id(node: Any) -> str:
    return str(getattr(node, "id", None) or id(node))


def _properties_text(props: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in props.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            try:
                parts.append(f"{key}={json.dumps(value, default=str)}")
            except TypeError:
                parts.append(f"{key}={value!s}")
        else:
            parts.append(f"{key}={value}")
    return " ".join(parts)


def _node_blob(node: Any) -> str:
    props = dict(getattr(node, "properties", None) or {})
    page = str(props.get("page_content") or "")
    return f"{page} {_properties_text(props)}".strip().lower()


def _serialize_node(node: Any, *, score: float | None = None) -> dict[str, Any]:
    props = dict(getattr(node, "properties", None) or {})
    page = str(props.get("page_content") or "")
    # Keep payload bounded for tool / API responses
    preview = page[:500] if page else _properties_text(props)[:500]
    slim_props = {
        k: v
        for k, v in props.items()
        if k != "page_content" and not isinstance(v, (dict, list))
    }
    out: dict[str, Any] = {
        "node_id": _node_id(node),
        "node_type": _node_type_name(node),
        "content_preview": preview,
        "properties": slim_props,
    }
    if score is not None:
        out["score"] = score
    return out


def _relationship_endpoints(rel: Any) -> tuple[Any, Any] | None:
    source = getattr(rel, "source", None) or getattr(rel, "source_node", None)
    target = getattr(rel, "target", None) or getattr(rel, "target_node", None)
    if source is None or target is None:
        return None
    return source, target


def query_knowledge_graph(
    knowledge_graph: Any,
    query: str,
    *,
    limit: int = 10,
    include_neighbors: bool = True,
) -> list[dict[str, Any]]:
    """Substring match over node content/properties; optional 1-hop neighbors.

    Works for document-node-only graphs (default ``KG_APPLY_TRANSFORMS=false``)
    and richer graphs after full Ragas transforms.
    """
    text = (query or "").strip().lower()
    if knowledge_graph is None or not text:
        return []

    # Match full phrase and individual tokens (skip very short tokens).
    tokens = [t for t in text.split() if len(t) >= 3]
    if text not in tokens:
        terms = [text, *tokens]
    else:
        terms = tokens or [text]

    nodes = list(getattr(knowledge_graph, "nodes", None) or [])
    scored: list[tuple[float, Any]] = []
    for node in nodes:
        blob = _node_blob(node)
        if not blob:
            continue
        score = 0.0
        for term in terms:
            if term in blob:
                # Phrase match weights higher than single-token hits.
                weight = 3.0 if term == text and " " in text else 1.0
                score += weight * float(blob.count(term))
        if score > 0:
            scored.append((score, node))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[: max(1, int(limit))]

    hits: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for score, node in top:
        serialized = _serialize_node(node, score=score)
        nid = serialized["node_id"]
        if nid in seen_ids:
            continue
        seen_ids.add(nid)

        neighbors: list[dict[str, Any]] = []
        if include_neighbors:
            for rel in list(getattr(knowledge_graph, "relationships", None) or []):
                ends = _relationship_endpoints(rel)
                if ends is None:
                    continue
                source, target = ends
                if _node_id(source) == nid:
                    neighbors.append(_serialize_node(target))
                elif _node_id(target) == nid:
                    neighbors.append(_serialize_node(source))
        if neighbors:
            serialized["neighbors"] = neighbors[:5]
        hits.append(serialized)

    return hits
