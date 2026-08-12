# Knowledge Graph (moved)

> **Canonical:** [../openspec/specs/knowledge-graph/spec.md](../openspec/specs/knowledge-graph/spec.md)

**Call 3 (chatbot Q&A):** `POST /internal/v1/recommendations/project-knowledge/query`  
**Call 2 (recommend):** `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations`  
**Portal:** React project-spec → Call 1 → Call 2 quote → React; Call 3 optional chatbot.

See [openspec/AGENTS.md](../openspec/AGENTS.md) · [portal-to-haystack-mapping.md](../Feasibility_Study_Spring/portal-to-haystack-mapping.md)

### Pointer — pytest / vector tool (2026-08-12)

| Topic | Canonical |
|-------|-----------|
| Testing runbook | [`docs/testing/knowledge-graph-testing-guide.md`](../docs/testing/knowledge-graph-testing-guide.md) |
| `project_vector_search` dim match | [knowledge-graph design](../openspec/specs/knowledge-graph/design.md) · [spec FR-KG-014 scenario](../openspec/specs/knowledge-graph/spec.md) |
| Suite isolation | [project-setup design](../openspec/specs/project-setup/design.md) |

```bash
cd haystack-fast-api
uv run pytest tests/test_project_vector_tool.py tests/test_project_knowledge_*.py -q
```
