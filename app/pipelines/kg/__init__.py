"""Knowledge graph pipeline (HR-76): post-join chunks → bridge → generate → save."""

from app.pipelines.kg.ragas_compat import ensure_langchain_community_vertexai_chat

ensure_langchain_community_vertexai_chat()

from app.pipelines.kg.bridge import DocumentToLangChainConverter
from app.pipelines.kg.generator import KnowledgeGraphGenerator
from app.pipelines.kg.runner import run_knowledge_graph
from app.pipelines.kg.saver import KnowledgeGraphSaver

__all__ = [
    "DocumentToLangChainConverter",
    "KnowledgeGraphGenerator",
    "KnowledgeGraphSaver",
    "run_knowledge_graph",
]
