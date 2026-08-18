"""HR-76: mandatory knowledge graph after final_doc_joiner; transforms on generator only."""

from pathlib import Path
from unittest.mock import patch

import pytest
from haystack.dataclasses import Document
from haystack.document_stores.in_memory import InMemoryDocumentStore

from app.config import get_settings
from app.core.exceptions import BadRequestError
from app.pipelines.indexing.embedder_factory import build_document_embedder
from app.pipelines.indexing.pipeline import build_indexing_pipeline
from app.pipelines.kg.bridge import DocumentToLangChainConverter
from app.pipelines.kg.generator import KnowledgeGraphGenerator
from app.pipelines.kg.runner import KnowledgeGraphResult, run_knowledge_graph
from app.pipelines.kg.saver import KnowledgeGraphSaver, safe_user_path_segment
from app.services.indexing import IndexingIngestService


def test_ragas_graph_imports_chat_vertexai_from_google_package() -> None:
    from langchain_google_vertexai import ChatVertexAI as GoogleChatVertexAI

    from app.pipelines.kg.ragas_compat import ensure_langchain_community_vertexai_chat

    ensure_langchain_community_vertexai_chat()
    from langchain_community.chat_models.vertexai import ChatVertexAI
    from ragas.testset.graph import KnowledgeGraph

    assert KnowledgeGraph is not None
    assert ChatVertexAI is GoogleChatVertexAI


def test_safe_user_path_segment() -> None:
    assert safe_user_path_segment("user/../x") == "user_.._x"
    assert safe_user_path_segment("normal-user_1") == "normal-user_1"


def test_bridge_and_generator_document_nodes(tmp_path: Path) -> None:
    docs = [
        Document(
            content="Need scissors lift for indoor mezzanine",
            meta={"user_id": "u1", "ingest_id": "ing_test"},
        )
    ]
    lc = DocumentToLangChainConverter().run(documents=docs)["langchain_documents"]
    assert len(lc) == 1
    assert "scissors" in lc[0].page_content.lower()

    gen = KnowledgeGraphGenerator(apply_transforms=False)
    out = gen.run(langchain_documents=lc)
    assert out["node_count"] == 1
    assert out["transform_applied"] is False
    assert out["knowledge_graph"] is not None

    saver = KnowledgeGraphSaver(artifact_dir=str(tmp_path))
    saved = saver.run(
        knowledge_graph=out["knowledge_graph"],
        user_id="u1",
        ingest_id="ing_test",
    )
    path = Path(saved["artifact_path"])
    assert path.exists()
    assert "u1" in str(path)
    assert "ing_test" in path.name


def test_run_knowledge_graph_user_scoped(tmp_path: Path) -> None:
    docs = [Document(content="Boom lift for facade", meta={})]
    result = run_knowledge_graph(
        docs,
        user_id="alice",
        ingest_id="ing_abc",
        artifact_dir=str(tmp_path),
        apply_transforms=False,
    )
    assert result.kg_built is True
    assert result.kg_node_count == 1
    assert result.kg_transform_applied is False
    assert result.kg_artifact_path
    assert Path(result.kg_artifact_path).exists()
    assert "alice" in result.kg_artifact_path


def test_service_always_builds_kg_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("KG_APPLY_TRANSFORMS", "false")
    get_settings.cache_clear()

    service = IndexingIngestService(
        pipeline=build_indexing_pipeline(
            document_store=InMemoryDocumentStore(),
            embedder=build_document_embedder(mode="mock", dimension=8),
        )
    )
    result = service.ingest_from_project_spec(
        user_id="bob",
        user_name="Bob Builder",
        project_text="Indoor elevated work for scissors lift",
    )
    assert result.user_id == "bob"
    assert "scissors" in result.user_requirement_summary.lower()
    from app.services.project_knowledge_session import get_project_knowledge_registry

    session = get_project_knowledge_registry().get("bob", result.ingest_id)
    assert session is not None
    assert session.kg_artifact_path
    assert Path(session.kg_artifact_path).exists()
    assert "bob" in session.kg_artifact_path
    assert session.meta.get("user_name") == "Bob Builder"
    assert session.meta.get("kg_node_count", 0) >= 1

    get_settings.cache_clear()


def test_two_users_distinct_kg_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path))
    get_settings.cache_clear()

    from app.services.project_knowledge_session import get_project_knowledge_registry

    def _ingest(uid: str, text: str):
        return IndexingIngestService(
            pipeline=build_indexing_pipeline(
                document_store=InMemoryDocumentStore(),
                embedder=build_document_embedder(mode="mock", dimension=4),
            )
        ).ingest_from_project_spec(user_id=uid, project_text=text)

    r1 = _ingest("user_a", "Need excavator for trench")
    r2 = _ingest("user_b", "Need boom lift for facade")
    s1 = get_project_knowledge_registry().get("user_a", r1.ingest_id)
    s2 = get_project_knowledge_registry().get("user_b", r2.ingest_id)
    assert s1 is not None and s2 is not None
    assert s1.kg_artifact_path != s2.kg_artifact_path
    assert "user_a" in (s1.kg_artifact_path or "")
    assert "user_b" in (s2.kg_artifact_path or "")

    get_settings.cache_clear()


def test_service_kg_failure_hard_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KG_ARTIFACT_DIR", str(tmp_path))
    get_settings.cache_clear()

    failed = KnowledgeGraphResult(
        kg_built=False,
        kg_node_count=0,
        kg_relationship_count=0,
        kg_artifact_path=None,
        kg_transform_applied=False,
        warnings=["simulated kg failure"],
    )

    service = IndexingIngestService(
        pipeline=build_indexing_pipeline(
            document_store=InMemoryDocumentStore(),
            embedder=build_document_embedder(mode="mock", dimension=4),
        )
    )
    with (
        patch(
            "app.pipelines.kg.runner.run_knowledge_graph",
            return_value=failed,
        ),
        pytest.raises(BadRequestError, match="simulated kg failure"),
    ):
        service.ingest_from_project_spec(
            user_id="u_fail",
            project_text="Need excavator",
        )

    get_settings.cache_clear()
