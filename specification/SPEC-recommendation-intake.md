# Specification: Recommendation Intake (Free-text / File + LLM Decompose)

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD (stage slice) |
| **Status** | MVP contract revised (v0.2.0) — free-text/file intake; structured multi-need form **removed** as public UX |
| **Feature id** | `recommendation-intake` |
| **Workspace** | `/workspaces/haystack-fast-api` |
| **Application module** | `haystack-fast-api` |
| **Python package** | `app` |
| **Spec location** | `specification/SPEC-recommendation-intake.md` |
| **As-built modules** | `app/api/recommendations.py`, `app/schemas/recommendations.py`, `app/services/recommendations.py`, `app/services/need_decomposer.py` |
| **Tests** | `tests/test_recommendations_intake.py` |
| **Parent feature** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) |
| **Depends on** | [`SPEC-project.md`](./SPEC-project.md), [`SPEC-project-setup.md`](./SPEC-project-setup.md), [`01-domain.md`](./01-domain.md) |
| **Related** | [`SPEC-recommendation-intake-and-pipeline-front.md`](./SPEC-recommendation-intake-and-pipeline-front.md); [`SPEC-recommendation-postman-testing-guide.md`](./SPEC-recommendation-postman-testing-guide.md) (Postman); [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md); [`00-overview.md`](./00-overview.md) |
| **Audience** | Engineers and agents implementing or consuming intake; portal / Spring integrators |

**Read [`SPEC-project.md`](./SPEC-project.md) and [`SPEC-project-setup.md`](./SPEC-project-setup.md) first.** Domain language: [`01-domain.md`](./01-domain.md). Full recommendation pipeline (Asset SQL, availability, `predict_price()`, Haystack ranking) remains normative in the **parent** agentic SPEC.

---

## Document roles

| Document | Owns |
|----------|------|
| **This SPEC** | Public intake API, free-text/file accept, validation, LLM need decomposition interface, **quantity expansion**, response envelope with **exactly one ranked item per unit-need**, layering, intake tests |
| Parent agentic SPEC | End-to-end recommendation (candidates → availability → price → rank), catalog rules, demo scenarios, KG/agents, deployment |
| Dynamic pricing SPEC | Production `predict_price()` |
| Foundation `00` / `01` | Vision and ubiquitous language |

When intake and parent conflict on **public intake contract**, **this SPEC wins**; update both in the same change set.

---

## 1. Purpose

This specification defines the **Intake** stage of equipment recommendation in `haystack-fast-api`:

1. Accept **unstructured project input** from the portal: a **single free-text box** (`project_text`) and/or an **uploaded file** of unstructured text, plus optional **rental start/end dates**.
2. **Extract text** from the file when provided (MVP: plain text / markdown; PDF/DOCX via converters when enabled).
3. Run an **LLM need decomposer** that turns unstructured text into one or more **internal needs** (description, optional equipment hints, optional **quantity**).
4. **Expand quantity**: if a decomposed need has `quantity = N` (*N* ≥ 1), produce **N unit-needs**. `RecommendationItem` has **no** `quantity` field—each unit is its own response row.
5. Hand each unit-need to the recommendation pipeline (later stages) and return **`results_by_need`** where each entry has **exactly one** ranked `item` (or `null` if no match / stub).

**Corrected product intent:** MVP UI is **not** a repeatable structured “add another need” form. Structured needs exist only **after** LLM decomposition (internal).

---

## 2. Outcomes

When this specification is implemented and followed:

- A client can submit free-text and/or a file (+ optional ISO dates) to a documented REST endpoint.
- Empty text (and empty extract) fail with **`{"error","message"}`** and HTTP **400**.
- Successful responses include `recommendation_id`, echoed dates, and **`results_by_need`**.
- Each `results_by_need` entry has singular **`item`** (`RecommendationItem | null`)—**never** a multi-rank `items[]` list of alternatives.
- Quantity *N* from decomposition yields **N** unit-need rows (unique `need_id`s), each with at most one item.
- Routers stay thin; orchestration lives in services / pipelines.

---

## 3. Scope

### 3.1 In scope (MVP)

| Area | Requirement |
|------|-------------|
| **Endpoint** | `POST /api/v1/recommendations/from-project-spec` |
| **JSON body** | `project_text`, optional `start_date` / `end_date`, optional `options` |
| **Multipart** | `file` (+ optional `project_text`, dates, options fields) |
| **UI alignment** | Single free-text box **or** file upload (not multi-row structured form) |
| **Decompose** | LLM (or injectable interface) → internal needs with optional quantity |
| **Quantity expansion** | *N* → *N* unit-needs; no quantity on `RecommendationItem` |
| **Response** | `results_by_need[].item` singular; exactly one ranked choice when matched |
| **Validation** | Non-empty source text; date window; shared error JSON; unsupported media → 400 |
| **Layering** | `api` → `services` → (future) `pipelines` |
| **Tests** | Free-text happy path, empty, dates, quantity expansion, singular `item`, multipart text file |

### 3.2 Out of scope (this SPEC)

- Asset SQL, Booking availability, `predict_price()`, production Bedrock ranking fill (parent SPEC).
- Auth / JWT, payment, booking writes, add-to-cart.
- Portal React implementation (contract is API + UX description only).
- Returning top-*N* alternative equipment lists per need.

### 3.3 Stub behaviour (as-built until ranking wired)

- **Need decomposer:** injectable. Default `StubNeedDecomposer` treats the full source text as **one** need with `quantity = 1` (tests may inject multi-need / quantity &gt; 1). Production MUST use an LLM decomposer when ranking is live (parent).
- **Per unit-need result:** `item: null` + warning that candidate selection / availability / pricing / ranking are not wired yet.
- Removing the warning without providing a real ranked `item` is non-compliant once the pipeline is claimed complete.

---

## 4. Actors & user stories

| Actor | Goal |
|-------|------|
| **Customer / portal** | Paste project text or upload a file (+ optional dates) → recommendations |
| **Intake / decomposer** | Turn unstructured text into unit-needs (after quantity expansion) |
| **Recommendation pipeline** | For each unit-need, select **exactly one** equipment recommendation (or none) |

### User stories

1. **As a customer**, I paste a project description into one free-text box so that I do not have to fill a multi-row equipment form.
2. **As a customer**, I upload a project file so that the same pipeline decomposes it into equipment needs.
3. **As the system**, when the text implies two scissors lifts, I create **two** unit-needs and return **two** rows, each with **one** `RecommendationItem` (no quantity field on the item).
4. **As a client**, when text is empty or dates are invalid, I receive **400** with a shared error shape.

---

## 5. Functional requirements

| ID | Requirement |
|----|-------------|
| **FR-I-001** | The service MUST accept `POST /api/v1/recommendations/from-project-spec` as JSON and/or `multipart/form-data` with unstructured **`project_text`** and/or **`file`**, plus optional `start_date` / `end_date` (ISO 8601 date). (Parent **FR-001**, **FR-002**) |
| **FR-I-002** | At least one non-empty source of text is required after combining/extracting `project_text` and file content; otherwise **400**. |
| **FR-I-003** | MVP file types: `text/plain`, `text/markdown` (and `text/*` plain extracts). PDF/DOCX SHOULD be supported via converters when enabled; unsupported types → **400**. |
| **FR-I-004** | The service MUST run a **need decomposer** (LLM in production) that maps source text → one or more internal needs (`need_id`, `description`, optional `equipment_hints`, optional `quantity` ≥ 1). |
| **FR-I-005** | **Quantity expansion:** for each internal need with `quantity = N`, expand into **N unit-needs** before ranking. **`RecommendationItem` MUST NOT include `quantity`.** (Parent **FR-006**) |
| **FR-I-006** | Unit-need `need_id` scheme: if *N* = 1, use `base_need_id`; if *N* &gt; 1, use `{base_need_id}__u{i}` for *i* = 1..*N*. |
| **FR-I-007** | Successful responses MUST use `results_by_need` with one entry per **unit-need**, order preserved. |
| **FR-I-008** | Each entry MUST expose singular **`item`**: exactly **one** `RecommendationItem` when a match is selected, or **`null`** when no match / pipeline stub. MUST NOT return an array of ranked alternatives per need. (Parent **FR-007**) |
| **FR-I-009** | Optional `options.include_pricing` (default `true`) MUST be accepted. |
| **FR-I-010** | If both dates are present, `end_date` MUST be on or after `start_date`; otherwise **400**. |
| **FR-I-011** | Errors use `{"error","message"}`; validation and empty extract → **400**. |
| **FR-I-012** | Routers stay thin; no SQL/Haystack graph in handlers. Async handlers MUST still **await** an offloaded call to the sync recommendation service (`run_in_threadpool` or equivalent) so pipeline/LLM I/O does not block the ASGI event loop (see pipeline **FR-P-012**). |
| **FR-I-013** | Public structured `needs[]` / “add another need” form body is **not** the MVP contract (removed). |
| **FR-I-014** | When a selected item includes pricing, payload fields follow pipeline **FR-P-011**: `daily_rate`, `total_price` (estimated total for the request duration), `currency`, `deposit_rate`, `model_version`, `explanation`. MUST NOT include fabricated `weekly_rate`. |

---

## 6. API contract (normative)

### 6.1 Recommend from project specification

`POST /api/v1/recommendations/from-project-spec`

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

#### Success response `200`

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

This section is a **verification runbook** for exercising the live intake API. It does **not** replace automated acceptance tests in `tests/test_recommendations_intake.py` or the GIVEN/WHEN/THEN criteria in §9.

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

1. **Given** non-empty `project_text` and valid dates, **when** `POST .../from-project-spec`, **then** `200`, `recommendation_id` starts with `rec_`, dates echoed, `results_by_need` present; each entry has key **`item`** (not `items`).
2. **Given** empty / whitespace `project_text` and no file, **when** posted, **then** `400` shared error shape.
3. **Given** `end_date` before `start_date`, **when** posted, **then** `400`.
4. **Given** a decomposer that returns one need with `quantity = 2`, **when** recommend runs, **then** `results_by_need` has **length 2**, ids follow `__u1` / `__u2`, and neither `item` object contains `quantity`.
5. **Given** a decomposer that returns two needs with quantity 1, **when** recommend runs, **then** two independent `need_id`s, each with singular `item`.
6. **Given** plain-text multipart file with content, **when** posted, **then** `200` and at least one unit-need result.
7. **Given** pipeline stub, **when** recommend runs, **then** each `item` is `null` and warnings are non-empty.

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

When the public intake contract changes, update **this file**, parent intake sections, and as-built code/tests in the same change set.
