# Proposal: Call 1 idempotency + correlation (S2a / resilience C1)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S2a) + audit gap-fill |
| **Date** | 2026-08-12 |
| **Trace** | FR-IX-024 · FR-IX-025 |
| **Plan** | [`Feasibility_Study/phase2-s2a-haystack-implementation-plan.md`](../../../../Feasibility_Study/phase2-s2a-haystack-implementation-plan.md) |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD (spec/contract before code) · TDD/BDD |

## Why

Spring must retry Call 1 after gateway/timeouts without double-indexing, and ops must join Spring + FastAPI logs. Resilience study C1 splits: **S2a** = FastAPI half; **S2b** = Spring client half.

## What shipped

| Item | Behaviour |
|------|-----------|
| `Idempotency-Key` | Optional; scoped with `user_id`; process-local store of successful lean 200; replay same `ingest_id`; failures not cached; single-flight concurrent |
| `X-Correlation-Id` | Optional; mint if missing; log + echo on all routes |
| `traceparent` | Optional; logged when present |
| Error contract | Unchanged `{"error","message"}` |
| FR-IX-023 body | Unchanged lean summary fields |

## Spec / design / contract

- `openspec/specs/indexing/spec.md` — FR-IX-024, FR-IX-025
- `openspec/specs/indexing/contracts/ingest-from-project-spec.md` — headers + replay rules
- `openspec/specs/indexing/design.md` — modules + diagram
- `openspec/TRACEABILITY.md` — FR map

## Code

- `app/services/ingest_idempotency.py`
- `app/middleware/correlation.py`
- `app/api/recommendations.py` (key wiring)
- `app/main.py` (middleware)
- `tests/test_ingest_idempotency.py`, `tests/test_correlation_middleware.py`

## Out of scope (still)

- Spring WebClient / Resilience4j / saga → S2b
- Redis/Postgres multi-replica idempotency
- 202 Accepted job store / SSE (C2)

## Checklist

- [x] OpenSpec requirements + scenarios
- [x] Contract header tables
- [x] TRACEABILITY FR rows
- [x] Implementation + default CI tests
- [x] Postman collection + README / Spring integration notes
- [x] Multi-replica limit documented
- [x] Spec-kit `tasks.md` + audit matrix
- [x] Gap-fill tests (single-flight, blank key, TTL, correlation bind)
- [x] Archived under `openspec/changes/archive/`
