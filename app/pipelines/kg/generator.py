"""KnowledgeGraphGenerator — document nodes + optional full Ragas transforms.

Full Ragas ``default_transforms`` / ``apply_transforms`` run **only here**
when ``apply_transforms=True`` (config ``KG_APPLY_TRANSFORMS``).
"""

from __future__ import annotations

import logging
from typing import Any

from haystack import component
from haystack.dataclasses import Document

logger = logging.getLogger(__name__)


def _import_ragas_graph():
    from app.pipelines.kg.ragas_compat import ensure_langchain_community_vertexai_chat

    ensure_langchain_community_vertexai_chat()
    from ragas.testset.graph import KnowledgeGraph, Node, NodeType

    return KnowledgeGraph, Node, NodeType


@component
class KnowledgeGraphGenerator:
    """Build a Ragas KnowledgeGraph from documents or LangChain docs.

    Always creates DOCUMENT nodes. When ``apply_transforms`` is true, runs
    full Ragas transforms (LLM + embeddings) inside this component only.
    """

    def __init__(self, *, apply_transforms: bool = False) -> None:
        self._apply_transforms = bool(apply_transforms)

    @component.output_types(
        knowledge_graph=object,
        node_count=int,
        relationship_count=int,
        transform_applied=bool,
        warnings=list[str],
    )
    def run(
        self,
        documents: list[Document] | None = None,
        langchain_documents: list[Any] | None = None,
    ) -> dict[str, Any]:
        warnings: list[str] = []
        KnowledgeGraph, Node, NodeType = _import_ragas_graph()

        kg = KnowledgeGraph()
        contents: list[tuple[str, dict[str, Any]]] = []

        if langchain_documents:
            for lc in langchain_documents:
                text = str(getattr(lc, "page_content", "") or "")
                meta = dict(getattr(lc, "metadata", None) or {})
                contents.append((text, meta))
        for doc in documents or []:
            contents.append((doc.content or "", dict(doc.meta or {})))

        for text, meta in contents:
            if not str(text).strip():
                continue
            node = Node(
                type=NodeType.DOCUMENT,
                properties={
                    "page_content": text,
                    "document_metadata": meta,
                },
            )
            kg.add(node)

        transform_applied = False
        if self._apply_transforms:
            try:
                from ragas.testset.transforms import apply_transforms, default_transforms

                # Full Ragas transform path — requires LLM/embedder configuration
                # in the environment. Failures surface as warnings unless strict.
                transforms = default_transforms()
                apply_transforms(kg, transforms)
                transform_applied = True
            except Exception as exc:  # noqa: BLE001
                msg = f"full Ragas transforms failed on KnowledgeGraphGenerator: {exc}"
                logger.warning(msg)
                warnings.append(msg)

        node_count = len(getattr(kg, "nodes", []) or [])
        rel_count = len(getattr(kg, "relationships", []) or [])
        return {
            "knowledge_graph": kg,
            "node_count": node_count,
            "relationship_count": rel_count,
            "transform_applied": transform_applied,
            "warnings": warnings,
        }
