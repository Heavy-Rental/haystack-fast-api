# Contract: Project Knowledge Query (Call 2)

| Field | Value |
|-------|--------|
| **Capability** | `knowledge-graph` (Part B — Stage-1 multi-agent Q&A) |
| **Method / path** | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| **Schemas** | `app/schemas/project_knowledge.py` |
| **Service** | `app/services/project_knowledge_qa.py` |
| **Prerequisite** | Successful `POST /internal/v1/recommendations/submitprojectspecification` in the **same process** (session registry is process-local) |
| **Behaviour** | [`../spec.md`](../spec.md) FR-KG-010, FR-KG-013, FR-KG-014 |
| **Testing** | [`../../../../docs/testing/knowledge-graph-testing-guide.md`](../../../../docs/testing/knowledge-graph-testing-guide.md) |
| **Standards** | OpenSpec · Spec-kit contracts · OpenSPDD agent prompts (`app/agents/prompts.py`) |

**Naming note:** Path is Spring-facing (`getassetrecommendations`). As-built behaviour is **project-knowledge Q&A** (markdown `answer`), **not** Call 3 ranked assets + prices (`results_by_need`).

---

## Request

`Content-Type: application/json`

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `user_id` | string | **yes** | Same `user_id` used at ingest; min length 1 |
| `ingest_id` | string | **yes** | `ingest_id` from Call 1 lean response; min length 1 |
| `query` | string | **yes** | Natural-language question **or** predefined prompt (may embed Call 1 `user_requirement_summary`); min length 1 |
| `top_k` | integer \| null | no | Optional retrieval depth override; `1…50` when set; defaults to `PROJECT_AGENT_TOP_K` |
| `kg_artifact_path` | string \| null | no | Optional path to reload KG-1 if the process-local session was lost. Vector store remains empty until re-ingest. |

### Example request (free-form)

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_REPLACE_ME",
  "query": "What excavator capacity and soil conditions are required?",
  "top_k": 5
}
```

### Example request (predefined prompt + Call 1 summary)

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_REPLACE_ME",
  "query": "Based on the existing information uploaded earlier, this is the summary: Indoor elevated work ~8m; need scissors lift. List equipment needs and constraints supported by the project sources only. Do not invent assets or rates."
}
```

### Example curl

```bash
curl -s -X POST http://localhost:8000/internal/v1/recommendations/project-knowledge/getassetrecommendations \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user_demo",
    "ingest_id": "ing_REPLACE_ME",
    "query": "What excavator capacity and soil conditions are required?",
    "top_k": 5
  }'
```

---

## Response (HTTP 200)

| Field | Type | Notes |
|-------|------|--------|
| `user_id` | string | Echo |
| `ingest_id` | string | Echo |
| `query` | string | Echo |
| `answer` | string | Markdown synthesis (`## Answer` / `## Evidence` / `## Gaps` under stub/llm contracts) |
| `sources_used` | string[] | Tool names invoked (expect both `project_vector_search` and `project_kg_query` on a healthy dual-source run) |
| `research_hits` | object[] | Vector retrieval hits (`content`, optional `score`, `meta`) |
| `graph_hits` | object[] | KG-1 hits (`content`, optional `score`, `meta` / previews) |
| `tool_traces` | object[] | Per-agent tool call trace: `agent`, `tool`, `query`, `hit_count` |
| `research_notes` | string \| null | Optional research-agent notes |
| `graph_notes` | string \| null | Optional graph-agent notes |

### Example success body

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_…",
  "query": "…",
  "answer": "## Answer\n…\n## Evidence\n- Vector: …\n- Graph: …\n## Gaps\n…",
  "sources_used": ["project_vector_search", "project_kg_query"],
  "research_hits": [],
  "graph_hits": [],
  "tool_traces": [
    { "agent": "research", "tool": "project_vector_search", "query": "…", "hit_count": 1 },
    { "agent": "graph", "tool": "project_kg_query", "query": "…", "hit_count": 1 }
  ],
  "research_notes": null,
  "graph_notes": null
}
```

---

## Errors

| Status | When |
|--------|------|
| `400` | Validation (`user_id` / `ingest_id` / `query` missing or empty) |
| `404` | No session for `(user_id, ingest_id)` |

Error body: `{"error","message"}`.

---

## Related

Ingest route: `POST /internal/v1/recommendations/submitprojectspecification` — lean Call 1 contract  
[`ingest-from-project-spec.md`](../../indexing/contracts/ingest-from-project-spec.md).

Call 3 ranked assets: **not this route** — see recommendation-pipeline / implementation-plan S7.5.
