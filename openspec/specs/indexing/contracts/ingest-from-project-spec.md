# Contract: `POST /api/v1/recommendations/from-project-spec`

| Field | Value |
|-------|--------|
| **Capability** | [`../spec.md`](../spec.md) (indexing) |
| **Design** | [`../design.md`](../design.md) |
| **Status** | as-built (technical ingest) + **TARGET** project-spec summary (FR-IX-023) |
| **DTO (as-built)** | `IngestFromProjectSpecResponse` (`app/schemas/indexing.py`) |

Live HTTP owner: **indexing** (not FR-010 recommend on the public route).

---

## Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Tenant for meta + KG path |
| `user_name` | no | Echo / audit |
| `project_text` and/or `file` | one non-empty source | JSON-only needs non-empty text |
| `start_date` / `end_date` | no | Window valid if both set; **TARGET:** may feed `tentative_*` on response |
| `options` / `include_pricing` | no | Accepted; **boolean** for future recommend pricing — **not** a budget amount |

Sources: multipart file uploads are packaged as Haystack `ByteStream` with `mime_type` derived from filename extension. Non-empty JSON `project_text` is unstructured `text/plain` when no file (or in addition to file sources).

---

## Success response `200` — as-built `IngestFromProjectSpecResponse`

| Field | Type | Notes |
|-------|------|--------|
| `ingest_id` | string | `ing_` + hex — **required handle for Call 2 / Call 3** |
| `user_id` / `user_name` | string / null | Echo |
| `data_kind` | structured \| unstructured \| mixed | |
| `mime_types_seen` / `filenames` | string[] | |
| `structured_count` / `unstructured_count` | int | Sources |
| `document_count` (+ structured/unstructured_document_count) | int | Pre-split logical units |
| `chunk_count` / `documents_written` | int | After split/write |
| `documents` | object[] | Previews + meta (`user_id`, `ingest_id`, …); previews include `has_embedding` |
| `kg_built` | bool | Always `true` on successful 200 |
| `kg_node_count` / `kg_relationship_count` | int \| null | |
| `kg_artifact_path` | string \| null | Under `KG_ARTIFACT_DIR/{user_id}/` |
| `kg_transform_applied` | bool | Full Ragas on generator |
| `warnings` | string[] | Soft per-file conversion issues MAY appear here |

**As-built gaps vs TARGET:** no `needs_summary`, no `tentative_start_date` / `tentative_end_date` on response, no `expected_budget`. Request dates are validated when both set but **not** echoed on the live ingest body today.

---

## Success response `200` — TARGET simplified / enriched envelope (FR-IX-023)

Default client-facing shape **SHOULD** be compact. Indexing/KG technical fields MAY remain on the same DTO, under a `verbose` flag, or in a nested `indexing` object (product choice at implement).

### Required identity

| Field | Type | Notes |
|-------|------|--------|
| `ingest_id` | string | From as-built; **must** remain |
| `user_id` / `user_name` | string / null | Echo |

### Project-spec summary (client-facing)

| Field | Type | Notes |
|-------|------|--------|
| `needs_summary` | array of objects | What the **uploaded project-spec** implies is needed |
| `needs_summary[].description` | string | Human-readable need |
| `needs_summary[].equipment_hints` | string[] | Optional category/type hints |
| `needs_summary[].quantity` | int \| null | Optional |
| `needs_summary[].need_id` | string \| null | Optional stable id for Call 3 |
| `tentative_start_date` | date \| null | Request dates preferred when present; else extracted |
| `tentative_end_date` | date \| null | ≥ start when both set |
| `expected_budget` | object \| null | **Not** `include_pricing` |
| `expected_budget.amount` | number | When known |
| `expected_budget.currency` | string \| null | e.g. `SGD` when known |
| `expected_budget.source` | string | e.g. `extracted` \| `request` \| `unknown` |
| `warnings` | string[] | Missing budget, weak extraction, date conflicts, etc. |

### Still not on Call 1 (default path)

| Field | Why |
|-------|-----|
| `recommendation_id` / `results_by_need` | Call 3 / FR-010 reattach |
| Ranked `item.asset_id` / ML `daily_rate` | Fleet + pricing tools after ingest |

### Example (TARGET, illustrative)

```json
{
  "ingest_id": "ing_a1b2c3",
  "user_id": "user_123",
  "needs_summary": [
    {
      "need_id": "need_1",
      "description": "Two scissor lifts approximately 10 m for interior fit-out",
      "equipment_hints": ["scissor lift"],
      "quantity": 2
    }
  ],
  "tentative_start_date": "2026-09-01",
  "tentative_end_date": "2026-09-14",
  "expected_budget": {
    "amount": 15000,
    "currency": "SGD",
    "source": "extracted"
  },
  "warnings": [],
  "kg_built": true,
  "documents_written": 12
}
```

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
| KG build failure | Hard-fail after successful index write path; see [`../../knowledge-graph/spec.md`](../../knowledge-graph/spec.md) |
| Invalid date window | Both dates set and `end_date` < `start_date` |

Dates are accepted; as-built: unused for ranking until recommend reattach. **TARGET:** may populate `tentative_*` on success.

---

## Breaking changes note

**Breaking relative to prior recommend-on-route envelope:**

- No default `results_by_need` (and no `recommendation_id`) on this path until reattach is specified (FR-IX-017; T017 later).
- **`user_id` is required**.
- Successful body is **ingest + `kg_*`**, not ranked recommend output (as-built vs parent FR-040).

**TARGET relative to as-built technical-only body:**

- Adds summary fields (FR-IX-023). Compact default MAY demote or nest full `documents[]` previews (breaking for clients that require previews without `verbose`).

Deferred recommend envelope: [`../../recommendation-intake/spec.md`](../../recommendation-intake/spec.md). Service-level FR-010: [`../../recommendation-pipeline/spec.md`](../../recommendation-pipeline/spec.md).  
Feasibility: [`../../../Feasibility_Study/call1-ingest-response-project-summary.md`](../../../Feasibility_Study/call1-ingest-response-project-summary.md).
