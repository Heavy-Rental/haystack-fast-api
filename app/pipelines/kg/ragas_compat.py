"""Make ragas 0.4.3 importable on langchain-community 0.4+.

ragas.llms.base still imports ``ChatVertexAI`` from
``langchain_community.chat_models.vertexai``. That module was removed when
Vertex AI moved to ``langchain-google-vertexai``. Re-export the real class
on the old path so ragas can import.
"""

from __future__ import annotations

import sys
import types


def ensure_langchain_community_vertexai_chat() -> None:
    name = "langchain_community.chat_models.vertexai"
    try:
        __import__(name)
        return
    except ImportError:
        pass

    try:
        from langchain_google_vertexai import ChatVertexAI
    except ImportError:

        class ChatVertexAI:
            """Fallback stub if langchain-google-vertexai is not installed."""

    module = types.ModuleType(name)
    module.ChatVertexAI = ChatVertexAI
    sys.modules[name] = module
    parent = sys.modules.get("langchain_community.chat_models")
    if parent is not None:
        parent.vertexai = module
