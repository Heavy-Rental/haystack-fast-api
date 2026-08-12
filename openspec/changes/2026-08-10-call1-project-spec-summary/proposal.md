# Proposal: Call 1 project-spec summary on ingest response (FR-IX-023)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-10 |
| **Status** | **Shipped as-built** (S1a–S1e / Phase 1.7) — Call 1 lean FR-IX-023 summary |
| **Capability** | indexing (+ intake alignment) |
| **Trace** | FR-IX-023 · FR-I-016 |

## Problem

Live `POST /internal/v1/recommendations/submitprojectspecification` returns the **FR-IX-023 as-built** lean body: `ingest_id`, `user_id`, `user_requirement_summary`, `tentative_*` (request preferred; free-text extract when omitted), `needs_summary[]`, `expected_budget` | null, `warnings[]`. Still not Call 3 `results_by_need`.

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

## Specs updated (as-built)

- `openspec/specs/indexing/spec.md` (**FR-IX-023 as-built** S1a–S1e / Phase 1.7)
- `openspec/specs/indexing/contracts/ingest-from-project-spec.md`
- `openspec/specs/indexing/design.md`
- `openspec/specs/recommendation-intake/spec.md` (FR-I-016)
- `openspec/AGENTS.md` flow
- `Feasibility_Study/call1-ingest-response-project-summary.md`
- `Feasibility_Study/implementation-plan.md` Phase 1

## Implementation tasks (shipped)

- [x] Extend `IngestFromProjectSpecResponse` schema (lean + FR-IX-023 fields)
- [x] Wire need decomposer / date / budget extractors after KG in `IndexingIngestService`
- [x] Echo request dates (S1b); free-text date extract (S1e); budget extract (S1d)
- [x] Tests + Postman + OpenAPI
- [x] Converge as-built status (Phase 1.7)
