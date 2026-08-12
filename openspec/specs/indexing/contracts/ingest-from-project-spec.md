# Contract: `POST /internal/v1/recommendations/submitprojectspecification`

| Field | Value |
|-------|--------|
| **Capability** | [`../spec.md`](../spec.md) (indexing) |
| **Design** | [`../design.md`](../design.md) |
| **Status** | **as-built** lean Call 1 + **full FR-IX-023** project-spec summary (S1a–S1e) + **S2a** idempotency/correlation + portal dual-hop note |
| **DTO (as-built)** | `IngestFromProjectSpecResponse` (`app/schemas/indexing.py`) |
| **Standards** | OpenSpec behaviour · Spec-kit contract tables · OpenSPDD (prompt/spec before code) |
| **Resilience** | Stage **S2a** / track **C1** — [`Feasibility_Study/phase2-s2a-haystack-implementation-plan.md`](../../../../Feasibility_Study/phase2-s2a-haystack-implementation-plan.md) |

Live HTTP owner: **indexing** (not FR-010 recommend on the public route).  
Internal pipeline still: dual-branch index → DocumentStore write → mandatory KG-1 → project-knowledge session register (for Call 2).

**Portal caller (Spring saga):** React `POST /api/recommendations/project-spec` → Spring **Call 1** hits **this** endpoint first, then Call 2 Q&A; React’s primary UX body for that portal request is Call 2 (see `Feasibility_Study_Spring/portal-to-haystack-mapping.md`). This route is **not** skipped for project-spec submit.

---

## Request headers (S2a as-built)

| Header | Required | Notes |
|--------|----------|--------|
| `Idempotency-Key` | no | UUID (or opaque string) per **logical** ingest. When present, scoped with `user_id`. Successful **200** lean body is stored process-locally and **replayed** on retry (same `ingest_id`). Failed **4xx/5xx are not cached**. Missing key → always new ingest (legacy behaviour). |
| `X-Correlation-Id` | no | End-to-end correlation. Logged on the request path; **echoed** on the response. If omitted, server mints a UUID. |
| `traceparent` | no | Optional W3C Trace Context; logged when present (C1 logging-only). |

**Idempotency rules (normative):**

1. Applies to **successful ingest only** (HTTP 200 lean body).  
2. Scope key = `user_id` + `Idempotency-Key` (same key under different users → different logical ingests).  
3. JSON and multipart honour the same key.  
4. Concurrent POSTs with the same scoped key use **single-flight** (wait for first producer; no double logical index).  
5. Store is **process-local memory** (optional TTL via `IDEMPOTENCY_TTL_SECONDS`, default 24h). **Not multi-replica safe** without a later shared store.  
6. Clients MAY retry **5xx** (and timed-out requests) with the **same** `Idempotency-Key`. Do **not** reuse a key for a different logical project-spec.

### Example headers

```http
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
X-Correlation-Id: spring-req-abc123
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
```

---

## Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Tenant for meta + KG path; also scopes `Idempotency-Key` |
| `user_name` | no | Audit only (not on lean public response) |
| `project_text` and/or `file` | one non-empty source | JSON-only needs non-empty text |
| `start_date` / `end_date` | no | Window valid if both set; echoed as `tentative_*` (S1b); free-text extract when omitted (S1e) |
| `options` / `include_pricing` | no | Accepted; **boolean** for future recommend pricing — **not** a budget amount |

Sources: multipart file uploads are packaged as Haystack `ByteStream` with `mime_type` derived from filename extension. Non-empty JSON `project_text` is unstructured `text/plain` when no file (or in addition to file sources).

### Example request (JSON)

```json
{
  "user_id": "user_demo",
  "user_name": "Demo User",
  "project_text": "Indoor elevated work ~8m; need scissors lift on soft clay.",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "options": { "include_pricing": true }
}
```

---

## Success response `200` — as-built lean `IngestFromProjectSpecResponse`

| Field | Type | Notes |
|-------|------|--------|
| `ingest_id` | string | `ing_` + hex — **required handle for Call 2 / Call 3** |
| `user_id` | string | Echo of request |
| `user_requirement_summary` | string | Deterministic summary of `project_text` or **extracted** multipart content (not raw bytes); may be truncated |
| `tentative_start_date` | date \| null | **S1b+S1e as-built:** request preferred; else free-text/file extract when confident; else `null` |
| `tentative_end_date` | date \| null | **S1b+S1e as-built:** request preferred; else free-text/file extract when confident; else `null` |
| `needs_summary` | array | **S1c as-built:** structured needs after index+KG via need decomposer (stub default in CI) |
| `needs_summary[].need_id` | string \| null | Optional stable id (e.g. `need_1`) |
| `needs_summary[].description` | string | Human-readable need |
| `needs_summary[].equipment_hints` | string[] | Optional category/type hints |
| `needs_summary[].quantity` | int \| null | Optional |
| `expected_budget` | object \| null | **S1d as-built:** extract only when confident; null + warning if not found; never invent |
| `expected_budget.amount` | number | When extracted |
| `expected_budget.currency` | string \| null | e.g. `SGD` |
| `expected_budget.source` | string | e.g. `extracted` |
| `warnings` | string[] | Soft issues (e.g. truncated summary, empty needs, budget not found); empty when none |

### Example (as-built lean + full FR-IX-023 S1a–S1e)

```json
{
  "ingest_id": "ing_a1b2c3d4e5f6",
  "user_id": "user_demo",
  "user_requirement_summary": "Indoor elevated work ~8m; need scissors lift on soft clay. Budget SGD 15000. From 2026-09-01 to 2026-09-12.",
  "tentative_start_date": "2026-09-01",
  "tentative_end_date": "2026-09-12",
  "needs_summary": [
    {
      "need_id": "need_1",
      "description": "Indoor elevated work ~8m; need scissors lift on soft clay. Budget SGD 15000. From 2026-09-01 to 2026-09-12.",
      "equipment_hints": [],
      "quantity": 1
    }
  ],
  "expected_budget": {
    "amount": 15000,
    "currency": "SGD",
    "source": "extracted"
  },
  "warnings": []
}
```

### Not on public body (still executed internally)

| Concern | Where |
|---------|--------|
| Chunk previews, counts, `data_kind`, mime/filenames | Indexing pipeline + session `meta` |
| `kg_built`, node/rel counts, artifact path, transforms | KG runner + session registry |
| Session DocumentStore + KG-1 | `ProjectKnowledgeSession` for Call 2 |

### FR-IX-023 as-built checklist (Phase 1.7)

All Call 1 project-spec summary increments are **as-built** (implementation-plan Phase 1):

| Stage | Field / behaviour | Status |
|-------|-------------------|--------|
| **S1a** | `ingest_id`, `user_id`, `user_requirement_summary`, `warnings` | **as-built** |
| **S1b** | Request date **echo** as `tentative_*` | **as-built** |
| **S1c** | `needs_summary[]` via need decomposer | **as-built** |
| **S1d** | `expected_budget` extract-only (never invent) | **as-built** |
| **S1e** | Free-text / file date extract when request omits dates (request preferred) | **as-built** |
| **1.7** | OpenSpec + Postman + regression mark full FR-IX-023 as-built | **as-built** |

Default response **SHOULD** stay compact (no public `documents[]` / `kg_*`).

### Still not on Call 1 (default path)

| Field | Why |
|-------|-----|
| `recommendation_id` / `results_by_need` | Call 3 / FR-010 reattach |
| Ranked `item.asset_id` / ML `daily_rate` | Fleet + pricing tools after ingest |

---

## Error notes (`400` / shared shape)

Error body shape (as-built): `{"error":"<code>","message":"<text>"}` (shared handlers in `app/core/errors.py`).

| Case | Notes |
|------|--------|
| Missing `user_id` | Required for meta + KG path (FR-IX-021) |
| Unclassified / unsupported type | Outside MIME map → 400 (FR-IX-003) |
| Empty file bytes / empty combined sources | FR-IX-009 |
| Zero documents after classification (hard conversion failure) | FR-IX-013 |
| Zero written chunks | FR-IX-016 |
| KG hard-fail | No lean success body; no session register for that ingest |
| Validation / bad content-type | `bad_request` — **not** stored under `Idempotency-Key` |

**Retry guidance (S2a):** Spring MAY retry **5xx** and transport timeouts with the same `Idempotency-Key`. **4xx** indicate client/input problems — fix the request before reusing a key (or use a new key for a new logical ingest).

**Ops limits (document only in C1):** process-local idempotency map; multi-replica requires a shared store (out of scope S2a). Max upload size is deployment/proxy-dependent (Uvicorn/reverse-proxy); no app-level hard cap beyond MIME validation.

---

## Call 2 handoff

Spring (or portal) stores `user_id` + `ingest_id` from this response, then calls:

`POST /internal/v1/recommendations/project-knowledge/getassetrecommendations`

For React **project-spec submit**, Call 2 **recommend** (`getassetrecommendations` quote) is the required second hop; Call 2 body is primary to React. Optional Call 3 chatbot: [`project-knowledge-query.md`](../../knowledge-graph/contracts/project-knowledge-query.md). Mapping: [`portal-to-haystack-mapping.md`](../../../../Feasibility_Study_Spring/portal-to-haystack-mapping.md).  
Recommend contract: [`get-asset-recommendations.md`](../../recommendation-pipeline/contracts/get-asset-recommendations.md).
