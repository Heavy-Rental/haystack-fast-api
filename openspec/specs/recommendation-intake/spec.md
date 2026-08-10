# Recommendation Intake Specification

| Field | Value |
|-------|--------|
| **Status** | **Deferred** for recommend envelope (`results_by_need`); **live** HTTP is indexing + mandatory KG |
| **Feature id** | `recommendation-intake` |
| **Standards** | OpenSpec · Spec-kit user stories · OpenSPDD (behaviour only; design is light) |
| **As-built modules (live HTTP)** | `app/api/recommendations.py`, `app/services/indexing.py`, `app/schemas/indexing.py`, `app/pipelines/indexing/*` |
| **As-built modules (recommend reattach / service)** | `app/schemas/recommendations.py`, `app/services/recommendations.py`, `app/services/need_decomposer.py`, `app/pipelines/intake_front.py` |
| **Tests** | `tests/test_recommendations_intake.py` (**HTTP ingest**); recommend service tests in `tests/test_recommend_pipeline_mvp.py` |
| **Parent** | [`../equipment-recommendation/spec.md`](../equipment-recommendation/spec.md) |
| **Live route authority** | [`../indexing/spec.md`](../indexing/spec.md) · KG: [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md) |
| **Related** | [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md); [`../../AGENTS.md`](../../AGENTS.md) Path C |
| **Legacy source** | `specification/SPEC-recommendation-intake.md` |

**Read** [`../../project.md`](../../project.md) and [`../project-setup/spec.md`](../project-setup/spec.md) first. Domain language: [`../domain/spec.md`](../domain/spec.md).

---

## Document roles

| Document | Owns |
|----------|------|
| [`../indexing/spec.md`](../indexing/spec.md) | **Live** public route behaviour and **ingest** response shape |
| **This capability** | Request body shapes; validation notes; **deferred** recommend response (`results_by_need` / singular `item`) for reattach; historical intake narrative |
| [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md) | FR-010.1–8 **service-level** recommend graph |
| Parent equipment-recommendation | End-to-end product vision, catalog, target KG |
| Dynamic pricing | Production `predict_price()` |

**Conflict rule:** For the **live** HTTP response of `POST .../from-project-spec`, the **indexing capability wins**. Sections marked **deferred** describe the pre-reroute / reattach recommend contract and MUST NOT be treated as current as-built HTTP behaviour.

---

## Live as-built (HTTP) — pointer

**Default path today:**

```text
POST /from-project-spec (user_id required)
  → IndexingIngestService
  → dual-branch index → final_doc_joiner → embed → write
  → mandatory KG after post-join chunks
  → IngestFromProjectSpecResponse (user_*, ingest_id, data_kind, documents_written, kg_*)
```

**Normative live contract:** [`../indexing/spec.md`](../indexing/spec.md) · KG: [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md) · Map: [`../../AGENTS.md`](../../AGENTS.md).  
Manual tests: [`../../../postman/README.md`](../../../postman/README.md) (**include `user_id`**).

Deferred API tables below that show `recommendation_id` / `results_by_need` apply only when recommend is reattached to HTTP.

---

## Purpose

### Live (indexing)

1. Accept project input: free-text and/or file (+ optional dates).
2. Classify structured vs unstructured; convert; vectorize; write to DocumentStore.
3. Return **ingest** metadata (`ingest_id`, `data_kind`, chunk/write counts, previews).

### Deferred (recommend reattach)

Historical / target intake for equipment recommendation:

1. Accept **unstructured project input** from the portal.
2. **Extract text** / convert files.
3. **LLM need decomposer** → internal needs (optional quantity).
4. **Expand quantity** → unit-needs; no quantity on `RecommendationItem`.
5. Return **`results_by_need`** with singular **`item`** per unit-need.

**Product intent (unchanged):** MVP UI is **not** a repeatable structured “add another need” form.

---

## Outcomes

### Live

- Client can submit free-text and/or file (+ optional ISO dates).
- Empty / unsupported / unclassifiable input → **400** shared error JSON.
- Success → **`ingest_id`**, `data_kind`, `documents_written`, chunk previews with `has_embedding` (see indexing capability).
- Routers stay thin; orchestration in services / pipelines.

### Deferred (recommend)

- Success would include `recommendation_id`, echoed dates, **`results_by_need`** with singular **`item`**.
- Quantity *N* → *N* unit-need rows. Not returned by the **default** HTTP path until reattach.

---

## Scope

### In scope (live HTTP)

| Area | Requirement |
|------|-------------|
| **Endpoint** | `POST /api/v1/recommendations/from-project-spec` |
| **JSON / multipart request** | Same fields as before (`project_text`, `file`, dates, options) + **`user_id`** (live) |
| **Pipeline** | Indexing (see indexing capability) |
| **Response** | `IngestFromProjectSpecResponse` |
| **Tests** | `tests/test_recommendations_intake.py` (ingest) |

### Deferred (recommend reattach)

| Area | Notes |
|------|--------|
| Decompose + quantity expansion | Service-level `RecommendationService` / `intake_front` |
| Response `results_by_need[].item` | Documented in deferred API tables |
| FR-I-004 … FR-I-008, FR-I-014 | Apply when recommend is reattached |

### Out of scope (this capability)

- Asset SQL, Booking availability, production Bedrock ranking fill (parent / pipeline).
- Auth / JWT, payment, booking writes, add-to-cart.
- Knowledge graph (parent + knowledge-graph capability; live KG is mandatory on indexing path).
- Portal React implementation.

---

## User Scenarios & Testing

### User Story 1 - Paste project text for index (Priority: P1) — LIVE

As a customer, I paste project text so the system **indexes** it (live) and later can recommend equipment (deferred).

**Independent Test:** `POST .../from-project-spec` with `user_id` + non-empty `project_text`; expect ingest response.

**Acceptance Scenarios:**

1. **Given** non-empty `project_text` and `user_id`, **When** `POST .../from-project-spec`, **Then** `200`, `ingest_id` starts with `ing_`, `data_kind=unstructured`, `documents_written` ≥ 1, `results_by_need` absent.
2. **Given** empty / whitespace `project_text` and no file, **When** posted, **Then** `400` shared error shape.

### User Story 2 - Upload project file (Priority: P1) — LIVE

As a customer, I upload a project file (txt/md/csv/…) so it is classified and vectorized.

**Independent Test:** multipart file with content + `user_id`.

**Acceptance Scenarios:**

1. **Given** plain-text or csv multipart file with content and `user_id`, **When** posted, **Then** `200` with matching `data_kind` and `documents_written` ≥ 1.

### User Story 3 - Quantity expansion to unit-needs (Priority: P2) — DEFERRED HTTP / service-level

As the system (deferred on HTTP), when text implies two scissors lifts, I create two unit-need rows each with one `RecommendationItem`.

**Independent Test:** Inject decomposer with `quantity=2` into `RecommendationService`; assert two rows.

**Acceptance Scenarios:**

1. **Given** a decomposer that returns one need with `quantity = 2`, **When** `RecommendationService` runs, **Then** `results_by_need` has **length 2**, ids follow `__u1` / `__u2`.
2. **Given** multi-need decomposer, **When** service runs, **Then** independent `need_id`s each with singular `item`.

### User Story 4 - Validation errors (Priority: P1) — LIVE

As a client, when text is empty or dates are invalid, I receive **400** with a shared error shape.

**Independent Test:** empty body, bad dates.

**Acceptance Scenarios:**

1. **Given** `end_date` before `start_date`, **When** posted, **Then** `400`.
2. **Given** missing required fields, **When** posted, **Then** `400` with `{"error","message"}`.

---

## Requirements

### Requirement: Accept from-project-spec (FR-I-001) — LIVE

The service MUST accept `POST /api/v1/recommendations/from-project-spec` as JSON and/or `multipart/form-data` with **`user_id`**, **`project_text`** and/or **`file`**, plus optional `user_name`, `start_date` / `end_date`.

#### Scenario: JSON free-text accepted
- **WHEN** a client posts JSON with non-empty `project_text` and required `user_id`
- **THEN** the request is accepted for the live indexing path

#### Scenario: Multipart file accepted
- **WHEN** a client posts multipart with `file` and/or `project_text` and required `user_id`
- **THEN** the request is accepted for the live indexing path

### Requirement: Non-empty source for recommend path (FR-I-002) — DEFERRED

On the recommend reattach path, non-empty source text after extract is required; empty → **400**.

#### Scenario: Empty source rejected on recommend path
- **WHEN** recommend reattach runs with empty extracted source
- **THEN** the path fails with **400** shared error shape

### Requirement: File types for recommend extract (FR-I-003) — SUPERSEDED LIVE / DEFERRED RECOMMEND-ONLY

For **live** HTTP, file-type support is owned by indexing (MIME map). Recommend-only extract rules (MVP plain text/markdown) remain deferred for reattach if distinct from indexing.

#### Scenario: Live MIME map wins
- **WHEN** a file is uploaded on the live route
- **THEN** indexing capability § file-type rules apply, not recommend-only MVP limits

### Requirement: Need decomposer (FR-I-004) — DEFERRED on HTTP; available service-level

The recommend path MUST decompose source text into internal needs (`need_id`, `description`, optional `equipment_hints`, optional `quantity` ≥ 1) via an injectable `NeedDecomposer` (stub or LLM).

#### Scenario: Stub decomposer one need
- **WHEN** default `StubNeedDecomposer` runs on non-empty text
- **THEN** a single internal need is produced from the full text (`quantity = 1`)

### Requirement: Quantity expansion (FR-I-005) — DEFERRED on HTTP

If a decomposed need has quantity *N* (*N* ≥ 1), the system MUST expand it into *N* unit-needs before ranking. `RecommendationItem` MUST NOT include `quantity`.

#### Scenario: Quantity two expands to two unit-needs
- **GIVEN** one need with `quantity = 2` and base id `need_1`
- **WHEN** expansion runs
- **THEN** unit-need ids are `need_1__u1` and `need_1__u2`

### Requirement: Unit-need id scheme (FR-I-006) — DEFERRED on HTTP

Unit-need ids: `base_id` when *N* = 1; `{base_id}__u{i}` for *i* = 1..*N* when *N* > 1. *N* < 1 is treated as 1.

#### Scenario: Single quantity keeps base id
- **GIVEN** quantity 1 and base id `need_2`
- **WHEN** expansion runs
- **THEN** the unit-need id is `need_2` (no `__u` suffix)

### Requirement: results_by_need response (FR-I-007) — DEFERRED — not live

Successful recommend responses MUST include `recommendation_id`, echoed dates, and `results_by_need` (one object per **unit-need**).

#### Scenario: Envelope present when recommend reattached
- **WHEN** recommend HTTP is reattached and succeeds
- **THEN** the body includes `recommendation_id` (prefix `rec_`) and `results_by_need` array

### Requirement: Singular item (FR-I-008) — DEFERRED — not live

Each `results_by_need` entry MUST expose singular **`item`** (`RecommendationItem | null`) — exactly one ranked choice or null. MUST NOT return multi-element ranked alternatives per need.

#### Scenario: No items array
- **WHEN** a unit-need result is assembled
- **THEN** the key is `item` (object or null), not `items[]`

### Requirement: Optional include_pricing (FR-I-009) — LIVE accept

Optional `options.include_pricing` (default `true`) MUST be accepted (ignored for ranking until reattach).

#### Scenario: Default include_pricing
- **WHEN** options omit `include_pricing`
- **THEN** the field defaults to `true` on the request model

### Requirement: Date window validation (FR-I-010) — LIVE

If both dates are present, `end_date` MUST be on or after `start_date`; otherwise **400**.

#### Scenario: End before start
- **GIVEN** `end_date` before `start_date` and non-empty source
- **WHEN** the request is posted
- **THEN** response is **400** with shared error shape

### Requirement: Shared error shape (FR-I-011) — LIVE

Errors use `{"error","message"}`; validation and empty/unclassified sources → **400**.

#### Scenario: Validation error shape
- **WHEN** validation fails
- **THEN** body is `{"error":"bad_request","message":"..."}` (or equivalent shared code)

### Requirement: Thin routers and threadpool (FR-I-012) — LIVE

Routers stay thin. Async handlers MUST **await** `run_in_threadpool` (or equivalent) for the sync service (currently **`IndexingIngestService`**; when recommend is reattached, **`RecommendationService`**).

#### Scenario: Sync work off event loop
- **WHEN** an async route handles a success path
- **THEN** the sync service runs via threadpool offload, not on the ASGI event loop

### Requirement: No public structured needs form (FR-I-013) — LIVE product

Public structured `needs[]` / “add another need” form body is **not** the MVP contract.

#### Scenario: from-needs not MVP
- **WHEN** clients seek structured multi-need intake as the public MVP
- **THEN** that contract is rejected; free-text/file is the product path

### Requirement: Pricing fields on selected item (FR-I-014) — DEFERRED on HTTP

When `include_pricing` is true and a match is selected, `item.pricing` MUST expose the deferred **PricingPayload** fields (see contracts below). MUST NOT expose fabricated `weekly_rate`.

#### Scenario: Pricing payload shape when selected
- **GIVEN** recommend reattach, `include_pricing=true`, and a ranked match
- **WHEN** the response is built
- **THEN** `item.pricing` includes `daily_rate`, `total_price`, `currency`, `deposit_rate`, `model_version`, `explanation` as applicable

### Requirement: Live success follows indexing (FR-I-015) — LIVE

**Live** successful responses MUST follow the indexing capability (`ingest_id`, …). MUST NOT require `results_by_need` on the default path.

#### Scenario: No results_by_need on live success
- **WHEN** live `POST .../from-project-spec` succeeds
- **THEN** the body is ingest-shaped and does not require `results_by_need`

---

## Deferred API contracts (recommend reattach)

### `POST /api/v1/recommendations/from-project-spec`

#### JSON (`Content-Type: application/json`)

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `user_id` | string | **yes (live)** | Required on live indexing path |
| `project_text` | string | **yes** for JSON-only | Non-empty after strip |
| `start_date` | date \| null | no | |
| `end_date` | date \| null | no | ≥ `start_date` if both set |
| `options.include_pricing` | boolean | no | Default `true` |

#### Multipart (`multipart/form-data`)

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `user_id` | string | **yes (live)** | |
| `file` | file | one of file / project_text | Unstructured project document |
| `project_text` | string | one of file / project_text | Optional supplement or sole text |
| `start_date` / `end_date` | string date | no | |
| `include_pricing` | boolean / string | no | Form field; default true |

When both `file` and `project_text` are present, source text is **file text first**, then a blank line, then `project_text` (both non-empty parts concatenated). **Locked** concatenation order.

#### Example request (JSON)

```json
{
  "project_text": "Indoor elevated work about 8m for two scissors lifts; also one excavator for trench work next to the site.",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "options": { "include_pricing": true }
}
```

#### Success response `200` — **live (as-built)**

See indexing capability: `IngestFromProjectSpecResponse` (`ingest_id`, `data_kind`, `documents_written`, …).

#### Success response `200` — **deferred (recommend reattach)**

| Field | Type | Notes |
|-------|------|--------|
| `recommendation_id` | string | `rec_` + hex |
| `start_date` / `end_date` | date \| null | Echo |
| `results_by_need` | array | One object per **unit-need** |

**NeedResult**

| Field | Type | Notes |
|-------|------|--------|
| `need_id` | string | After quantity expansion |
| **`item`** | **RecommendationItem \| null** | **Exactly one ranked choice, or null. Not a list.** |
| `warnings` | string[] | Stub / no-match / decompose notes |

**RecommendationItem** (no `quantity`)

| Field | Type |
|-------|------|
| `equipment_type` | string \| null |
| `asset_id` | string \| null |
| `rank` | integer \| null (use `1` when selected) |
| `rationale` | string \| null |
| `pricing` | PricingPayload \| null |
| `availability` | string (`available` \| `unavailable` \| `unknown` …) |

**PricingPayload** (when `include_pricing` and a match is selected; see pipeline **FR-P-011**)

| Field | Type | Notes |
|-------|------|--------|
| `daily_rate` | number \| null | Predicted price **per day for the requested duration window** (duration is a model input). Do not re-scale for a different window — call recommend / `predict_price` again. |
| `total_price` | number \| null | Estimated total for that window: `daily_rate × duration_days` (mockup “Estimated total”). |
| `currency` | string | Default **SGD** |
| `deposit_rate` | number | Default **0.30** (FR-024) |
| `model_version` | string \| null | e.g. experimental or fallback id |
| `explanation` | string \| null | Human-readable; SHOULD note duration scope |

MUST NOT expose **`weekly_rate`** fabricated as `daily_rate × 7`.

#### Example response (quantity expansion: 2 scissors → 2 unit-needs; excavator → 1; stub items)

```json
{
  "recommendation_id": "rec_a1b2c3...",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "results_by_need": [
    {
      "need_id": "need_1__u1",
      "item": null,
      "warnings": [
        "Intake accepted; candidate selection, availability, pricing, and ranking are not wired yet (stub pipeline)."
      ]
    },
    {
      "need_id": "need_1__u2",
      "item": null,
      "warnings": [
        "Intake accepted; candidate selection, availability, pricing, and ranking are not wired yet (stub pipeline)."
      ]
    },
    {
      "need_id": "need_2",
      "item": null,
      "warnings": [
        "Intake accepted; candidate selection, availability, pricing, and ranking are not wired yet (stub pipeline)."
      ]
    }
  ]
}
```

When ranking is live, each `item` is a single object (e.g. one Scissors Lift recommendation), **not** an array of ranked alternatives.

#### Error `400`

```json
{ "error": "bad_request", "message": "human-readable validation or business rule failure" }
```

---

## Quantity expansion algorithm

```text
for each decomposed need with base_id, description, hints, quantity N:
  if N < 1: treat as 1
  if N == 1:
    emit unit-need(need_id=base_id, ...)
  else:
    for i in 1..N:
      emit unit-need(need_id=f"{base_id}__u{i}", ...)
```

---

## Deferred design notes (recommend path)

```text
  project_text and/or file
           │
           ▼
  resolve source text (400 if empty)
           │
           ▼
  NeedDecomposer (LLM / stub) → internal needs (+ quantity)
           │
           ▼
  expand quantity → unit-needs
           │
           ▼
  per unit-need: pipeline (stub or real) → item | null
           │
           ▼
  RecommendFromProjectSpecResponse
```

### As-built file map (recommend reattach / service)

| Path | Role |
|------|------|
| `app/schemas/recommendations.py` | Request/response models; singular `item` |
| `app/services/need_decomposer.py` | `NeedDecomposer` protocol, `StubNeedDecomposer` |
| `app/services/recommendations.py` | Resolve text, decompose, expand, assemble |
| `app/api/recommendations.py` | JSON + multipart routes (live → indexing) |
| `tests/test_recommendations_intake.py` | Live HTTP ingest acceptance tests |

---

## Manual testing notes

> **Live HTTP (indexing):** use [`../../../postman/README.md`](../../../postman/README.md) and collection `postman/Indexing-Pipeline.postman_collection.json`. Expect `ingest_id` / `data_kind` / `documents_written`, **not** `recommendation_id` / `results_by_need`.
>
> **Deferred recommend Postman:** valid again only after reattach. See [`../../../docs/testing/recommendation-postman-testing-guide.md`](../../../docs/testing/recommendation-postman-testing-guide.md) when present.

Automated live HTTP: `tests/test_recommendations_intake.py`. Recommend service: `tests/test_recommend_pipeline_mvp.py`.

---

## Open questions

| # | Question | Status |
|---|----------|--------|
| 1 | LLM model id / Bedrock vs other for production decomposer | Parent open questions / Day 4 |
| 2 | PDF/DOCX converters in first demo week | SHOULD; plain text MVP minimum (live now via indexing MIME map for broader types) |
| 3 | Concatenation order when both file and project_text present | **Locked:** file then project_text |

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-05 | Initial as-built structured `from-needs` intake |
| **0.2.0** | 2026-08-05 | **Breaking:** free-text/file MVP; LLM decompose; quantity expansion; singular `item` per unit-need; remove public structured multi-need form |
| **0.2.1** | 2026-08-05 | Added Manual testing (Postman / Swagger) verification runbook |
| **0.3.0** | 2026-08-06 | **PR review:** document `PricingPayload` (`daily_rate` + `total_price`, no `weekly_rate`); **FR-I-012** threadpool offload; **FR-I-014** pricing fields |
| **0.4.0** | 2026-08-07 | Spec reconcile: live = indexing; recommend deferred |
| **0.5.0** | 2026-08-07 | Sequential map; live requires `user_id`; mandatory KG fields |
| **1.0.0** | 2026-08-10 | Migrated to OpenSpec Requirement/Scenario under `openspec/specs/recommendation-intake/` |

When the **live** public contract changes, update **indexing + knowledge-graph** first, then this file’s pointers.

**Reading order:** [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md) · [`../../AGENTS.md`](../../AGENTS.md) · [Next: Pipeline (deferred path) →](../recommendation-pipeline/spec.md)
