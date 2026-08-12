# Tasks: S2a Call 1 idempotency + correlation (FR-IX-024 / FR-IX-025)

**Input:** [`../../../specs/indexing/spec.md`](../../../specs/indexing/spec.md)  
**Contract:** [`../../../specs/indexing/contracts/ingest-from-project-spec.md`](../../../specs/indexing/contracts/ingest-from-project-spec.md)  
**Design:** [`../../../specs/indexing/design.md`](../../../specs/indexing/design.md)  
**Proposal:** [`./proposal.md`](./proposal.md)  
**Plan:** [`../../../../Feasibility_Study/phase2-s2a-haystack-implementation-plan.md`](../../../../Feasibility_Study/phase2-s2a-haystack-implementation-plan.md)  
**Spec-kit phase:** Tasks → Implement → Converge → **Archived**  
**Standards:** OpenSpec · GitHub Spec-kit · OpenSPDD · TDD/BDD

---

## Phase 0 — Spec / contract first (A1)

- [x] T001 Contract header tables: `Idempotency-Key`, `X-Correlation-Id`, `traceparent` + replay rules
- [x] T002 Requirements FR-IX-024 / FR-IX-025 + scenarios in `specs/indexing/spec.md`
- [x] T003 Design REASONS modules + diagram for S2a
- [x] T004 TRACEABILITY rows FR-IX-024 / FR-IX-025
- [x] T005 This `tasks.md` + proposal (Spec-kit change pack)

---

## Phase 1 — Idempotency store + route (A2–A3)

- [x] T006 `app/services/ingest_idempotency.py` — protocol/store, scope key, TTL, single-flight
- [x] T007 Wire `Idempotency-Key` on JSON + multipart ingest in `app/api/recommendations.py`
- [x] T008 OpenAPI optional headers on ingest
- [x] T009 Config `IDEMPOTENCY_TTL_SECONDS` + `.env.example`

---

## Phase 2 — Correlation (A4)

- [x] T010 `app/middleware/correlation.py` — extract/mint, echo, contextvars, log filter
- [x] T011 Register middleware + log format in `app/main.py`

---

## Phase 3 — Test pack (TDD/BDD) — plan §7

- [x] T012 Same key → same `ingest_id` (JSON)
- [x] T013 Same key does not re-run ingest service
- [x] T014 Different keys → distinct `ingest_id`s
- [x] T015 Missing key → always new ingest
- [x] T016 Multipart honours key
- [x] T017 Failure 400 not cached as success
- [x] T018 Key scoped by `user_id`
- [x] T019 Error body shape regression with key
- [x] T020 FR-IX-023 success fields still present with key
- [x] T021 Correlation header echoed / minted
- [x] T022 Correlation on ingest + Q&A; `traceparent` accepted

### Audit gap-fill (2026-08-12)

- [x] T023 Concurrent same key → single-flight (one producer)
- [x] T024 Blank/whitespace key treated as missing
- [x] T025 Store TTL unit expiry
- [x] T026 Correlation log record binds client `correlation_id`

---

## Phase 4 — Docs (A5)

- [x] T027 Postman README resilience headers + limits
- [x] T028 Spring integration contract notes (S2a headers)
- [x] T029 Postman **collection** optional resilience headers on ingest (+ Q&A/health correlation)
- [x] T030 CHANGELOG S2a entry
- [x] T031 Feasibility_Study README S2a plan version 1.1.0 / Implemented

---

## Phase 5 — Converge + archive

- [x] T032 Default CI: `pytest tests/test_ingest_idempotency.py tests/test_correlation_middleware.py` green
- [x] T033 Multi-replica / process-local limit documented (contract + Postman + design)
- [x] T034 Archive this change under `openspec/changes/archive/`

---

## Audit matrix — S2a plan §9 exit criteria

| Exit criterion | Evidence | Status |
|----------------|----------|--------|
| Double POST same `Idempotency-Key` → one logical `ingest_id` | `test_same_idempotency_key_returns_same_ingest_id`, `test_same_key_does_not_re_run_ingest_service` | **PASS** |
| Different keys → two ingests | `test_different_keys_yield_distinct_ingest_ids` | **PASS** |
| Missing key → unchanged | `test_missing_key_always_new_ingest` | **PASS** |
| Correlation id logged (and echoed) | `test_correlation_header_echoed_*`, `test_correlation_logged_on_ingest` (binds cid) | **PASS** |
| Error shape regression green | `test_error_body_shape_regression_with_key` | **PASS** |
| OpenSpec contract updated; default CI green | `specs/indexing/contracts/ingest-from-project-spec.md`; pytest S2a modules | **PASS** |
| Multi-replica / memory-store limitation documented | contract §headers; Postman README Limits; design Safeguards | **PASS** |
| Concurrent single-flight | `test_concurrent_same_key_single_flight` | **PASS** (gap-fill) |
| Blank key = missing | `test_blank_idempotency_key_treated_as_missing` | **PASS** (gap-fill) |
| TTL expiry | `test_store_ttl_expires_entry` | **PASS** (gap-fill) |
