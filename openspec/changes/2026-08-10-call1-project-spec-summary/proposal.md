# Proposal: Call 1 project-spec summary on ingest response (FR-IX-023)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-10 |
| **Status** | Spec / feasibility only — **not implemented** |
| **Capability** | indexing (+ intake alignment) |
| **Trace** | FR-IX-023 · FR-I-016 |

## Problem

Live `POST /internal/v1/recommendations/submitprojectspecification` returns a **lean** ingest body (`ingest_id`, `user_id`, `user_requirement_summary`, `warnings[]`) after S1a. Spring/portal clients still want **full FR-IX-023** enrichment: structured `needs_summary[]`, tentative rental dates, and expected budget — while keeping `ingest_id` for Call 2 / Call 3.

## Proposal

1. After successful index + mandatory KG, extract (or echo):
   - `needs_summary[]`
   - `tentative_start_date` / `tentative_end_date` (request preferred)
   - `expected_budget` (nullable; never invent)
2. Keep **not** returning `results_by_need` / ranked assets / ML rent on Call 1.
3. Optional compact default: nest or gate verbose indexing fields.

## Non-goals

- Call 3 reattach (fleet + pricing)
- Using `include_pricing` as budget
- Runtime code in this change set

## Specs updated

- `openspec/specs/indexing/spec.md` (FR-IX-023 TARGET)
- `openspec/specs/indexing/contracts/ingest-from-project-spec.md`
- `openspec/specs/indexing/design.md`
- `openspec/specs/recommendation-intake/spec.md` (FR-I-016)
- `openspec/AGENTS.md` flow
- `Feasibility_Study/call1-ingest-response-project-summary.md`

## Implementation tasks (later)

- [ ] Extend `IngestFromProjectSpecResponse` schema
- [ ] Wire need decomposer / extractors after KG in `IndexingIngestService`
- [ ] Echo request dates; extract budget safely
- [ ] Tests + Postman + OpenAPI
- [ ] Converge as-built status when shipped
