# Contract: Project Knowledge Query

| Field | Value |
|-------|--------|
| **Capability** | `knowledge-graph` (Part B — Stage-1 multi-agent Q&A) |
| **Method / path** | `POST /api/v1/recommendations/project-knowledge/query` |
| **Schemas** | `app/schemas/project_knowledge.py` |
| **Service** | `app/services/project_knowledge_qa.py` |
| **Prerequisite** | Successful `POST /api/v1/recommendations/from-project-spec` in the **same process** (session registry is process-local) |
| **Behaviour** | [`../spec.md`](../spec.md) FR-KG-010, FR-KG-013, FR-KG-014 |
| **Testing** | [`../../../../docs/testing/knowledge-graph-testing-guide.md`](../../../../docs/testing/knowledge-graph-testing-guide.md) |

---

## Request

`Content-Type: application/json`

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `user_id` | string | **yes** | Same `user_id` used at ingest; min length 1 |
| `ingest_id` | string | **yes** | `ingest_id` returned by `/from-project-spec`; min length 1 |
| `query` | string | **yes** | Natural-language question; min length 1 |
| `top_k` | integer \| null | no | Optional retrieval depth override; `1…50` when set; defaults to `PROJECT_AGENT_TOP_K` |
| `kg_artifact_path` | string \| null | no | Optional path to reload KG-1 if the process-local session was lost. Vector store remains empty until re-ingest. |

### Example request

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_REPLACE_ME",
  "query": "What excavator capacity and soil conditions are required?",
  "top_k": 5
}
```

### Example curl

```bash
curl -s -X POST http://localhost:8000/api/v1/recommendations/project-knowledge/query \
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
  ]
}
```

**Expect (healthy Stage-1 run):** HTTP 200; both tools appear in `sources_used` and/or `tool_traces`; answer evidence cites Vector and Graph when hits exist.

---

## Negatives

| Case | Call | Expect |
|------|------|--------|
| Missing session | Q&A with unknown `ingest_id` (or no prior ingest in this process) | **404** `{"error":"not_found",…}` |
| Empty query | Q&A with `"query": ""` | **422** or **400** |
| Missing required fields | Omit `user_id`, `ingest_id`, or `query` | **422** (validation) |
| Missing `user_id` on **ingest** (upstream) | Ingest without `user_id` | **400** (indexing) |
| KG failure on **ingest** (upstream) | Simulated in pytest | Ingest **400** (hard-fail) — session never registered |

Shared error JSON shape (project-setup / core errors):

```json
{ "error": "<code>", "message": "<human-readable reason>" }
```

Common codes: `not_found`, `bad_request`, validation-driven 422.

---

## Process-local session note

- Sessions live in `ProjectKnowledgeSessionRegistry` in-process.
- Ingest (**15**) and query (**16**) must hit the **same** uvicorn process.
- After restart, optional `kg_artifact_path` may reload KG-1 only; dual-source Q&A requires re-ingest until DocumentStore snapshots exist (Stage 2).

---

## Related ingest fields (Part A — ownership shared with indexing)

Successful ingest that enables this route returns (among other indexing fields):

| Field | Expect on success |
|-------|-------------------|
| `ingest_id` | Starts with `ing_` |
| `kg_built` | `true` |
| `kg_node_count` | `≥ 1` |
| `kg_relationship_count` | present |
| `kg_artifact_path` | non-empty, under user-scoped path |
| `kg_transform_applied` | `false` when transforms off |

Ingest route: `POST /api/v1/recommendations/from-project-spec` — see indexing capability contracts for full field tables.
