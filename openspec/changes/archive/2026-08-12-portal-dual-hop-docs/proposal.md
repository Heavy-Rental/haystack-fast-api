# Proposal: Portal dual-hop docs (Call 1 → Call 2)

| Field | Value |
|-------|--------|
| **Status** | **Superseded** by `2026-08-12-call2-recommend-call3-qa` (Call 2 = recommend, Call 3 = Q&A) |
| **Date** | 2026-08-12 |
| **Standards** | OpenSpec · GitHub Spec-kit · OpenSPDD |
| **Sources** | `Feasibility_Study/implementation-plan.md` §1.2.0 · `Feasibility_Study_Spring/portal-to-haystack-mapping.md` |

## Why

React portal submit `POST /api/recommendations/project-spec` is a **Spring-owned** saga that must call haystack **Call 1 then Call 2**, returning Call 2 Q&A to React. Specs previously treated Call 2 as only “optional” in places and lacked a testable OpenSpec requirement for the portal hop.

## What

| Artifact | Change |
|----------|--------|
| `openspec/config.yaml` | Portal dual-hop in Spec-kit context (not optional-only Call 2) |
| `specs/knowledge-graph/spec.md` | Requirement + scenarios: Call 2 after Call 1; not ingest |
| `specs/knowledge-graph/design.md` | REASONS Operations portal sequence + code path |
| `specs/knowledge-graph/contracts/project-knowledge-query.md` | Headers (correlation; no Idempotency-Key); code path |
| `specs/indexing/spec.md` + `design.md` | Norms/safeguards + diagram note Call 1 first |
| `TRACEABILITY.md` | Portal dual-hop + S2a archive rows |
| `specification/*` stubs | Soft-compat pointers |

## Non-goals

- Runtime changes to `app/api/recommendations.py`
- Call 3 / fleet quote on Call 2
- Spring Boot code (S2b)

## Checklist

- [x] OpenSpec requirements + scenarios
- [x] Contracts + design (OpenSPDD)
- [x] Spec-kit config context
- [x] TRACEABILITY
- [x] Legacy specification redirects
