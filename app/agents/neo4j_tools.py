"""In-process Neo4j / KG-2 tools for recommend mode (S7.2 / S8.3).

Templates only — no free-form Cypher, no MCP server.
Fake backend is the default; ``NEO4J_BACKEND=bolt`` reads a live fleet graph.
Populate enqueue is ops-only (HTTP to the pack admin URL) and never runs on
the recommend hot path.

Tool names are stable contracts for LangGraph traces and Delegator skip (K-3).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

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

FLEET_LABELS: frozenset[str] = frozenset(
    {"Asset", "Booking", "Category", "Attachment"}
)
DOCUMENT_LABELS: frozenset[str] = frozenset({"Document"})

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

# Use labels() membership, not `:Document`. Neo4j 5+ emits 01N50 when a
# negative label predicate names a token that has never been created.
_FLEET_NODES_CYPHER = (
    "MATCH (n) "
    "WHERE any(l IN labels(n) WHERE l IN $fleet_labels) "
    "AND NOT 'Document' IN labels(n) "
    "RETURN n"
)
_FLEET_RELS_CYPHER = (
    "MATCH (a)-[r]->(b) "
    "WHERE any(l IN labels(a) WHERE l IN $fleet_labels) "
    "AND any(l IN labels(b) WHERE l IN $fleet_labels) "
    "AND NOT 'Document' IN labels(a) AND NOT 'Document' IN labels(b) "
    "RETURN a, r, b"
)


class FreeFormCypherRejected(ValueError):
    """Agents must not pass free-form Cypher to Neo4j tools."""


class UnknownNeo4jTemplateError(ValueError):
    """Template name is not on the Neo4j read allowlist."""


# ---------------------------------------------------------------------------
# Graph backends
# ---------------------------------------------------------------------------


@runtime_checkable
class Neo4jBackend(Protocol):
    """Read-only KG-2 source (fake fixture or live Bolt)."""

    @property
    def is_empty(self) -> bool:
        ...

    @property
    def is_available(self) -> bool:
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

    @property
    def is_available(self) -> bool:
        return True

    def nodes(self) -> list[dict[str, Any]]:
        return deepcopy(self._nodes)

    def relationships(self) -> list[dict[str, Any]]:
        return deepcopy(self._relationships)


class UnavailableNeo4jBackend:
    """Bolt down / missing driver / auth fail — K-3 skip path."""

    @property
    def is_empty(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        return False

    def nodes(self) -> list[dict[str, Any]]:
        return []

    def relationships(self) -> list[dict[str, Any]]:
        return []


def _labels_of(raw: Any) -> list[str]:
    if hasattr(raw, "labels"):
        return [str(label) for label in raw.labels]
    if isinstance(raw, dict):
        labels = raw.get("labels")
        if labels:
            return [str(label) for label in labels]
        label = raw.get("label")
        if label:
            return [str(label)]
    return []


def _props_of(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        props = raw.get("properties")
        if isinstance(props, dict):
            return dict(props)
        skip = {"labels", "label", "properties", "from", "to", "type"}
        return {k: v for k, v in raw.items() if k not in skip}
    try:
        return dict(raw)
    except Exception:  # noqa: BLE001
        return {}


def _raw_id(raw: Any, props: dict[str, Any]) -> str:
    for key in ("id", "asset_id", "name"):
        value = props.get(key)
        if value is not None and str(value).strip():
            return str(value)
    if isinstance(raw, dict):
        for key in ("id", "asset_id"):
            value = raw.get(key)
            if value is not None and str(value).strip():
                return str(value)
    element_id = getattr(raw, "element_id", None)
    if element_id is not None:
        return str(element_id)
    return ""


def _primary_label(labels: list[str]) -> str:
    for name in ("Asset", "Booking", "Category", "Attachment"):
        if name in labels:
            return name
    return labels[0] if labels else ""


def _is_fleet_node(labels: list[str]) -> bool:
    labs = set(labels)
    if labs & DOCUMENT_LABELS and not (labs & FLEET_LABELS):
        return False
    if "Document" in labs and not (labs & FLEET_LABELS):
        return False
    return bool(labs & FLEET_LABELS)


def _map_node(raw: Any) -> dict[str, Any] | None:
    labels = _labels_of(raw)
    if not _is_fleet_node(labels):
        return None
    props = _props_of(raw)
    node_id = _raw_id(raw, props)
    if not node_id:
        return None
    category = props.get("category")
    return {
        "id": node_id,
        "label": _primary_label(labels),
        "category": category,
        "properties": props,
    }


def _rel_type(raw: Any) -> str:
    if hasattr(raw, "type"):
        return str(raw.type or "")
    if isinstance(raw, dict):
        return str(raw.get("type") or "")
    return ""


def _rel_endpoints(
    raw: Any, start: Any | None, end: Any | None
) -> tuple[Any, Any]:
    if start is not None and end is not None:
        return start, end
    if isinstance(raw, dict):
        return raw.get("from"), raw.get("to")
    start_node = getattr(raw, "start_node", None)
    end_node = getattr(raw, "end_node", None)
    return start_node, end_node


def _endpoint_id(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    mapped = _map_node(raw)
    if mapped is not None:
        return str(mapped["id"])
    props = _props_of(raw) if not isinstance(raw, str) else {}
    return _raw_id(raw, props)


def map_fleet_graph(
    raw_nodes: list[Any],
    raw_relationships: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map Bolt / dict records to the S7.2 fixture shape. Drops ``:Document``."""
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_nodes:
        mapped = _map_node(raw)
        if mapped is None or mapped["id"] in seen:
            continue
        seen.add(str(mapped["id"]))
        nodes.append(mapped)

    rels: list[dict[str, Any]] = []
    for raw in raw_relationships:
        if isinstance(raw, dict) and (
            "from" in raw or "type" in raw or raw.get("r") is None
        ):
            start, end = _rel_endpoints(raw, raw.get("a"), raw.get("b"))
            if start is None and raw.get("from") is not None:
                start, end = raw.get("from"), raw.get("to")
            rel = raw.get("r", raw)
        else:
            rel = raw
            start, end = _rel_endpoints(raw, None, None)
        src = _endpoint_id(start)
        dst = _endpoint_id(end)
        if not src or not dst or src not in seen or dst not in seen:
            continue
        rels.append({"from": src, "to": dst, "type": _rel_type(rel)})
    return nodes, rels


def _try_import_graph_database() -> Any | None:
    try:
        from neo4j import GraphDatabase  # type: ignore[import-not-found]
    except ImportError:
        return None
    return GraphDatabase


class BoltNeo4jBackend:
    """Live KG-2 read over Bolt. Fleet labels only; never touches ``:Document``."""

    def __init__(
        self,
        uri: str,
        user: str = "neo4j",
        password: str = "neo4j",
        *,
        driver: Any | None = None,
    ) -> None:
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = driver
        self._error: BaseException | None = None
        self._cache: tuple[list[dict[str, Any]], list[dict[str, Any]]] | None = None
        if driver is None:
            graph_database = _try_import_graph_database()
            if graph_database is None:
                self._error = ImportError("neo4j package not installed")
                return
            try:
                self._driver = graph_database.driver(uri, auth=(user, password))
            except Exception as exc:  # noqa: BLE001
                self._error = exc
                self._driver = None

    @classmethod
    def from_mapped(
        cls,
        nodes: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> BoltNeo4jBackend:
        """Unit helper: skip Bolt and use already-mapped fleet rows."""
        inst = cls.__new__(cls)
        inst._uri = ""
        inst._user = ""
        inst._password = ""
        inst._driver = None
        inst._error = None
        inst._cache = (deepcopy(nodes), deepcopy(relationships))
        return inst

    @property
    def is_available(self) -> bool:
        if self._error is not None:
            return False
        try:
            self._load()
        except Exception as exc:  # noqa: BLE001
            self._error = exc
            logger.warning("neo4j bolt unavailable: %s", exc)
            return False
        return True

    @property
    def is_empty(self) -> bool:
        if not self.is_available:
            return True
        nodes, rels = self._load()
        return not nodes and not rels

    def nodes(self) -> list[dict[str, Any]]:
        if not self.is_available:
            return []
        return deepcopy(self._load()[0])

    def relationships(self) -> list[dict[str, Any]]:
        if not self.is_available:
            return []
        return deepcopy(self._load()[1])

    def _load(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if self._cache is not None:
            return self._cache
        if self._driver is None:
            raise RuntimeError("neo4j driver is not configured")
        params = {"fleet_labels": list(FLEET_LABELS)}
        with self._driver.session() as session:
            node_rows = [record["n"] for record in session.run(_FLEET_NODES_CYPHER, params)]
            rel_rows = list(session.run(_FLEET_RELS_CYPHER, params))
        raw_rels = [
            {"a": record["a"], "r": record["r"], "b": record["b"]} for record in rel_rows
        ]
        self._cache = map_fleet_graph(node_rows, raw_rels)
        return self._cache


def build_neo4j_backend(
    kind: str = "fake",
    *,
    settings: Any | None = None,
    driver: Any | None = None,
) -> Neo4jBackend:
    """Construct a KG-2 backend. Unknown/missing Bolt degrades to unavailable."""
    name = str(kind or "fake").strip().lower()
    if name in {"", "fake", "memory"}:
        return FakeNeo4jBackend()
    if name != "bolt":
        raise ValueError(f"unknown neo4j backend kind: {name!r}")
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    uri = str(getattr(settings, "neo4j_uri", "") or "")
    user = str(getattr(settings, "neo4j_user", "neo4j") or "neo4j")
    password = str(getattr(settings, "neo4j_password", "neo4j") or "")
    backend = BoltNeo4jBackend(uri, user=user, password=password, driver=driver)
    if not backend.is_available:
        return UnavailableNeo4jBackend()
    return backend


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
    if getattr(graph, "is_empty", True):
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


def _default_http_post(url: str, *, timeout: float = 2.0) -> dict[str, Any]:
    response = httpx.post(url, timeout=timeout)
    response.raise_for_status()
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if "status" not in payload:
        payload["status"] = "queued"
    return payload


def trigger_neo4j_populate(
    *,
    backend: Neo4jBackend | None = None,
    populate_url: str | None = None,
    http_post: Callable[[str], dict[str, Any]] | None = None,
    timeout_seconds: float = 2.0,
    **kwargs: Any,
) -> dict[str, Any]:
    """Enqueue a non-blocking KG-2 populate job.

    Fake / no URL: ``noop`` (empty) or ``queued``. Live URL: best-effort HTTP
    POST; transport errors become ``unavailable``. Never raises to callers.
    """
    _reject_freeform(**kwargs)
    job_id = f"neo4j_pop_{uuid.uuid4().hex}"
    url = str(populate_url or "").strip()
    if url:
        poster = http_post or (
            lambda target: _default_http_post(target, timeout=timeout_seconds)
        )
        try:
            payload = poster(url) or {}
        except Exception:
            logger.warning("neo4j populate POST failed url=%s", url, exc_info=True)
            return {"job_id": job_id, "status": "unavailable", "blocking": False}
        status = str(payload.get("status") or "queued")
        returned_id = payload.get("job_id")
        return {
            "job_id": str(returned_id) if returned_id else job_id,
            "status": status,
            "blocking": False,
        }

    graph = backend if backend is not None else FakeNeo4jBackend()
    status = "noop" if getattr(graph, "is_empty", True) else "queued"
    return {
        "job_id": job_id,
        "status": status,
        "blocking": False,
    }
