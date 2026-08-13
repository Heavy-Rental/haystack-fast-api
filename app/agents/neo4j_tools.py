"""In-process Neo4j / KG-2 tools for recommend mode (S7.2 / Phase 7).

Templates only — no free-form Cypher, no MCP server, no live driver.
Fake backend is the default until S8 wires populate + a real client.

Tool names are stable contracts for LangGraph traces and Delegator skip (K-3).
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Stable tool names (Delegator allowlist / traces)
# ---------------------------------------------------------------------------

TOOL_NEO4J_CYPHER_READ = "neo4j_cypher_read"
TOOL_TRIGGER_NEO4J_POPULATE = "trigger_neo4j_populate"

RECOMMEND_NEO4J_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_NEO4J_CYPHER_READ,
        TOOL_TRIGGER_NEO4J_POPULATE,
    }
)

TEMPLATE_ASSET_NEIGHBORS = "asset_neighbors"
TEMPLATE_ASSETS_BY_CATEGORY = "assets_by_category"
TEMPLATE_COMPATIBLE_ATTACHMENTS = "compatible_attachments"

ALLOWED_NEO4J_TEMPLATES: frozenset[str] = frozenset(
    {
        TEMPLATE_ASSET_NEIGHBORS,
        TEMPLATE_ASSETS_BY_CATEGORY,
        TEMPLATE_COMPATIBLE_ATTACHMENTS,
    }
)

TOOL_DESCRIPTIONS: dict[str, str] = {
    TOOL_NEO4J_CYPHER_READ: (
        "Fleet Worker [6]: optional KG-2 neighbor context via allowlisted "
        "templates only. Empty graph returns []. Never invents relationships."
    ),
    TOOL_TRIGGER_NEO4J_POPULATE: (
        "Ops: enqueue a non-blocking KG-2 populate job from Postgres-Haystack. "
        "Does not run on the recommend hot path; never blocks a quote."
    ),
}

_FREEFORM_KEYS = ("cypher", "query", "raw_cypher", "sql", "statement", "raw_sql")


class FreeFormCypherRejected(ValueError):
    """Agents must not pass free-form Cypher to Neo4j tools."""


class UnknownNeo4jTemplateError(ValueError):
    """Template name is not on the Neo4j read allowlist."""


# ---------------------------------------------------------------------------
# Graph backends
# ---------------------------------------------------------------------------


@runtime_checkable
class Neo4jBackend(Protocol):
    """Read-only KG-2 source (fake fixture until S8)."""

    @property
    def is_empty(self) -> bool:
        ...

    def nodes(self) -> list[dict[str, Any]]:
        ...

    def relationships(self) -> list[dict[str, Any]]:
        ...


class FakeNeo4jBackend:
    """In-memory fixture graph (default CI / local). Empty unless injected."""

    def __init__(
        self,
        nodes: list[dict[str, Any]] | None = None,
        relationships: list[dict[str, Any]] | None = None,
    ) -> None:
        self._nodes = deepcopy(nodes) if nodes is not None else []
        self._relationships = (
            deepcopy(relationships) if relationships is not None else []
        )

    @classmethod
    def from_fixture(cls, path: str | Path) -> FakeNeo4jBackend:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            nodes=list(data.get("nodes") or []),
            relationships=list(data.get("relationships") or []),
        )

    @property
    def is_empty(self) -> bool:
        return not self._nodes and not self._relationships

    def nodes(self) -> list[dict[str, Any]]:
        return deepcopy(self._nodes)

    def relationships(self) -> list[dict[str, Any]]:
        return deepcopy(self._relationships)


def _reject_freeform(**kwargs: Any) -> None:
    for key in _FREEFORM_KEYS:
        if key in kwargs and kwargs[key] is not None:
            raise FreeFormCypherRejected(
                f"free-form Cypher/SQL rejected (got {key!r}); "
                "use allowlisted neo4j_cypher_read templates only"
            )


def _node_by_id(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    for node in nodes:
        if str(node.get("id") or "") == node_id:
            return deepcopy(node)
    return None


def _neighbors_of(
    backend: Neo4jBackend,
    asset_id: str,
    *,
    rel_types: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    nodes = backend.nodes()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rel in backend.relationships():
        rel_type = str(rel.get("type") or "")
        if rel_types is not None and rel_type not in rel_types:
            continue
        src = str(rel.get("from") or "")
        dst = str(rel.get("to") or "")
        other = dst if src == asset_id else src if dst == asset_id else ""
        if not other or other in seen:
            continue
        node = _node_by_id(nodes, other)
        if node is None:
            continue
        node["relationship"] = rel_type
        seen.add(other)
        out.append(node)
    return out


def _assets_by_category(backend: Neo4jBackend, category: str) -> list[dict[str, Any]]:
    needle = category.strip().lower()
    hits: list[dict[str, Any]] = []
    for node in backend.nodes():
        if str(node.get("label") or "") != "Asset":
            continue
        if str(node.get("category") or "").strip().lower() != needle:
            continue
        hits.append(deepcopy(node))
    return hits


def neo4j_cypher_read(
    *,
    template: str,
    backend: Neo4jBackend | None = None,
    asset_id: str | None = None,
    category: str | None = None,
    need_id: str | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Run an allowlisted KG-2 template. Empty graph → []."""
    del need_id  # reserved for traces / future template params
    _reject_freeform(**kwargs)
    graph = backend if backend is not None else FakeNeo4jBackend()
    name = str(template or "").strip()
    if name not in ALLOWED_NEO4J_TEMPLATES:
        raise UnknownNeo4jTemplateError(
            f"unknown neo4j template {name!r}; "
            f"allowed={sorted(ALLOWED_NEO4J_TEMPLATES)}"
        )
    if graph.is_empty:
        return []
    if name == TEMPLATE_ASSET_NEIGHBORS:
        return _neighbors_of(graph, str(asset_id or ""))
    if name == TEMPLATE_ASSETS_BY_CATEGORY:
        return _assets_by_category(graph, str(category or ""))
    if name == TEMPLATE_COMPATIBLE_ATTACHMENTS:
        return _neighbors_of(
            graph,
            str(asset_id or ""),
            rel_types=frozenset({"HAS_ATTACHMENT", "COMPATIBLE_WITH"}),
        )
    return []


def trigger_neo4j_populate(
    *,
    backend: Neo4jBackend | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Enqueue a non-blocking KG-2 populate job (no-op until S8)."""
    _reject_freeform(**kwargs)
    graph = backend if backend is not None else FakeNeo4jBackend()
    job_id = f"neo4j_pop_{uuid.uuid4().hex}"
    status = "noop" if graph.is_empty else "queued"
    return {
        "job_id": job_id,
        "status": status,
        "blocking": False,
    }
