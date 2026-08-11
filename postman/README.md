# Postman — Indexing + Stage-1 multi-agent Q&A

Importable Postman artifacts for:

```text
# Ingest
classify → convert → clean → split → embed → write → KG-1

# Multi-agent (same process)
research (vector) → graph (KG-1) → synthesis
```

## Files

| Path | Purpose |
|------|---------|
| `Indexing-Pipeline.postman_collection.json` | Collection: ingest happy-path + negatives + **Stage-1 multi-agent** |
| `Indexing-Pipeline-Local.postman_environment.json` | Environment (`baseUrl`, paths, `userId`, `ingestId`, `agentQuery`) |
| `fixtures/` | Sample upload files for multipart requests |
| `README.md` | This guide |

### Environment / collection variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `baseUrl` | `http://localhost:8000` | API host |
| `ingestPath` | `/internal/v1/recommendations/submitprojectspecification` | Index + mandatory KG |
| `projectKnowledgePath` | `/internal/v1/recommendations/project-knowledge/getassetrecommendations` | Multi-agent Q&A |
| `userId` | `user_demo` | Required identity |
| `ingestId` | _(empty)_ | Filled by successful ingest Tests scripts |
| `agentQuery` | excavator/soil question | Query for multi-agent request |

### Fixtures

| File | Kind | Expected `data_kind` |
|------|------|----------------------|
| `fixtures/project.txt` | Unstructured | `unstructured` |
| `fixtures/brief.md` | Unstructured | `unstructured` |
| `fixtures/needs.csv` | Structured | `structured` |
| `fixtures/needs.json` | Structured | `structured` |
| `fixtures/empty.txt` | Empty | **400** |
| `fixtures/unsupported.bin` | Unknown | **400** |

## Start the API

```bash
cd haystack-fast-api
uv sync --all-groups
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Confirm: [http://localhost:8000/health](http://localhost:8000/health) and [http://localhost:8000/docs](http://localhost:8000/docs).

Defaults (CI-friendly):

- `INDEXING_EMBEDDER=mock` — no embedding API key  
- `PROJECT_AGENT_MODE=stub` — deterministic multi-agent synthesis, no LLM key  
- `KG_APPLY_TRANSFORMS=false` — document nodes only  

## Import into Postman

1. Open Postman → **Import**.
2. Drag in (or select):
   - `postman/Indexing-Pipeline.postman_collection.json`
   - `postman/Indexing-Pipeline-Local.postman_environment.json`
3. Top-right: select environment **Indexing Pipeline Local**.
4. Optional: confirm `baseUrl` = `http://localhost:8000`.

## Multipart file requests

After import, Postman may not resolve relative `src` paths. For each **file** request:

1. Open the request → **Body** → **form-data**.
2. Row `file` → type **File** → **Select Files**.
3. Choose the matching file under `haystack-fast-api/postman/fixtures/`.

Do **not** set `Content-Type: application/json` on multipart requests. Let Postman set `multipart/form-data` with a boundary.

All multipart happy-path requests include **`user_id`** (and optional `user_name`).

## Run order (suggested)

### Ingest (Parts 1–3 + mandatory KG)

| # | Request | Expect |
|---|---------|--------|
| 01 | GET Health | 200 (`ok` or `degraded`) |
| 02 | JSON project_text | 200, `data_kind=unstructured`, `has_embedding=true`, `kg_built=true` |
| 03 | JSON no dates | 200 |
| 04 | multipart `.txt` | 200, unstructured |
| 05 | multipart `.md` | 200, unstructured |
| 06 | multipart `.csv` | 200, **structured** |
| 07 | multipart `.json` | 200, structured |
| 08 | CSV + project_text | 200, often `mixed` |
| 09–14 | Negatives | **400**, `{"error":"bad_request","message":"..."}` |

### Stage-1 multi-agent Q&A (project sources only)

| # | Request | Expect |
|---|---------|--------|
| **15** | Ingest project-spec for multi-agent | 200; saves `ingestId` / `userId` |
| **16** | Project-knowledge query | 200; `sources_used` includes both tools |
| 17 | Missing session | **404** `not_found` |
| 18 | Empty query | **422** or **400** |

**Important:** Run **15 then 16** against the **same** uvicorn process. Sessions are process-local; restarting the server clears `ingestId` sessions even if the env var is still set.

Use **Collection → Run collection** to execute all Tests tabs (multi-agent folder will fail **16** if run order is wrong or `ingestId` is empty — run folder 04 alone after 15, or run the full collection in order).

## Required identity

All ingest requests must include **`user_id`** (JSON or form-data). Optional: **`user_name`**.

Knowledge graph is **mandatory** on successful ingest. Artifacts land under `artifacts/kg/{user_id}/kg_{ingest_id}.json`. Full Ragas transforms only if `KG_APPLY_TRANSFORMS=true` (runs inside `KnowledgeGraphGenerator`). KG failure fails the request.

## Success body checklist — ingest (S1a lean)

```json
{
  "ingest_id": "ing_…",
  "user_id": "user_demo",
  "user_requirement_summary": "Indoor elevated work ~8m; need scissors lift…",
  "tentative_start_date": "2026-09-01",
  "tentative_end_date": "2026-09-12",
  "needs_summary": [
    {
      "need_id": "need_1",
      "description": "Indoor elevated work ~8m; need scissors lift…",
      "equipment_hints": [],
      "quantity": 1
    }
  ],
  "warnings": []
}
```

(`tentative_*` are `null` when request omits dates. Stub decomposer yields one need from project text.)

**Not present on public body:** `documents[]`, `kg_*`, counts, `data_kind` (still run internally for Call 2).  
**Not present** (old recommend API): `recommendation_id`, `results_by_need`.

## Success body checklist — multi-agent Q&A

`POST /internal/v1/recommendations/project-knowledge/getassetrecommendations`

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_…",
  "query": "What excavator capacity and soil conditions are required?",
  "answer": "## Answer\n…\n## Evidence\n- Vector: …\n- Graph: …\n## Gaps\n…",
  "sources_used": ["project_vector_search", "project_kg_query"],
  "research_hits": [{ "content": "…", "score": null, "meta": {} }],
  "graph_hits": [{ "content": "…", "score": 1.0, "meta": {} }],
  "tool_traces": [
    { "agent": "research", "tool": "project_vector_search", "query": "…", "hit_count": 1 },
    { "agent": "graph", "tool": "project_kg_query", "query": "…", "hit_count": 1 }
  ]
}
```

Optional body field: `kg_artifact_path` (reload KG-1 after process restart; vector store stays empty until re-ingest).

Env: `PROJECT_AGENT_MODE=stub` (default) or `llm`; `PROJECT_AGENT_TOP_K=5`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Connection refused | Start uvicorn on port 8000 |
| Multipart 400 / empty file | Re-select fixture file; ensure file type is **File** not Text |
| Multipart 400 missing `user_id` | Form-data must include `user_id` |
| Wrong Content-Type on file upload | Remove manual `Content-Type` header |
| Tests fail on `has_embedding` / `kg_built` | Restart uvicorn with current code (`--reload`) |
| Multi-agent **16** → 404 | Re-run **15** on the same server; do not restart between 15 and 16 |
| Multi-agent empty `ingestId` | Run **15** first; check Collection/Environment variables |
| Health `degraded` | OK without Postgres for these endpoints |

## Specs

SDD source of truth: [`openspec/AGENTS.md`](../openspec/AGENTS.md) (OpenSpec · Spec-kit · OpenSPDD).

- **Indexing (live ingest):** [`openspec/specs/indexing/spec.md`](../openspec/specs/indexing/spec.md)
- **Knowledge graph + multi-agent:** [`openspec/specs/knowledge-graph/spec.md`](../openspec/specs/knowledge-graph/spec.md)
- **KG testing (pytest / curl / Postman):** [`docs/testing/knowledge-graph-testing-guide.md`](../docs/testing/knowledge-graph-testing-guide.md)
- Tasks (archived): [`openspec/changes/archive/2026-08-07-indexing-file-type-router/tasks.md`](../openspec/changes/archive/2026-08-07-indexing-file-type-router/tasks.md) · [`…/knowledge-graph-hr-76/tasks.md`](../openspec/changes/archive/2026-08-07-knowledge-graph-hr-76/tasks.md) · [`…/kg-multi-agent-stage1/tasks.md`](../openspec/changes/archive/2026-08-08-kg-multi-agent-stage1/tasks.md)
- Broader pipeline testing guide: [`docs/testing/recommendation-pipeline-testing-guide.md`](../docs/testing/recommendation-pipeline-testing-guide.md)
- Deferred recommend Postman (reattach only): [`docs/testing/recommendation-postman-testing-guide.md`](../docs/testing/recommendation-postman-testing-guide.md)
