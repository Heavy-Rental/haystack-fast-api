# Proposal (archived): HR-65 Intake & Pipeline Front

| Field | Value |
|-------|--------|
| **Change id** | `2026-08-07-hr-65-intake-front` |
| **Tracking** | HR-65 |
| **Branch (historical)** | `HR-65-implement-intake-stage-for-recommender-system` |
| **Status** | **Archived / superseded** |
| **Superseded by (live HTTP)** | [`../../../specs/indexing/spec.md`](../../../specs/indexing/spec.md) |
| **Superseded related** | [`../../../specs/knowledge-graph/spec.md`](../../../specs/knowledge-graph/spec.md) (mandatory KG after joiner) |
| **Retained service path** | [`../../../specs/recommendation-pipeline/spec.md`](../../../specs/recommendation-pipeline/spec.md) (FR-010.1–8) |
| **Deferred recommend envelope** | [`../../../specs/recommendation-intake/spec.md`](../../../specs/recommendation-intake/spec.md) |
| **Historical detail** | [`historical-spec.md`](./historical-spec.md) |

---

## Why this change existed

HR-65 delivered the **intake stage** for the recommender: free-text/file public intake API, Haystack FR-010 steps 1–3 (resolve → decompose → expand), singular `item` response envelope, and later the full FR-010.1–8 MVP with seed fleet, availability, pricing adapter, and template rank.

## What shipped (historical)

- Public `POST /api/v1/recommendations/from-project-spec` returning **recommend** envelope (`recommendation_id`, `results_by_need`, singular `item`).
- Haystack `intake_front` pipeline + `RecommendationService`.
- Optional `NEED_DECOMPOSER=llm`; default stub for CI.
- Full FR-010.1–8 service path with seed fleet (not Spring ORM).

## Supersession (2026-08-07)

| Topic | Current authority |
|-------|-------------------|
| Sequential reading map | [`../../../AGENTS.md`](../../../AGENTS.md) |
| Live `POST .../from-project-spec` | [`../../../specs/indexing/spec.md`](../../../specs/indexing/spec.md) (`user_id` required) |
| Mandatory KG after joiner + Stage-1 multi-agent | [`../../../specs/knowledge-graph/spec.md`](../../../specs/knowledge-graph/spec.md) |
| FR-010.1–8 service graph | [`../../../specs/recommendation-pipeline/spec.md`](../../../specs/recommendation-pipeline/spec.md) |
| Deferred recommend HTTP envelope | [`../../../specs/recommendation-intake/spec.md`](../../../specs/recommendation-intake/spec.md) |
| Live Postman | [`../../../../postman/README.md`](../../../../postman/README.md) |

**Do not treat** the historical recommend HTTP response in [`historical-spec.md`](./historical-spec.md) as live as-built behaviour without reattach.

## Scope of this archive

- Preserve HR-65 stage narrative, FR-PF-* requirements, design, acceptance criteria, LLM integration guidance, and testing notes so **no detail is lost**.
- Point implementers at OpenSpec Path B (live) and Path C (deferred recommend).

## Out of scope for this archive entry

- Re-implementing recommend as default HTTP (separate future change).
- Modifying Python app code.

## Conflict rule

Live HTTP → **indexing**. FR-010 service → **recommendation-pipeline**. Deferred recommend API tables → **recommendation-intake**. Historical HR-65 prose → **this archive**.
