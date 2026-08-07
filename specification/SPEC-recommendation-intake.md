# Specification: Recommendation Intake (Free-text / File + LLM Decompose)

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (stage slice) |
| **Status** | **Breaking (0.5.0):** Live route = **indexing + mandatory KG** ([`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md), [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md)); requires **`user_id`**. Recommend `results_by_need` below is **deferred**. Sequential map: [`README.md`](./README.md). |
| **Feature id** | `recommendation-intake` |
| **Workspace** | `/workspaces/haystack-fast-api` |
| **Application module** | `haystack-fast-api` |
| **Python package** | `app` |
| **Spec location** | `specification/SPEC-recommendation-intake.md` |
| **As-built modules (live HTTP)** | `app/api/recommendations.py`, `app/services/indexing.py`, `app/schemas/indexing.py`, `app/pipelines/indexing/*` |
| **As-built modules (recommend reattach / service)** | `app/schemas/recommendations.py`, `app/services/recommendations.py`, `app/services/need_decomposer.py`, `app/pipelines/intake_front.py` |
| **Tests** | `tests/test_recommendations_intake.py` (**HTTP ingest**); recommend service tests in `tests/test_recommend_pipeline_mvp.py` |
| **Parent feature** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) |
| **Depends on** | [`SPEC-project.md`](./SPEC-project.md), [`SPEC-project-setup.md`](./SPEC-project-setup.md), [`01-domain.md`](./01-domain.md) |
| **Related** | [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) (**live route**); [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md); [`../postman/README.md`](../postman/README.md) (live Postman); [`SPEC-recommendation-postman-testing-guide.md`](./SPEC-recommendation-postman-testing-guide.md) (**deferred** recommend Postman); [`00-overview.md`](./00-overview.md) |
| **Audience** | Engineers and agents implementing or consuming intake; portal / Spring integrators |

**Read [`SPEC-project.md`](./SPEC-project.md) and [`SPEC-project-setup.md`](./SPEC-project-setup.md) first.** Domain language: [`01-domain.md`](./01-domain.md).

---

## Document roles

| Document | Owns |
|----------|------|
| [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) | **Live** public route behaviour and **ingest** response shape |
| **This SPEC** | Request body shapes; validation notes; **deferred** recommend response (`results_by_need` / singular `item`) for reattach; historical intake narrative |
| [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) | FR-010.1–8 **service-level** recommend graph |
| Parent agentic SPEC | End-to-end product vision, catalog, target KG |
| Dynamic pricing SPEC | Production `predict_price()` |
| Foundation `00` / `01` | Vision and ubiquitous language |

**Conflict rule:** For the **live** HTTP response of `POST .../from-project-spec`, the **indexing SPEC wins**. Sections in this file marked **deferred** describe the pre-reroute / reattach recommend contract and MUST NOT be treated as current as-built HTTP behaviour.

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

**Normative live contract:** [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) · KG: [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md) · Map: [`README.md`](./README.md).  
Manual tests: [`../postman/README.md`](../postman/README.md) (**include `user_id`**).

§6.1 tables that show `recommendation_id` / `results_by_need` are **deferred** (reattach only).

---

## 1. Purpose

### 1.1 Live (indexing)

1. Accept project input: free-text and/or file (+ optional dates).
2. Classify structured vs unstructured; convert; vectorize; write to DocumentStore.
3. Return **ingest** metadata (`ingest_id`, `data_kind`, chunk/write counts, previews).

### 1.2 Deferred (recommend reattach)

Historical / target intake for equipment recommendation:

1. Accept **unstructured project input** from the portal.
2. **Extract text** / convert files.
3. **LLM need decomposer** → internal needs (optional quantity).
4. **Expand quantity** → unit-needs; no quantity on `RecommendationItem`.
5. Return **`results_by_need`** with singular **`item`** per unit-need.

**Product intent (unchanged):** MVP UI is **not** a repeatable structured “add another need” form.

---

## 2. Outcomes

### 2.1 Live

- Client can submit free-text and/or file (+ optional ISO dates).
- Empty / unsupported / unclassifiable input → **400** shared error JSON.
- Success → **`ingest_id`**, `data_kind`, `documents_written`, chunk previews with `has_embedding` (see indexing SPEC).
- Routers stay thin; orchestration in services / pipelines.

### 2.2 Deferred (recommend)

- Success would include `recommendation_id`, echoed dates, **`results_by_need`** with singular **`item`**.
- Quantity *N* → *N* unit-need rows. Not returned by the **default** HTTP path until reattach.

---

## 3. Scope

### 3.1 In scope (live HTTP)

| Area | Requirement |
|------|-------------|
| **Endpoint** | `POST /api/v1/recommendations/from-project-spec` |
| **JSON / multipart request** | Same fields as before (`project_text`, `file`, dates, options) |
| **Pipeline** | Indexing (see indexing SPEC) |
| **Response** | `IngestFromProjectSpecResponse` |
| **Tests** | `tests/test_recommendations_intake.py` (ingest) |

### 3.2 Deferred (recommend reattach)

| Area | Notes |
|------|--------|
| Decompose + quantity expansion | Service-level `RecommendationService` / `intake_front` |
| Response `results_by_need[].item` | Documented in §6 deferred tables |
| FR-I-004 … FR-I-008, FR-I-014 | Apply when recommend is reattached |

### 3.3 Out of scope (this SPEC)

- Asset SQL, Booking availability, production Bedrock ranking fill (parent / pipeline SPEC).
- Auth / JWT, payment, booking writes, add-to-cart.
- Knowledge graph (parent §11; indexing tasks T020).
- Portal React implementation.

---

## 4. Actors & user stories

| Actor | Goal |
|-------|------|
| **Customer / portal** | Submit project text/file → **today:** ingest/index; **target:** recommendations |
| **Indexing pipeline** | Classify, convert, vectorize, write (live) |
| **Intake / decomposer** | Turn text into unit-needs (**deferred** on HTTP) |
| **Recommendation pipeline** | One equipment choice per unit-need (**service-level / deferred HTTP**) |

### User stories

1. **As a customer**, I paste project text so the system **indexes** it (live) and later can recommend equipment (deferred).
2. **As a customer**, I upload a project file (txt/md/csv/…) so it is classified and vectorized.
3. **As the system (deferred)**, when text implies two scissors lifts, I create two unit-need rows each with one `RecommendationItem`.
4. **As a client**, when text is empty or dates are invalid, I receive **400** with a shared error shape.

---

## 5. Functional requirements

### 5.1 Live (HTTP) — also see indexing SPEC FR-IX-*

| ID | Requirement |
|----|-------------|
| **FR-I-001** | The service MUST accept `POST /api/v1/recommendations/from-project-spec` as JSON and/or `multipart/form-data` with **`user_id`**, **`project_text`** and/or **`file`**, plus optional `user_name`, `start_date` / `end_date`. |
| **FR-I-009** | Optional `options.include_pricing` (default `true`) MUST be accepted (ignored for ranking until reattach). |
| **FR-I-010** | If both dates are present, `end_date` MUST be on or after `start_date`; otherwise **400**. |
| **FR-I-011** | Errors use `{"error","message"}`; validation and empty/unclassified sources → **400**. |
| **FR-I-012** | Routers stay thin. Async handlers MUST **await** `run_in_threadpool` (or equivalent) for the sync service (currently **`IndexingIngestService`**). |
| **FR-I-013** | Public structured `needs[]` / “add another need” form body is **not** the MVP contract. |
| **FR-I-015** | **Live** successful responses MUST follow the indexing SPEC (`ingest_id`, …). MUST NOT require `results_by_need` on the default path. |

### 5.2 Deferred (recommend reattach)

| ID | Requirement | Status |
|----|-------------|--------|
| **FR-I-002** | Non-empty source after extract for recommend path | Deferred |
| **FR-I-003** | File types for recommend extract (expanded types now via indexing MIME map) | Superseded for live by indexing §3; deferred for recommend-only rules |
| **FR-I-004** | Need decomposer | Deferred on HTTP; available service-level |
| **FR-I-005** | Quantity expansion | Deferred on HTTP |
| **FR-I-006** | Unit-need id scheme | Deferred on HTTP |
| **FR-I-007** | `results_by_need` response | **Deferred** — not live |
| **FR-I-008** | Singular `item` | **Deferred** — not live |
| **FR-I-014** | Pricing fields on selected item | Deferred on HTTP |

---

## 6. API contract

### 6.1 `POST /api/v1/recommendations/from-project-spec`

#### JSON (`Content-Type: application/json`)

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `project_text` | string | **yes** for JSON-only | Non-empty after strip |
| `start_date` | date \| null | no | |
| `end_date` | date \| null | no | ≥ `start_date` if both set |
| `options.include_pricing` | boolean | no | Default `true` |

#### Multipart (`multipart/form-data`)

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `file` | file | one of file / project_text | Unstructured project document |
| `project_text` | string | one of file / project_text | Optional supplement or sole text |
| `start_date` / `end_date` | string date | no | |
| `include_pricing` | boolean / string | no | Form field; default true |

When both `file` and `project_text` are present, source text is **file text first**, then a blank line, then `project_text` (both non-empty parts concatenated).

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

See [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) §5: `IngestFromProjectSpecResponse` (`ingest_id`, `data_kind`, `documents_written`, …).

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

After LLM decompose might yield: scissors qty 2, excavator qty 1 → three unit-needs:

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

## 7. Design

### 7.1 Flow

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

### 7.2 As-built file map

| Path | Role |
|------|------|
| `app/schemas/recommendations.py` | Request/response models; singular `item` |
| `app/services/need_decomposer.py` | `NeedDecomposer` protocol, `StubNeedDecomposer` |
| `app/services/recommendations.py` | Resolve text, decompose, expand, assemble |
| `app/api/recommendations.py` | JSON + multipart routes |
| `tests/test_recommendations_intake.py` | Intake acceptance tests |

### 7.3 Quantity expansion algorithm

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

## 8. Manual testing (Postman / Swagger)

> **Live HTTP (indexing):** use [`../postman/README.md`](../postman/README.md) and collection `postman/Indexing-Pipeline.postman_collection.json`. Expect `ingest_id` / `data_kind` / `documents_written`, **not** `recommendation_id` / `results_by_need`.
>
> **Below:** historical / **deferred recommend** Postman steps (valid again only after reattach). Also see [`SPEC-recommendation-postman-testing-guide.md`](./SPEC-recommendation-postman-testing-guide.md) (deferred banner).

This section is a **verification runbook**. Automated live HTTP tests: `tests/test_recommendations_intake.py`. Recommend service tests: `tests/test_recommend_pipeline_mvp.py`.

### 8.1 Start the server

From the application module (`haystack-fast-api/`, where `pyproject.toml` and `app/` live):

```bash
cd haystack-fast-api
uv sync --all-groups   # first time / after dependency changes
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

| Resource | URL |
|----------|-----|
| **Base URL** | `http://localhost:8000` |
| Health | `http://localhost:8000/health` |
| OpenAPI / Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |

**Auth:** none required on recommend routes yet (project constitution).

### 8.2 Smoke check (optional)

| Field | Value |
|-------|--------|
| Method | `GET` |
| URL | `http://localhost:8000/health` |

Expect **200** with `status` / `database` fields. Intake does not require Postgres for the current stub path; health may report `degraded` if the DB is down without blocking intake.

### 8.3 Request A — free-text (JSON) happy path

| Field | Value |
|-------|--------|
| Method | **POST** |
| URL | `http://localhost:8000/api/v1/recommendations/from-project-spec` |

**Headers**

| Key | Value |
|-----|--------|
| `Content-Type` | `application/json` |

In Postman: **Body → raw → JSON** (Postman usually sets `Content-Type` for you).

**Body**

```json
{
  "project_text": "Indoor elevated work about 8m; need scissors lifts for fit-out.",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "options": {
    "include_pricing": true
  }
}
```

**Expect**

- Status: **200**
- `recommendation_id` starts with `rec_`
- Dates echoed
- `results_by_need` is an array
- Each row has singular **`item`** (not `items`)
- **As-built stub:** `item` is `null` and `warnings` includes the stub-pipeline message

Example shape (stub):

```json
{
  "recommendation_id": "rec_...",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "results_by_need": [
    {
      "need_id": "need_1",
      "item": null,
      "warnings": [
        "Intake accepted; candidate selection, availability, pricing, and ranking are not wired yet (stub pipeline)."
      ]
    }
  ]
}
```

### 8.4 Request B — file upload (multipart)

| Field | Value |
|-------|--------|
| Method | **POST** |
| URL | `http://localhost:8000/api/v1/recommendations/from-project-spec` |

**Body → form-data** (Postman)

| Key | Type | Value |
|-----|------|--------|
| `file` | **File** | A `.txt` or `.md` file (e.g. contents: `Need one forklift for loading bay`) |
| `start_date` | Text | `2026-09-01` (optional) |
| `end_date` | Text | `2026-09-12` (optional) |
| `project_text` | Text | Optional extra free text |
| `include_pricing` | Text | `true` (optional; default true) |

Do **not** force `Content-Type: application/json`. Postman must send `multipart/form-data` with a boundary.

**Expect:** **200**, same response envelope as §8.3.

MVP file types: **plain text / markdown**. PDF/DOCX SHOULD return **400** until converters are enabled.

### 8.5 Negative cases

| Case | Body / setup | Expect |
|------|----------------|--------|
| Empty text | `{"project_text": "   "}` | **400** `{"error":"bad_request","message":"..."}` |
| Invalid dates | `start_date` after `end_date` + non-empty text | **400** shared error shape |
| Missing fields | `{}` | **400** |
| Empty multipart | form-data with no `file` and no `project_text` | **400** |

### 8.6 Suggested Postman collection

Folder: **Recommendation Intake**

1. `GET Health`
2. `POST From Project Spec (JSON)` — §8.3
3. `POST From Project Spec (file)` — §8.4
4. `POST Empty text (400)`
5. `POST Bad dates (400)`

**Environment variable**

| Variable | Example |
|----------|---------|
| `baseUrl` | `http://localhost:8000` |

Request URL: `{{baseUrl}}/api/v1/recommendations/from-project-spec`

### 8.7 What is live vs not (manual check)

| Behaviour | Visible in Postman now? |
|-----------|-------------------------|
| Accept free-text / file | **Yes** |
| Multi-need envelope with singular `item` | **Yes** |
| Stub warning + `item: null` | **Yes** (pipeline not filled yet) |
| Real LLM splitting “two scissors lifts” into 2 unit-needs | **No** — default `StubNeedDecomposer` = one need from full text |
| Quantity expansion (`need_1__u1`, `need_1__u2`) | Covered in **pytest** with injected decomposer; not default live stub |
| Real prices / ranked equipment in `item` | **No** — parent Days 3–5 |

### 8.8 Swagger UI alternative

1. Open `http://localhost:8000/docs`
2. Find **POST `/api/v1/recommendations/from-project-spec`**
3. **Try it out** with the JSON body from §8.3

Same server and contract as Postman.

### 8.9 Automated tests (pytest)

```bash
cd haystack-fast-api
uv run pytest tests/test_recommendations_intake.py -v
# full suite:
uv run pytest tests/ -v
```

---

## 9. Acceptance criteria

### 9.1 Live HTTP (indexing)

1. **Given** non-empty `project_text`, **when** `POST .../from-project-spec`, **then** `200`, `ingest_id` starts with `ing_`, `data_kind=unstructured`, `documents_written` ≥ 1, `results_by_need` absent.
2. **Given** empty / whitespace `project_text` and no file, **when** posted, **then** `400` shared error shape.
3. **Given** `end_date` before `start_date`, **when** posted, **then** `400`.
4. **Given** plain-text or csv multipart file with content, **when** posted, **then** `200` with matching `data_kind` and `documents_written` ≥ 1.
5. Full AC table: indexing SPEC §7.

### 9.2 Deferred / service-level recommend

6. **Given** a decomposer that returns one need with `quantity = 2`, **when** `RecommendationService` runs, **then** `results_by_need` has **length 2**, ids follow `__u1` / `__u2`.
7. **Given** multi-need decomposer, **when** service runs, **then** independent `need_id`s each with singular `item`.
8. Covered by `tests/test_recommend_pipeline_mvp.py` / pipeline SPEC.

---

## 10. Open questions

| # | Question | Status |
|---|----------|--------|
| 1 | LLM model id / Bedrock vs other for production decomposer | Parent open questions / Day 4 |
| 2 | PDF/DOCX converters in first demo week | SHOULD; plain text MVP minimum |
| 3 | Concatenation order when both file and project_text present | **Locked:** file then project_text |

---

## 11. Change control

| Version | Date | Notes |
|---------|------|--------|
| **0.1.0** | 2026-08-05 | Initial as-built structured `from-needs` intake |
| **0.2.0** | 2026-08-05 | **Breaking:** free-text/file MVP; LLM decompose; quantity expansion; singular `item` per unit-need; remove public structured multi-need form |
| **0.2.1** | 2026-08-05 | Added §8 Manual testing (Postman / Swagger) verification runbook |
| **0.3.0** | 2026-08-06 | **PR review:** document `PricingPayload` (`daily_rate` + `total_price`, no `weekly_rate`); **FR-I-012** threadpool offload; **FR-I-014** pricing fields |
| **0.4.0** | 2026-08-07 | Spec reconcile: live = indexing; recommend deferred |
| **0.5.0** | 2026-08-07 | Sequential map; live requires `user_id`; mandatory KG fields |

When the **live** public contract changes, update **indexing + knowledge-graph SPECs** first, then this file’s pointers.

---

**Reading order:** [← Knowledge graph](./SPEC-knowledge-graph.md) · [Map](./README.md) · [Next: Pipeline (deferred path) →](./SPEC-recommendation-pipeline.md)
