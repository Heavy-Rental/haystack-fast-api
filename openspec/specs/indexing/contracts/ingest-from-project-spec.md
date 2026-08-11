# Contract: `POST /internal/v1/recommendations/submitprojectspecification`

| Field | Value |
|-------|--------|
| **Capability** | [`../spec.md`](../spec.md) (indexing) |
| **Design** | [`../design.md`](../design.md) |
| **Status** | **as-built lean public body (S1a)** + **TARGET** full FR-IX-023 (`needs_summary[]`, dates, budget) |
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
| `start_date` / `end_date` | no | Window valid if both set; **TARGET** may echo as `tentative_*` later |
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
| `warnings` | string[] | Soft issues (e.g. truncated summary, conversion soft warnings); empty when none |

### Example (as-built lean)

```json
{
  "ingest_id": "ing_a1b2c3d4e5f6",
  "user_id": "user_demo",
  "user_requirement_summary": "Indoor elevated work ~8m; need scissors lift on soft clay.",
  "warnings": []
}
```

### Not on public body (still executed internally)

| Concern | Where |
|---------|--------|
| Chunk previews, counts, `data_kind`, mime/filenames | Indexing pipeline + session `meta` |
| `kg_built`, node/rel counts, artifact path, transforms | KG runner + session registry |
| Session DocumentStore + KG-1 | `ProjectKnowledgeSession` for Call 2 |

### As-built gaps vs full FR-IX-023 TARGET

No structured `needs_summary[]`, no `tentative_start_date` / `tentative_end_date`, no `expected_budget` on the live lean body yet.

---

## Success response `200` — TARGET full FR-IX-023 (later)

Additive enrichment of lean body (or superseding structured fields). Default **SHOULD** stay compact.

| Field | Type | Notes |
|-------|------|--------|
| `needs_summary[]` | array | Project-spec implied needs |
| `needs_summary[].description` | string | Human-readable need |
| `needs_summary[].equipment_hints` | string[] | Optional |
| `needs_summary[].quantity` | int \| null | Optional |
| `needs_summary[].need_id` | string \| null | Optional stable id for Call 3 |
| `tentative_start_date` / `tentative_end_date` | date \| null | Request preferred, else extract |
| `expected_budget` | object \| null | Extract only; **never invent** |

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
