# Contract: `POST /internal/v1/recommendations/submitprojectspecification`

| Field | Value |
|-------|--------|
| **Capability** | [`../spec.md`](../spec.md) (indexing) |
| **Design** | [`../design.md`](../design.md) |
| **Status** | **as-built** lean Call 1 + **full FR-IX-023** project-spec summary (S1a–S1e) |
| **DTO (as-built)** | `IngestFromProjectSpecResponse` (`app/schemas/indexing.py`) |
| **Standards** | OpenSpec behaviour · Spec-kit contract tables · OpenSPDD (prompt/spec before code) |

Live HTTP owner: **indexing** (not FR-010 recommend on the public route).  
Internal pipeline still: dual-branch index → DocumentStore write → mandatory KG-1 → project-knowledge session register (for Call 2).

---

## Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Tenant for meta + KG path |
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

## Error notes (`400`)

Error body shape: `{"error","message"}` (shared handlers).

| Case | Notes |
|------|--------|
| Missing `user_id` | Required for meta + KG path (FR-IX-021) |
| Unclassified / unsupported type | Outside MIME map → 400 (FR-IX-003) |
| Empty file bytes / empty combined sources | FR-IX-009 |
| Zero documents after classification (hard conversion failure) | FR-IX-013 |
| Zero written chunks | FR-IX-016 |
| KG hard-fail | No lean success body; no session register for that ingest |

---

## Call 2 handoff

Spring (or portal) stores `user_id` + `ingest_id` from this response, then calls:

`POST /internal/v1/recommendations/project-knowledge/getassetrecommendations`

See knowledge-graph contract [`project-knowledge-query.md`](../../knowledge-graph/contracts/project-knowledge-query.md).  
`user_requirement_summary` is for display / optional prompt embedding; **not** required on Call 2 when the session is live.
