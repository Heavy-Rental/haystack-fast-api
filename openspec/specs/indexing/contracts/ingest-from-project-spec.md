# Contract: `POST /api/v1/recommendations/from-project-spec` (as-built)

| Field | Value |
|-------|--------|
| **Capability** | [`../spec.md`](../spec.md) (indexing) |
| **Design** | [`../design.md`](../design.md) |
| **Status** | as-built |
| **DTO** | `IngestFromProjectSpecResponse` (`app/schemas/indexing.py`) |

Live HTTP owner: **indexing** (not FR-010 recommend on the public route).

---

## Request

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Tenant for meta + KG path |
| `user_name` | no | Echo / audit |
| `project_text` and/or `file` | one non-empty source | JSON-only needs non-empty text |
| `start_date` / `end_date` | no | Window valid if both set |
| `options` / `include_pricing` | no | Accepted; unused until reattach |

Sources: multipart file uploads are packaged as Haystack `ByteStream` with `mime_type` derived from filename extension. Non-empty JSON `project_text` is unstructured `text/plain` when no file (or in addition to file sources).

---

## Success response `200` — `IngestFromProjectSpecResponse`

| Field | Type | Notes |
|-------|------|--------|
| `ingest_id` | string | `ing_` + hex |
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

Dates are accepted; unused for ranking until recommend reattach.

---

## Breaking changes note

**Breaking relative to prior recommend-on-route envelope:**

- No default `results_by_need` (and no `recommendation_id`) on this path until reattach is specified (FR-IX-017; T017 later).
- **`user_id` is required**.
- Successful body is **ingest + `kg_*`**, not ranked recommend output (as-built vs parent FR-040).

Deferred recommend envelope: [`../../recommendation-intake/spec.md`](../../recommendation-intake/spec.md). Service-level FR-010: [`../../recommendation-pipeline/spec.md`](../../recommendation-pipeline/spec.md).
