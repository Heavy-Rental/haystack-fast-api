"""Stage-1 project knowledge session registry."""

from pathlib import Path

import pytest
from haystack.dataclasses import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.core.exceptions import NotFoundError
from app.pipelines.kg.generator import KnowledgeGraphGenerator
from app.pipelines.kg.saver import KnowledgeGraphSaver
from app.services.project_knowledge_session import (
    ProjectKnowledgeSession,
    ProjectKnowledgeSessionRegistry,
    get_or_load_session,
    load_knowledge_graph_from_artifact,
)


def test_registry_put_get_delete() -> None:
    reg = ProjectKnowledgeSessionRegistry()
    store = InMemoryDocumentStore()
    session = ProjectKnowledgeSession(
        user_id="u1",
        ingest_id="ing_1",
        document_store=store,
        knowledge_graph=None,
        meta={"chunk_count": 0},
    )
    reg.put(session)
    assert len(reg) == 1
    got = reg.get("u1", "ing_1")
    assert got.document_store is store
    deleted = reg.delete("u1", "ing_1")
    assert deleted is True
    assert len(reg) == 0
    with pytest.raises(NotFoundError):
        reg.get("u1", "ing_1")


def test_load_kg_from_artifact(tmp_path: Path) -> None:
    docs = [Document(content="Need 20-ton excavator on soft clay")]
    kg = KnowledgeGraphGenerator(apply_transforms=False).run(documents=docs)[
        "knowledge_graph"
    ]
    path = KnowledgeGraphSaver(artifact_dir=str(tmp_path)).run(
        knowledge_graph=kg,
        user_id="u1",
        ingest_id="ing_x",
    )["artifact_path"]
    loaded = load_knowledge_graph_from_artifact(path)
    assert len(list(loaded.nodes)) >= 1

    reg = ProjectKnowledgeSessionRegistry()
    with pytest.raises(NotFoundError):
        reg.get("u1", "ing_x")
    session = get_or_load_session(
        "u1",
        "ing_x",
        kg_artifact_path=path,
        registry=reg,
    )
    assert session.knowledge_graph is not None
    assert session.meta.get("hydrated_from_artifact") is True
