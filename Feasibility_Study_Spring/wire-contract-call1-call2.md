# Wire contract — Spring → haystack-fast-api (Call 1 / 2 / 3)

| Field | Value |
|-------|--------|
| **Version** | **2.0.0** |
| **Date** | 2026-08-12 |
| **Status** | As-built: Call 2 **recommend**, Call 3 **chatbot Q&A** |
| **Base URL (local)** | `http://localhost:8000` |
| **Auth** | None yet — private network only |
| **Portal mapping** | [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md) |

---

## Portal project-spec saga

```text
React  POST /api/recommendations/project-spec
  → Call 1  POST /internal/v1/recommendations/submitprojectspecification
  → Call 2  POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
            → quote / items[]  (primary body to React)
  → optional Call 3  POST /internal/v1/recommendations/project-knowledge/query
            → chatbot answer
```

---

## Endpoint inventory (live)

| Endpoint | Method | Role |
|----------|--------|------|
| `/health` | GET | Liveness / readiness |
| `/internal/v1/recommendations/submitprojectspecification` | POST | **Call 1** ingest |
| `/internal/v1/recommendations/project-knowledge/getassetrecommendations` | POST | **Call 2** recommend / quote |
| `/internal/v1/recommendations/project-knowledge/query` | POST | **Call 3** chatbot Q&A |

Optional: `POST /internal/v1/pricing/quote` (pricing only; not portal submit saga).

---

## Common

**Error body:** `{"error":"<code>","message":"<text>"}`  
**Correlation:** optional `X-Correlation-Id` / `traceparent` on all routes (echo/mint).  
**Idempotency-Key:** Call 1 only (S2a).

---

## Call 1 — ingest

See lean FR-IX-023 fields in [`call1-ingest-response-for-spring.md`](./call1-ingest-response-for-spring.md).

---

## Call 2 — recommend / quote

**Path:** `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations`  
**Code:** prefix `/internal/v1/recommendations` + `"/project-knowledge/getassetrecommendations"`  
**Contract:** `openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md`

### Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | yes | Same as Call 1 |
| `ingest_id` | yes | From Call 1 |
| `query` | no | Optional focus |
| `top_k` | no | Cap items |

### Response `200` (summary)

| Field | Notes |
|-------|--------|
| `user_id`, `ingest_id`, `query` | Echo |
| `quoteRef` | `QUO-…` |
| `confidenceScore`, `days`, `estimatedTotal` | When known |
| `specSummary`, `rationale` | From session / synthesis |
| `items[]` | `rankOrder`, `equipment.id`, `baseDailyRate`, `lineTotal`, … |
| `warnings` | Soft issues |

**Not on Call 2:** Q&A `answer` / tool_traces (use Call 3).

**Saga:** Call 2 5xx → do not re-ingest; keep `ingest_id`.

---

## Call 3 — chatbot Q&A

**Path:** `POST /internal/v1/recommendations/project-knowledge/query`  
**Contract:** `openspec/specs/knowledge-graph/contracts/project-knowledge-query.md`

### Request

| Field | Required |
|-------|----------|
| `user_id` | yes |
| `ingest_id` | yes |
| `query` | **yes** |
| `top_k` | no |
| `kg_artifact_path` | no |

### Response `200`

| Field | Notes |
|-------|--------|
| `user_id`, `ingest_id`, `query` | Echo |
| `answer` | Markdown chatbot reply |
| `sources_used`, `research_hits`, `graph_hits`, `tool_traces` | Evidence |
| `research_notes`, `graph_notes` | Optional |

---

## Document control

| Version | Date | Notes |
|---------|------|--------|
| **2.0.0** | 2026-08-12 | Call 2 recommend; Call 3 query; full path inventory |
| **1.1.1** | 2026-08-12 | Prior Call 2 = Q&A (superseded) |
