"""Run KG build from post-final_doc_joiner Haystack Documents (HR-76)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from haystack.dataclasses import Document

from app.pipelines.kg.bridge import DocumentToLangChainConverter
from app.pipelines.kg.generator import KnowledgeGraphGenerator
from app.pipelines.kg.saver import KnowledgeGraphSaver


@dataclass
class KnowledgeGraphResult:
    kg_built: bool
    kg_node_count: int | None
    kg_relationship_count: int | None
    kg_artifact_path: str | None
    kg_transform_applied: bool
    warnings: list[str]
    knowledge_graph: Any | None = None


def run_knowledge_graph(
    documents: list[Document],
    *,
    user_id: str,
    ingest_id: str,
    artifact_dir: str = "artifacts/kg",
    apply_transforms: bool = False,
) -> KnowledgeGraphResult:
    """Bridge → KnowledgeGraphGenerator (optional full Ragas) → saver."""
    if not documents:
        return KnowledgeGraphResult(
            kg_built=False,
            kg_node_count=0,
            kg_relationship_count=0,
            kg_artifact_path=None,
            kg_transform_applied=False,
            warnings=["no documents available for knowledge graph"],
            knowledge_graph=None,
        )

    bridge = DocumentToLangChainConverter()
    bridge_out = bridge.run(documents=documents)
    lc_docs = bridge_out.get("langchain_documents") or []

    generator = KnowledgeGraphGenerator(apply_transforms=apply_transforms)
    gen_out = generator.run(langchain_documents=lc_docs)
    warnings = list(gen_out.get("warnings") or [])
    kg = gen_out.get("knowledge_graph")
    node_count = int(gen_out.get("node_count") or 0)
    transform_applied = bool(gen_out.get("transform_applied"))

    if kg is None or node_count == 0:
        return KnowledgeGraphResult(
            kg_built=False,
            kg_node_count=node_count,
            kg_relationship_count=int(gen_out.get("relationship_count") or 0),
            kg_artifact_path=None,
            kg_transform_applied=transform_applied,
            warnings=warnings or ["knowledge graph produced no nodes"],
            knowledge_graph=None,
        )

    saver = KnowledgeGraphSaver(artifact_dir=artifact_dir)
    save_out = saver.run(
        knowledge_graph=kg,
        user_id=user_id,
        ingest_id=ingest_id,
    )
    return KnowledgeGraphResult(
        kg_built=True,
        kg_node_count=int(save_out.get("node_count") or node_count),
        kg_relationship_count=int(
            save_out.get("relationship_count") or gen_out.get("relationship_count") or 0
        ),
        kg_artifact_path=str(save_out.get("artifact_path") or ""),
        kg_transform_applied=transform_applied,
        warnings=warnings,
        knowledge_graph=kg,
    )
