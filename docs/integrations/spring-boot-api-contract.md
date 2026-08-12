# Haystack API Contract — Spring Boot Integration

| Field | Value |
|-------|--------|
| **Document type** | External integration contract (caller-facing — written for the Spring Boot team, not internal reasoning) |
| **Status** | Draft — pending Spring Boot review, see "Open items" below |
| **Audience** | Spring Boot backend engineers integrating against `haystack-fast-api` |
| **Caller** | Spring Boot only. No route below is called directly by a browser/mobile client. |
| **Base URL (local dev)** | `http://localhost:8000` |
| **Auth** | **None yet** (deferred project-wide). Restrict access at network/ops level until an auth SDD exists — do not treat any route below as safe to expose publicly. |
| **Spring handoff pack (S2b / C1)** | [`Feasibility_Study_Spring/`](../../Feasibility_Study_Spring/) — wire contract uses live **`/internal/v1/recommendations/...`** paths; copy that folder into the Spring Boot repo |
| **Portal → haystack mapping** | [`Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../../Feasibility_Study_Spring/portal-to-haystack-mapping.md) |
| **Internal reasoning (Haystack maintainers only, not required reading for integration)** | [`openspec/specs/dynamic-pricing/`](../../openspec/specs/dynamic-pricing/), [`openspec/specs/recommendation-intake/`](../../openspec/specs/recommendation-intake/), [`openspec/project.md`](../../openspec/project.md) |

> **Path note:** Live Call 1 / Call 2 routes are under **`/internal/v1/recommendations/`** (see OpenSpec + Spring pack). Sections below that still show `/api/v1/...` are historical draft text — prefer [`Feasibility_Study_Spring/wire-contract-call1-call2.md`](../../Feasibility_Study_Spring/wire-contract-call1-call2.md) for Spring integration.

### Portal project-spec submit saga (normative)

```text
React  POST /api/recommendations/project-spec
  → Spring Call 1  POST /internal/v1/recommendations/submitprojectspecification
  → Spring Call 2  POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
  → React  primary body = Call 2 Q&A (mapped)
```

Call 1 is required first (ingest + `ingest_id`). Call 2 is the required second hop for this portal UX.

---

## Endpoint inventory

| Endpoint | Method | Purpose | Status |
|---|---|---|---|
| `/health` | GET | Liveness / readiness | Live |
| `/internal/v1/recommendations/submitprojectspecification` | POST | Ingest a project spec (text and/or file), build a knowledge graph | Live |
| `/internal/v1/recommendations/project-knowledge/getassetrecommendations` | POST | Multi-agent Q&A over a previously ingested project | Live |
| `/internal/v1/pricing/quote` | POST | Authoritative, guardrail-clamped price per asset at checkout | Live |

---

## Conventions common to every endpoint

- **Content-Type**: `application/json`, except ingest which also accepts `multipart/form-data` (for file upload).
- **Error shape**: every non-2xx response is `{"error": "<code>", "message": "<human-readable string>"}`.

  | HTTP status | `error` code |
  |---|---|
  | 400 | `bad_request` (includes request validation failures) |
  | 401 | `unauthorized` |
  | 403 | `forbidden` |
  | 404 | `not_found` |
  | 409 | `conflict` |
  | 422 | `bad_request` |
  | 500 | `internal_error` (unexpected server-side failure — treat as retryable/alertable, not a client bug) |

- **Correlation (S2a as-built):** send optional `X-Correlation-Id` (and/or W3C `traceparent`). Haystack logs and **echoes** `X-Correlation-Id` on every response; mints a UUID when omitted.
- **Idempotency on ingest (S2a as-built):** send optional `Idempotency-Key` (UUID per logical ingest) on Call 1. Scoped with `user_id`. Successful **200** lean bodies are replayed from a **process-local** store (same `ingest_id`); **4xx/5xx are not cached**. Safe for timeout retries. **Not multi-replica shared** yet.

Normative OpenSpec: [`openspec/specs/indexing/contracts/ingest-from-project-spec.md`](../../openspec/specs/indexing/contracts/ingest-from-project-spec.md).

---

## `GET /health`

Liveness/readiness check. No auth, no request body.

**Response `200`**
```json
{ "status": "ok", "database": "up" }
```

| Field | Type | Notes |
|---|---|---|
| `status` | `"ok" \| "degraded"` | Overall service status |
| `database` | `"up" \| "down"` | PostgreSQL connectivity at request time |

`status: "degraded"` can occur with `database: "down"` — the process is still up, but pricing/recommend routes that need DB access will fail.

---

## `POST /internal/v1/recommendations/submitprojectspecification`

Ingests a project description (free text and/or an uploaded file), always builds a knowledge graph on success (KG build failure fails the whole request), and returns an `ingest_id` used by the Q&A endpoint below.

**Request — `application/json`**

| Field | Type | Required | Notes |
|---|---|---|---|
| `user_id` | string | yes | Stable identifier; tenants documents/KG artifacts by this value |
| `user_name` | string | no | Display name only, echoed back |
| `project_text` | string | yes | Free-text project description |
| `start_date` | date (`YYYY-MM-DD`) | no | Rental window start |
| `end_date` | date (`YYYY-MM-DD`) | no | Rental window end; must be ≥ `start_date` |
| `options.include_pricing` | bool | no (default `true`) | Whether to attach pricing fields downstream |

**Request — `multipart/form-data`**: same fields as form parts, plus optional `file` (binary). Either `project_text` or `file` should carry real content.

**Response `200`** (lean body, FR-IX-023 — indexing/KG still run underneath but their internals are not exposed here)

```json
{
  "ingest_id": "ing_a1b2c3d4e5f6",
  "user_id": "user_demo",
  "user_requirement_summary": "Indoor elevated work ~8m; need scissors lift on soft clay. Budget SGD 15000. From 2026-09-01 to 2026-09-12.",
  "tentative_start_date": "2026-09-01",
  "tentative_end_date": "2026-09-12",
  "needs_summary": [
    {"need_id": "need_1", "description": "Indoor elevated work ~8m; need scissors lift on soft clay.", "equipment_hints": [], "quantity": 1}
  ],
  "expected_budget": {"amount": 15000, "currency": "SGD", "source": "extracted"},
  "warnings": []
}
```

| Field | Type | Notes |
|---|---|---|
| `ingest_id` | string | Must persist — required as `ingest_id` on Call 2 |
| `user_id` | string | Echo of request `user_id` |
| `user_requirement_summary` | string | Deterministic summary of the submitted requirement; safe to display or embed in a Call 2 `query` |
| `tentative_start_date` / `tentative_end_date` | date \| null | Request date preferred; else extracted from text/file when confident; `null` if unknown |
| `needs_summary` | array | Structured needs from decomposition — display only, **not** ranked fleet recommendations |
| `needs_summary[].need_id` | string \| null | Optional stable id |
| `needs_summary[].description` | string | Human-readable need |
| `needs_summary[].equipment_hints` | string[] | Optional category/type hints |
| `needs_summary[].quantity` | int \| null | Optional quantity when known |
| `expected_budget` | object \| null | `null` if missing/uncertain — never invent client-side |
| `expected_budget.amount` | number | Extracted amount |
| `expected_budget.currency` | string \| null | ISO-like code when known (e.g. `SGD`) |
| `expected_budget.source` | string | Provenance marker, e.g. `"extracted"` |
| `warnings` | string[] | Soft issues (e.g. truncated summary); empty when none |

Not on this response: ranked assets, ML daily rates, `results_by_need` — those belong to a separate recommend/pricing flow, not this ingest call.

**Caveat worth knowing**: `ingest_id` and its underlying session are **process-local, in-memory** — they do not survive a Haystack restart/redeploy. Call 2 accepts an optional `kg_artifact_path` to reload the knowledge graph after a restart, but **this response does not return that path** — it is computed internally at ingest time and not currently exposed on the lean body. Until that's exposed, Spring Boot cannot use it and should simply re-ingest rather than relying on a stale `ingest_id`. Flagged as an open item below.

---

## `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations`

Multi-agent Q&A (vector search + knowledge-graph query + synthesis) scoped to one prior ingest.

**Request**

| Field | Type | Required | Notes |
|---|---|---|---|
| `user_id` | string | yes | Must match the `user_id` used at ingest |
| `ingest_id` | string | yes | From `/submitprojectspecification`'s response |
| `query` | string | yes | Natural-language question |
| `top_k` | int (1–50) | no | Retrieval depth override |
| `kg_artifact_path` | string | no | Reload KG-1 if the in-memory session was lost (see caveat above) |

**Response `200`**

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_a1b2c3d4",
  "query": "What excavator and soil conditions are specified?",
  "answer": "The project requires a 20-ton excavator suited for soft clay...",
  "sources_used": ["project_vector_search", "project_kg_query"],
  "research_hits": [{"content": "...", "score": 0.83, "meta": {}}],
  "graph_hits": [{"content": "...", "score": null, "meta": {}}],
  "tool_traces": [{"agent": "research", "tool": "project_vector_search", "query": "excavator soil", "hit_count": 3}],
  "research_notes": null,
  "graph_notes": null
}
```

**Error case**: `404 not_found` when `ingest_id` doesn't resolve to a live session (expired, wrong `user_id`, or lost to a restart — see caveat above).

---

## `POST /internal/v1/pricing/quote`

Synchronous, authoritative, guardrail-clamped price per asset for a proposed rental window — intended for checkout, not browse/recommend (recommend-time pricing already comes back on the ingest/recommend response separately). Resolves `category`/`condition`/`capacity`/`platform_height`/rate bounds **server-side** from `asset_id` — the request never supplies them.

**Request**

| Field | Type | Required | Notes |
|---|---|---|---|
| `rental_plan_id` | string | yes | Opaque identifier, echoed back — **not validated against Haystack's DB**; Spring Boot's own record |
| `start_date` | date | yes | Rental window start |
| `end_date` | date | yes | Rental window end; must be ≥ `start_date` |
| `distance_km` | float (≥ 0) | yes | Delivery distance for the whole request (one site assumed) |
| `items` | array | yes, ≥ 1 item | See below |
| `items[].item_id` | string | yes | Caller-defined identifier for correlating this item in the response |
| `items[].asset_id` | integer | yes | Real Haystack `Asset.id` primary key — **not** a string code |

**Request example**
```json
{
  "rental_plan_id": "plan_123",
  "start_date": "2026-09-01",
  "end_date": "2026-09-08",
  "distance_km": 18.4,
  "items": [
    { "item_id": "item_1", "asset_id": 1 },
    { "item_id": "item_2", "asset_id": 3 }
  ]
}
```

**Response `200`** (always `200` even if individual items fail — see per-item `error` below; only a systemic outage returns a non-2xx)

```json
{
  "rental_plan_id": "plan_123",
  "currency": "SGD",
  "deposit_rate": 0.30,
  "degraded": false,
  "results": [
    {
      "item_id": "item_1",
      "asset_id": 1,
      "daily_rate": 380.0,
      "total_price": 2660.0,
      "was_clamped": true,
      "min_daily_rate": 380.0,
      "max_daily_rate": 520.0,
      "model_version": "prod-2026-08-07",
      "degraded": false,
      "error": null
    }
  ],
  "warnings": []
}
```

| Field | Type | Notes |
|---|---|---|
| `currency` | string | Always `"SGD"` today |
| `deposit_rate` | float | Fixed constant (`0.30`); read from here rather than hardcoding a copy |
| `degraded` | bool | Top-level convenience flag = OR of every item's own `degraded` — not a shared resolution |
| `results[].daily_rate` / `total_price` | float \| null | `null` only when `error` is set |
| `results[].was_clamped` | bool \| null | Whether the model's raw output was outside `[min_daily_rate, max_daily_rate]` and got clamped |
| `results[].degraded` | bool \| null | This item's own read fell back to a secondary data source (still a real value, not fabricated) |
| `results[].error` | string \| null | Set (`"asset_not_found"`, `"unrecognized_category: ..."`) when this item couldn't be priced — every other pricing field is `null` on that item, but the rest of the batch still returns normally |

**Known, expected behavior — not a bug**: `was_clamped: true` is common for multi-day rentals today (a calibration characteristic being tracked internally, not a defect in this endpoint).

**Failure modes**:
- Per-item failure (bad `asset_id`, unrecognized category) → `200` with that item's `error` set, rest of the batch unaffected.
- Systemic failure (neither Haystack data source is reachable — cold start) → `500 internal_error`, no partial response; safe to retry.

---

## Open items — needs Spring Boot review before this is finalized

1. **Auth**: none of the routes above are authenticated yet. Confirm what network-level restriction (VPC, mTLS, IP allowlist, etc.) is protecting them in each environment until a real auth story lands.
2. **`ingest_id` session lifetime**: currently process-local/in-memory, lost on Haystack restart. Flag if your integration needs this to survive restarts — the fix (persisting sessions) isn't built yet.
3. **`kg_artifact_path` not returned by Call 1**: Call 2 accepts an optional `kg_artifact_path` to reload the knowledge graph after a Haystack restart, but the current `/submitprojectspecification` response doesn't include it (it's computed internally and never surfaced). Spring Boot cannot use this recovery path today — flag if you need it and we'll add the field to the lean response.

**Resolved**: `results[].error` field on `/internal/v1/pricing/quote` — kept as specified (`error: string | null`, values `"asset_not_found"` / `"unrecognized_category: ..."`, every other pricing field `null` on that item). It exists to satisfy the "clear per-item error, no failed batch" requirement locked before this endpoint was built. Flag directly to us if this shape doesn't fit your DTO once you're integrating — not blocking in the meantime.

---

## Change log

| Date | Note |
|------|------|
| 2026-08-12 (later) | Fixed endpoint paths (`/internal/v1/recommendations/submitprojectspecification`, `/internal/v1/recommendations/project-knowledge/getassetrecommendations` — table and headers previously said `/api/v1/...`) and rewrote the Call 1 response example/field table to match the live lean `IngestFromProjectSpecResponse` schema (`ingest_id`, `user_id`, `user_requirement_summary`, `tentative_start_date`, `tentative_end_date`, `needs_summary`, `expected_budget`, `warnings`) instead of a stale raw-indexing shape. Added open item on `kg_artifact_path` not being returned by Call 1. Cross-checked against the app team's own Spring-facing wire-contract notes. |
| 2026-08-12 | **S2a:** documented `Idempotency-Key` + `X-Correlation-Id` / `traceparent` conventions (process-local idempotency). |
| 2026-08-11 | Initial draft, compiled from `app/schemas/*.py` and `app/api/*.py` as of `feature/ml-6-internal-pricing-api`. Covers all 4 live routes Spring Boot calls. |
| 2026-08-11 (later) | Resolved the `results[].error` open item — kept as specified, no shape change. Dropped the Postman collection item — decided not to build one for this endpoint; the field tables and JSON examples in this doc are the integration reference. |
