# Postman — Call 1 ingest · Call 2 recommend · Call 3 chatbot Q&A

Importable Postman artifacts aligned with **as-built** haystack-fast-api (lean Call 1, quote Call 2, Q&A Call 3).

```text
# Call 1 — ingest (public lean FR-IX-023)
index + mandatory KG-1 (internal) → ingest_id, summary, needs_summary, …

# Call 2 — recommend / quote (same process, after Call 1)
SessionRecommendService → MVP or RECOMMEND_VIA_AGENT_GRAPH
→ quoteRef, items[], confidenceScore, mlPredictedPrice

# Call 3 — chatbot Q&A (optional follow-up)
research (vector) → graph (KG-1) → synthesis → answer
```

## Files

| Path | Purpose |
|------|---------|
| `Indexing-Pipeline.postman_collection.json` | Health + Call 1 happy/negatives + **Call 2 quote** + **Call 3 Q&A** |
| `Indexing-Pipeline-Local.postman_environment.json` | Environment (`baseUrl`, paths, `userId`, `ingestId`, …) |
| `fixtures/` | Sample upload files for multipart requests |
| `README.md` | This guide |

### Environment / collection variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `baseUrl` | `http://localhost:8000` | API host |
| `ingestPath` | `/internal/v1/recommendations/submitprojectspecification` | **Call 1** |
| `projectKnowledgePath` | `/internal/v1/recommendations/project-knowledge/getassetrecommendations` | **Call 2 recommend / quote** |
| `projectKnowledgeQueryPath` | `/internal/v1/recommendations/project-knowledge/query` | **Call 3 chatbot Q&A** |
| `userId` | `user_demo` | Required identity (saved from Call 1) |
| `ingestId` | _(empty)_ | Filled by successful Call 1 Tests scripts |
| `agentQuery` | excavator/soil question | Optional Call 2 focus; Call 3 query text |
| `idempotencyKey` | _(empty / collection)_ | Optional Call 1 `Idempotency-Key` |
| `correlationId` | `postman-corr-demo` | Optional `X-Correlation-Id` |
| `traceparent` | _(empty)_ | Optional W3C trace |

### Fixtures

| File | Kind | Notes |
|------|------|--------|
| `fixtures/project.txt` | Unstructured text | Happy multipart |
| `fixtures/brief.md` | Markdown | Happy multipart |
| `fixtures/needs.csv` | Structured CSV | Happy multipart |
| `fixtures/needs.json` | Structured JSON | Happy multipart |
| `fixtures/empty.txt` | Empty | **400** |
| `fixtures/unsupported.bin` | Unknown type | **400** |

> Public Call 1 responses no longer expose `data_kind` / `documents_written`. Classification still runs **internally** in the indexing pipeline.

## Start the API

```bash
cd haystack-fast-api
uv sync --all-groups
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Confirm: [http://localhost:8000/health](http://localhost:8000/health) and [http://localhost:8000/docs](http://localhost:8000/docs).

### Profiles that affect Postman results

| Profile | Typical env | Call 2 `equipment.id` |
|---------|-------------|------------------------|
| **Local / CI-like** | `FLEET_BACKEND=fake`, `RECOMMEND_VIA_AGENT_GRAPH=false`, `INDEXING_EMBEDDER=mock`, `PROJECT_AGENT_MODE=stub` | Seed `AST-*` |
| **Live compose** | `FLEET_BACKEND=sql`, `PRICING_SCHEMA=public`, optional `RECOMMEND_VIA_AGENT_GRAPH=true`, `NEO4J_BACKEND=bolt` | Digit string `assets.id` |

Sessions are **process-local** (InMemory default). Restarting uvicorn clears `ingestId` sessions unless you re-run Call 1 (or use durable `INDEXING_DOCUMENT_STORE=pgvector` + session reload paths).

## Import into Postman

1. Open Postman → **Import**.
2. Drag in:
   - `postman/Indexing-Pipeline.postman_collection.json`
   - `postman/Indexing-Pipeline-Local.postman_environment.json`
3. Top-right: select environment **Indexing Pipeline Local**.
4. Confirm `baseUrl` = `http://localhost:8000`.

## Multipart file requests

After import, Postman may not resolve relative `src` paths. For each **file** request:

1. Open the request → **Body** → **form-data**.
2. Row `file` → type **File** → **Select Files**.
3. Choose the matching file under `haystack-fast-api/postman/fixtures/`.

Do **not** set `Content-Type: application/json` on multipart requests.

All multipart happy-path requests include **`user_id`** (and optional `user_name`).

## Run order (suggested)

### Ingest (Call 1)

| # | Request | Expect |
|---|---------|--------|
| 01 | GET Health | 200 (`ok` or `degraded`) |
| 02 | JSON project_text | 200 **lean** FR-IX-023 |
| 03 | JSON no dates | 200 lean |
| 04–08 | multipart files | 200 lean |
| 09–14 | Negatives | **400**, `{"error":"bad_request","message":"..."}` |

### Portal dual-hop + chatbot (folder 04)

| # | Request | Expect |
|---|---------|--------|
| **15** | Call 1 ingest (saves `ingestId` / `userId`) | 200 lean FR-IX-023 |
| **16** | **Call 2 recommend** `getassetrecommendations` | 200 **quote**: `quoteRef`, `items`, `confidenceScore` (no `answer`) |
| **17** | **Call 3 chatbot Q&A** `project-knowledge/query` | 200 **`answer`**, `sources_used` (no `quoteRef`) |
| 18 | Call 2 missing session | **404** `not_found` |
| 19 | Call 3 empty query | **422** or **400** |

**Important:** Run **15 → 16** (and **17** if testing chatbot) against the **same** uvicorn process.

Portal product path maps to **15 + 16** (Call 1 + Call 2 quote). Call 3 is optional follow-up chat.

## Required identity

All ingest requests must include **`user_id`** (JSON or form-data). Optional: **`user_name`**.

Knowledge graph is **mandatory** on successful ingest (hard-fail if KG build fails). Artifacts land under `artifacts/kg/{user_id}/kg_{ingest_id}.json`. Full Ragas transforms only if `KG_APPLY_TRANSFORMS=true`. **`kg_*` fields are not on the public Call 1 body.**

## Resilience headers (S2a / C1)

| Header | Required | Purpose |
|--------|----------|---------|
| `Idempotency-Key` | no | **Call 1 only.** Same `user_id` + key → same `ingest_id` on retry (process-local). |
| `X-Correlation-Id` | no | All routes; **echoed**. Server mints UUID if omitted. |
| `traceparent` | no | Optional W3C Trace Context; logged when present. |

**Error shape (all routes):** `{"error":"<code>","message":"<text>"}`.

**Retry:** clients MAY retry **5xx** / transport timeouts on Call 1 with the **same** `Idempotency-Key`.

**Limits:** idempotency map is **process-local** (not multi-replica). Optional TTL: `IDEMPOTENCY_TTL_SECONDS` (default 86400).

## Success body checklists (as-built)

### Call 1 ingest (lean FR-IX-023)

```json
{
  "ingest_id": "ing_…",
  "user_id": "user_demo",
  "user_requirement_summary": "…",
  "tentative_start_date": "2026-09-01",
  "tentative_end_date": "2026-09-30",
  "needs_summary": [
    {
      "need_id": "need_1",
      "description": "…",
      "equipment_hints": ["scissor lift"],
      "quantity": 1
    }
  ],
  "expected_budget": { "amount": 15000, "currency": "SGD", "source": "extracted" },
  "warnings": []
}
```

**Not on public body:** `data_kind`, `documents_written`, `documents[]`, `kg_built`, `kg_artifact_path`, `recommendation_id`, `results_by_need`.

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
      "needId": "need_1",
      "mlPredictedPrice": 185.0,
      "equipment": {
        "id": "12",
        "name": "…",
        "category": "Scissors Lift",
        "baseDailyRate": 185.0,
        "available": true
      }
    }
  ],
  "warnings": []
}
```

| Field notes | |
|-------------|--|
| `equipment.id` | Live SQL: `str(assets.id)`. Fake: seed `AST-*`. |
| `mlPredictedPrice` | Predicted daily rate when item returned; equals `baseDailyRate` when set. |
| `confidenceScore` | Evidence formula; `null` if no items. |
| Not on body | `answer`, `tool_traces` |

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

## Normative / process docs

| Doc | Purpose |
|-----|---------|
| [`docs/call1-call2-endpoint-process.md`](../docs/call1-call2-endpoint-process.md) | Full Call 1/2 process + eval |
| [`docs/multi-agent-architecture.md`](../docs/multi-agent-architecture.md) | Multi-agent graphs (gate, Call 2 C/W/D, Call 3) |
| [`docs/eval/`](../docs/eval/) | Offline eval scoreboard + test-data export |
| [`openspec/specs/indexing/contracts/ingest-from-project-spec.md`](../openspec/specs/indexing/contracts/ingest-from-project-spec.md) | Call 1 contract |
| [`openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md`](../openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md) | Call 2 contract |
| [`openspec/specs/knowledge-graph/contracts/project-knowledge-query.md`](../openspec/specs/knowledge-graph/contracts/project-knowledge-query.md) | Call 3 contract |
| [`Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md) | Spring dual-hop |

## Collection tests (what Postman asserts)

| Requests | Assertions |
|----------|------------|
| Call 1 happy (02–08, 15) | 200; lean keys; **no** `data_kind` / `kg_built` / `documents`; save `ingestId` |
| Call 1 negatives (09–14) | 400 + shared error shape |
| Call 2 (16) | 200; `quoteRef` / `items`; no `answer` / `tool_traces`; item price/score shape |
| Call 3 (17) | 200; `answer`; no `quoteRef` |
| Call 2 missing session (18) | 404 `not_found` |
| Call 3 empty query (19) | 400 or 422 |
