# Testing Guide: Knowledge Graph Assembly & Multi-Agent Q&A

Normative **how to verify** Part A (KG assembly) and Part B (Stage-1 multi-agent).

| Field | Value |
|-------|--------|
| **Capability** | [`openspec/specs/knowledge-graph/spec.md`](../../openspec/specs/knowledge-graph/spec.md) |
| **Design** | [`openspec/specs/knowledge-graph/design.md`](../../openspec/specs/knowledge-graph/design.md) |
| **Q&A contract** | [`openspec/specs/knowledge-graph/contracts/project-knowledge-query.md`](../../openspec/specs/knowledge-graph/contracts/project-knowledge-query.md) |
| **Postman (live HTTP)** | [`../../postman/README.md`](../../postman/README.md) — folder **04 Stage-1 multi-agent Q&A** |
| **Source migration** | Extracted from historical `specification/SPEC-knowledge-graph.md` §10 |

Operational Postman import/fixture detail: [`../../postman/README.md`](../../postman/README.md).

---

## Prerequisites

```bash
cd haystack-fast-api
uv sync --all-groups
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Confirm: `GET http://localhost:8000/health` and OpenAPI at `/docs`.

**CI-safe defaults** (no LLM / embedder API keys required):

| Env | Default | Purpose |
|-----|---------|---------|
| `INDEXING_EMBEDDER` | `mock` | Deterministic embeddings for store + retrieval |
| `KG_APPLY_TRANSFORMS` | `false` | Document nodes only (full Ragas transforms optional) |
| `PROJECT_AGENT_MODE` | `stub` | Deterministic synthesis from tool hits |
| `PROJECT_AGENT_TOP_K` | `5` | Retrieval depth |
| `KG_ARTIFACT_DIR` | `artifacts/kg` | User-scoped JSON snapshots |

Working directory for all commands: **`haystack-fast-api/`** (app root).

---

## Automated tests (pytest)

```bash
cd haystack-fast-api

# Part A — mandatory KG after final_doc_joiner (hard-fail, artifacts, multi-user paths)
uv run pytest tests/test_knowledge_graph.py -v

# Part B — session registry, tools, LangGraph agents, HTTP Q&A
uv run pytest \
  tests/test_project_knowledge_session.py \
  tests/test_project_vector_tool.py \
  tests/test_project_kg_query_tool.py \
  tests/test_project_knowledge_agents.py \
  tests/test_project_knowledge_api.py -v

# Full suite (includes indexing + recommend service tests)
uv run pytest tests/ -v
```

| Test file | Proves |
|-----------|--------|
| `tests/test_knowledge_graph.py` | Bridge/generator/saver; ingest always builds KG; hard-fail on KG error; per-user artifact paths |
| `tests/test_project_knowledge_session.py` | Registry put/get/delete; load KG from JSON artifact |
| `tests/test_project_vector_tool.py` | Dense retrieval over ingest-scoped `InMemoryDocumentStore` |
| `tests/test_project_kg_query_tool.py` | KG-1 substring / document-node query |
| `tests/test_project_knowledge_agents.py` | One LangGraph run invokes **both** tools; synthesis cites Vector + Graph |
| `tests/test_project_knowledge_api.py` | HTTP ingest → Q&A 200 dual-source; missing session **404** |

**Expect:** all listed tests pass with `PROJECT_AGENT_MODE=stub` and mock embedder.

---

## Manual HTTP — curl

Use distinctive project text so vector + KG hits are obvious under mock embeddings.

### 1) Ingest (Part A)

```bash
curl -s -X POST http://localhost:8000/internal/v1/recommendations/submitprojectspecification \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user_demo",
    "user_name": "Demo User",
    "project_text": "Site preparation for foundation work. Requires a 20-ton excavator operating on soft clay soil. Project timeline is 8 weeks from mobilisation."
  }'
```

**Expect (ingest):** HTTP 200; `ingest_id` starts with `ing_`; `kg_built=true`; `kg_node_count ≥ 1`; `kg_artifact_path` non-empty; `documents_written ≥ 1`; `documents[0].has_embedding=true`; no `recommendation_id` / `results_by_need`.

### 2) Multi-agent Q&A (Part B)

Same process; paste `ingest_id` from step 1:

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

**Expect (Q&A):** HTTP 200; body shape:

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

Full field tables: [project-knowledge-query contract](../../openspec/specs/knowledge-graph/contracts/project-knowledge-query.md).

### Negatives

| Case | Call | Expect |
|------|------|--------|
| Missing session | Q&A with unknown `ingest_id` | **404** `{"error":"not_found",…}` |
| Empty query | Q&A with `"query": ""` | **422** or **400** |
| Missing `user_id` on ingest | Ingest without `user_id` | **400** |
| KG failure | (simulated in pytest) | Ingest **400** (hard-fail) |

---

## Manual HTTP — Postman

1. Import:
   - `postman/Indexing-Pipeline.postman_collection.json`
   - `postman/Indexing-Pipeline-Local.postman_environment.json`
2. Select environment **Indexing Pipeline Local**.
3. Start uvicorn (same process for the multi-agent pair).
4. Folder **04 Stage-1 multi-agent Q&A**:

| # | Request | Expect |
|---|---------|--------|
| **15** | Ingest project-spec for multi-agent | 200; Tests save `ingestId` / `userId` |
| **16** | Project-knowledge query (multi-agent) | 200; both tools in `sources_used` + `tool_traces` |
| 17 | Missing session | **404** |
| 18 | Empty query | **422** or **400** |

**Run 15 then 16 without restarting the server.** Sessions are process-local; a restart invalidates in-memory DocumentStore + session even if `ingestId` remains in the environment.

Fixture/import detail: [`../../postman/README.md`](../../postman/README.md).

---

## Acceptance mapping (test → AC)

| Acceptance criterion | Proof |
|----------------------|--------|
| Ingest produces DocumentStore chunks **and** KG-1 | `test_knowledge_graph.py`; curl/Postman **15**; ingest response `kg_*` + `documents_written` |
| LangGraph invokes vector tool **and** KG tool in one run | `test_project_knowledge_agents.py`; Postman **16**; `sources_used` / `tool_traces` |
| Synthesis uses both sources | Stub answer contains Vector + Graph evidence; agent + API tests |
| KG-1 discard without affecting other sessions | `test_project_knowledge_session.py` registry delete |
| Converter-only file-type variance | Indexing suite + `test_indexing_*` (shared generator) |
| KG-2 persistence without re-query Postgres | **Stage 2** — not tested yet |

Normative AC wording: [openspec knowledge-graph spec](../../openspec/specs/knowledge-graph/spec.md) User Scenarios & Requirements.

---

## Known limitations (when testing)

| Limitation | Implication |
|------------|-------------|
| Process-local sessions | Ingest and Q&A must hit the **same** uvicorn process |
| Vector store not snapshotted | After restart, optional `kg_artifact_path` reloads KG-1 only; dual-source needs re-ingest |
| `PROJECT_AGENT_MODE=stub` | Synthesis is template-based from tool hits (stable CI); use `llm` only with `LLM_*` configured |
| Mock embeddings | Prefer distinctive fixture phrases (e.g. “20-ton excavator”, “soft clay”); do not judge ranking quality |
| No KG-2 / fleet tools | Answers must not claim live equipment inventory or availability |

---

## Related docs

- Behaviour: [`openspec/specs/knowledge-graph/spec.md`](../../openspec/specs/knowledge-graph/spec.md)
- Design (REASONS): [`openspec/specs/knowledge-graph/design.md`](../../openspec/specs/knowledge-graph/design.md)
- Structured prompts index: [`openspec/spdd/prompts/project-knowledge-agents.md`](../../openspec/spdd/prompts/project-knowledge-agents.md)
- Indexing (ingest HTTP): [`openspec/specs/indexing/spec.md`](../../openspec/specs/indexing/spec.md)
- Broader pipeline testing: [`recommendation-pipeline-testing-guide.md`](./recommendation-pipeline-testing-guide.md) (if present)
