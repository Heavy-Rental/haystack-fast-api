"""project_kg_query tool."""

from haystack.dataclasses import Document

from app.agents.tools import TOOL_PROJECT_KG_QUERY, build_project_kg_query_tool
from app.pipelines.kg.generator import KnowledgeGraphGenerator
from app.pipelines.kg.query import query_knowledge_graph
from app.services.project_knowledge_session import ProjectKnowledgeSession
from haystack.document_stores.in_memory import InMemoryDocumentStore


def test_query_knowledge_graph_document_nodes() -> None:
    docs = [
        Document(
            content="Project needs a 20-ton excavator on soft clay within 8 weeks."
        )
    ]
    kg = KnowledgeGraphGenerator(apply_transforms=False).run(documents=docs)[
        "knowledge_graph"
    ]
    hits = query_knowledge_graph(kg, "excavator soft clay")
    assert len(hits) >= 1
    assert "excavator" in hits[0]["content_preview"].lower()


def test_kg_tool_wrapper() -> None:
    docs = [Document(content="Timeline is 8 weeks for soft clay trench.")]
    kg = KnowledgeGraphGenerator(apply_transforms=False).run(documents=docs)[
        "knowledge_graph"
    ]
    session = ProjectKnowledgeSession(
        user_id="u",
        ingest_id="ing",
        document_store=InMemoryDocumentStore(),
        knowledge_graph=kg,
    )
    tool = build_project_kg_query_tool(session)
    assert tool.name == TOOL_PROJECT_KG_QUERY
    hits = tool("soft clay")
    assert len(hits) >= 1
