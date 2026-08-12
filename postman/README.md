# Postman — Call 1 ingest · Call 2 recommend · Call 3 chatbot Q&A

Importable Postman artifacts for:

```text
# Call 1 — ingest
classify → convert → clean → split → embed → write → KG-1 → lean FR-IX-023 body

# Call 2 — recommend / quote (same process, after Call 1)
SessionRecommendService → seed fleet + pricing → quoteRef / items[]

# Call 3 — chatbot Q&A (optional follow-up)
research (vector) → graph (KG-1) → synthesis → answer
```

## Files

| Path | Purpose |
|------|---------|
| `Indexing-Pipeline.postman_collection.json` | Ingest happy-path + negatives + **Call 2 recommend** + **Call 3 Q&A** |
| `Indexing-Pipeline-Local.postman_environment.json` | Environment (`baseUrl`, paths, `userId`, `ingestId`, `agentQuery`) |
| `fixtures/` | Sample upload files for multipart requests |
| `README.md` | This guide |

### Environment / collection variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `baseUrl` | `http://localhost:8000` | API host |
| `ingestPath` | `/internal/v1/recommendations/submitprojectspecification` | **Call 1** index + KG |
| `projectKnowledgePath` | `/internal/v1/recommendations/project-knowledge/getassetrecommendations` | **Call 2 recommend / quote** |
| `projectKnowledgeQueryPath` | `/internal/v1/recommendations/project-knowledge/query` | **Call 3 chatbot Q&A** |
| `userId` | `user_demo` | Required identity |
| `ingestId` | _(empty)_ | Filled by successful Call 1 Tests scripts |
| `agentQuery` | excavator/soil question | Optional Call 2 focus; required-style text for Call 3 |

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
- `PROJECT_AGENT_MODE=stub` — deterministic Call 3 synthesis, no LLM key  
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

### Ingest (Call 1)

| # | Request | Expect |
|---|---------|--------|
| 01 | GET Health | 200 (`ok` or `degraded`) |
| 02 | JSON project_text | 200 lean body (`ingest_id`, summary, …) |
| 03 | JSON no dates | 200 |
| 04 | multipart `.txt` | 200 |
| 05 | multipart `.md` | 200 |
| 06 | multipart `.csv` | 200 |
| 07 | multipart `.json` | 200 |
| 08 | CSV + project_text | 200 |
| 09–14 | Negatives | **400**, `{"error":"bad_request","message":"..."}` |

### Portal dual-hop + chatbot (folder 04)

| # | Request | Expect |
|---|---------|--------|
| **15** | Call 1 ingest (saves `ingestId` / `userId`) | 200 lean FR-IX-023 |
| **16** | **Call 2 recommend** `getassetrecommendations` | 200 **quote**: `quoteRef`, `items` (no `answer`) |
| **17** | **Call 3 chatbot Q&A** `project-knowledge/query` | 200 **`answer`**, tools (no `quoteRef`) |
| 18 | Call 2 missing session | **404** `not_found` |
| 19 | Call 3 empty query | **422** or **400** |

**Important:** Run **15 → 16** (and **17** if testing chatbot) against the **same** uvicorn process. Sessions are process-local; restarting the server clears `ingestId` sessions.

Portal product path maps to **15 + 16** (Call 1 + Call 2 quote). Call 3 is optional follow-up chat.

## Required identity

All ingest requests must include **`user_id`** (JSON or form-data). Optional: **`user_name`**.

Knowledge graph is **mandatory** on successful ingest. Artifacts land under `artifacts/kg/{user_id}/kg_{ingest_id}.json`. Full Ragas transforms only if `KG_APPLY_TRANSFORMS=true`. KG failure fails the request.

## Resilience headers (S2a / C1)

| Header | Required | Purpose |
|--------|----------|---------|
| `Idempotency-Key` | no | **Call 1 only.** Same `user_id` + key → same `ingest_id` on retry (process-local). |
| `X-Correlation-Id` | no | All routes; **echoed**. Server mints UUID if omitted. |
| `traceparent` | no | Optional W3C Trace Context; logged when present. |

**Error shape (all routes):** `{"error":"<code>","message":"<text>"}`.

**Retry:** clients MAY retry **5xx** / transport timeouts on Call 1 with the **same** `Idempotency-Key`.

**Limits:** idempotency map is **process-local** (not multi-replica). Optional TTL: `IDEMPOTENCY_TTL_SECONDS` (default 86400).

## Success body checklists

### Call 1 ingest (FR-IX-023)

```json
{
  "ingest_id": "ing_…",
  "user_id": "user_demo",
  "user_requirement_summary": "…",
  "tentative_start_date": null,
  "tentative_end_date": null,
  "needs_summary": [],
  "expected_budget": null,
  "warnings": []
}
```

### Call 2 recommend quote

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_…",
  "query": "…",
  "quoteRef": "QUO-…",
  "confidenceScore": 0.71,
  "days": 12,
  "estimatedTotal": 2220.0,
  "specSummary": "…",
  "rationale": "…",
  "items": [
    {
      "rankOrder": 1,
      "matchScore": 1.0,
      "reason": "…",
      "lineTotal": 2220.0,
      "quantity": 1,
      "equipment": {
        "id": "AST-…",
        "name": "…",
        "category": "…",
        "baseDailyRate": 185.0
      }
    }
  ],
  "warnings": []
}
```

### Call 3 chatbot Q&A

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_…",
  "query": "…",
  "answer": "## Answer\n…",
  "sources_used": ["project_vector_search", "project_kg_query"],
  "research_hits": [],
  "graph_hits": [],
  "tool_traces": [],
  "research_notes": null,
  "graph_notes": null
}
```

## Normative docs

- Portal mapping: `Feasibility_Study_Spring/portal-to-haystack-mapping.md`
- OpenSpec Call 2: `openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md`
- OpenSpec Call 3: `openspec/specs/knowledge-graph/contracts/project-knowledge-query.md`
