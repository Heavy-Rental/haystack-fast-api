# Phase 2 Implementation Plan — S2a (haystack-fast-api)

| Field | Value |
|-------|--------|
| **Document type** | Implementation plan (stage-scoped) |
| **Stage** | **S2a** — Resilience C1, FastAPI half |
| **Repo** | `haystack-fast-api` |
| **Phase** | Phase 2 (main plan) · Track **C1** (resilience study) |
| **Version** | 1.0.0 |
| **Date** | 2026-08-11 |
| **Status** | Ready to implement |
| **Sibling plan** | [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md) |
| **Parent** | [`implementation-plan.md`](./implementation-plan.md) Phase 2 |
| **Study** | [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) |
| **Standards** | OpenSpec · Spec-kit · SPDD · TDD/BDD · stage PR template |

---

## 1. Goal

Make Call 1 **safe to retry** and **traceable** on the FastAPI side so Spring can use timeouts/retries without double-indexing, and ops can correlate logs end-to-end.

**Primary endpoint:**  
`POST /internal/v1/recommendations/submitprojectspecification`

Also touch logging for:  
`POST /internal/v1/recommendations/project-knowledge/getassetrecommendations`  
`GET /health` (correlation optional)

---

## 2. Shared wire contract (agree with Spring)

| Item | Convention |
|------|------------|
| Ingest | `POST /internal/v1/recommendations/submitprojectspecification` |
| Q&A | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| Health | `GET /health` |
| Idempotency header | `Idempotency-Key` (UUID per logical ingest) |
| Correlation | `X-Correlation-Id` and/or W3C `traceparent` |
| Error body (as-built) | `{"error":"<code>","message":"<text>"}` |
| Success ingest body | FR-IX-023 lean: `ingest_id`, `user_id`, summary, dates, needs, budget, warnings |

---

## 3. As-built baseline (do not re-implement)

| Already done | Location |
|--------------|----------|
| Shared error JSON | `app/core/errors.py`, `app/core/exceptions.py` |
| Threadpool offload | `app/api/recommendations.py` (`run_in_threadpool`) |
| Internal routes + lean Call 1 body | FR-IX-023 S1a–S1e as-built |
| Health endpoint | `GET /health` |

---

## 4. In scope vs out of scope

### In scope (maps to main plan steps)

| Step | Work | Priority |
|------|------|----------|
| **2.3 (app half)** | Accept `Idempotency-Key`; store mapping → return same `ingest_id` on retry | **P0** |
| **2.4 (app half)** | Read `X-Correlation-Id` / `traceparent`; log on request path | **P0** |
| **2.6 (app half)** | Document error contract + max body/size notes; thin regression tests | **P1** |

### Out of scope

- Spring WebClient / Resilience4j / saga → **S2b plan**
- 202 Accepted + job store / SSE → Phase 9 / C2
- Redis/Postgres idempotency for multi-replica (memory OK for single-node; **document limit**)
- Changing public FR-IX-023 response shape
- Call 3 recommend reattach

---

## 5. Architecture

```text
POST .../submitprojectspecification
       │
       ├─ middleware: extract X-Correlation-Id / traceparent → bind logging context
       │
       ├─ if Idempotency-Key present:
       │     hit in-memory store?
       │       YES → return cached IngestFromProjectSpecResponse (same ingest_id)
       │       NO  → run IndexingIngestService → store key → response
       │
       └─ if no key → current behavior (always new ingest)
```

### Design rules

1. **Idempotency applies to successful ingest only** (200). Failed 4xx/5xx MUST NOT be cached as success.
2. **Scope key** by something stable: recommend `user_id` + `Idempotency-Key` (or key alone if Spring always sends a global UUID).
3. **TTL** optional (e.g. 24h) for memory pressure; document single-process limit.
4. **In-flight** same key concurrent POST: prefer single-flight (wait) or return **409** `conflict`; document choice.
5. **Correlation** is logging-only in C1 (optional response echo of `X-Correlation-Id`).
6. **Do not invent** assets/rates/budgets; idempotency only reuses a prior successful lean response.

---

## 6. Implementation steps

### A1 — Spec / contract first (OpenSpec · Spec-kit · SPDD)

| File | Change |
|------|--------|
| `openspec/specs/indexing/contracts/ingest-from-project-spec.md` | Header tables: `Idempotency-Key`, correlation; replay semantics |
| `openspec/specs/indexing/spec.md` | Requirements + scenarios for idempotent ingest |
| `openspec/TRACEABILITY.md` | Map FR if assigned |
| `Feasibility_Study/implementation-plan.md` | Mark S2a steps when done |

### A2 — Idempotency store

| Artifact | Notes |
|----------|--------|
| `app/services/ingest_idempotency.py` (or `app/core/idempotency.py`) | Protocol + `InMemoryIdempotencyStore` |
| Store value | Serialized lean `IngestFromProjectSpecResponse` for 200 only |
| Config | Optional `IDEMPOTENCY_TTL_SECONDS`; feature default on |

```python
def get(key: str) -> IngestFromProjectSpecResponse | None: ...
def put(key: str, response: IngestFromProjectSpecResponse) -> None: ...
# optional single-flight lock per key
```

### A3 — Wire into ingest route

| Location | Work |
|----------|------|
| `app/api/recommendations.py` | Read `Idempotency-Key`; check store before service; put after success |
| JSON + multipart | Both honor the same key |
| OpenAPI | Document optional header |

### A4 — Correlation middleware

| Artifact | Notes |
|----------|--------|
| `app/middleware/correlation.py` (or logging filter) | Prefer request header; else generate UUID |
| Logging | contextvars / `extra={"correlation_id": ...}` on ingest + Q&A |
| Response (optional) | Echo `X-Correlation-Id` |

### A5 — Docs (2.6 app half)

| Artifact | Notes |
|----------|--------|
| `postman/README.md` and/or ops note | Headers table; error shape; max upload if configured |
| OpenSpec | Client may retry **5xx** only with same `Idempotency-Key` |

---

## 7. Test pack (TDD / BDD) — default CI

**Modules:** `tests/test_ingest_idempotency.py` + middleware/correlation tests.

| # | Scenario | Assert |
|---|----------|--------|
| 1 | Same `Idempotency-Key` twice (JSON) | Same `ingest_id`; second is store hit (no double logical ingest) |
| 2 | Different keys | Two distinct `ingest_id`s |
| 3 | Missing key | Current behavior (always new ingest) |
| 4 | Key + multipart | Same as JSON |
| 5 | First request 400, second fixed same key | Second succeeds as **new** work (failure not cached as success) |
| 6 | Correlation header present | Logged and/or echoed |
| 7 | Regression | Error body `{"error","message"}`; FR-IX-023 fields still on success |

**No** live LLM / Neo4j / primary. Use existing stub modes.

### BDD sketches

```text
Scenario: Idempotent ingest replay
  Given a successful Call 1 with Idempotency-Key "k1"
  When  the same request is POSTed again with Idempotency-Key "k1"
  Then  the response ingest_id equals the first response
  And   a second full index+KG is not required

Scenario: Missing key is not idempotent
  Given no Idempotency-Key header
  When  two identical successful ingests run
  Then  two different ingest_ids are returned
```

---

## 8. Suggested PR packing

| PR | Content |
|----|---------|
| **PR-B / S2a-1** | Idempotency store + route wiring + tests (2.3) |
| **S2a-2** | Correlation middleware + log verification (2.4) — may merge into S2a-1 |
| **S2a-3** | Docs / Postman / OpenSpec converge (2.6) |

Use main plan §6 PR template: **What & Why** + **Key Changes**; link sibling Spring PR under Dependent PRs.

---

## 9. Exit criteria

- [ ] Double POST same `Idempotency-Key` → one logical `ingest_id`
- [ ] Different keys → two ingests
- [ ] Missing key → unchanged
- [ ] Correlation id logged (and optionally echoed)
- [ ] Error shape regression green
- [ ] OpenSpec contract updated; default CI green
- [ ] Multi-replica / memory-store limitation documented

---

## 10. Effort estimate

| Slice | Rough |
|-------|--------|
| A1 specs | 0.5–1 d |
| A2–A3 idempotency | 1–2 d |
| A4 correlation | 0.5 d |
| A5 docs + polish | 0.5 d |
| **Total S2a** | **~2.5–4 eng-days** |

---

## 11. Coordination with S2b

| Spring behavior | Needs this plan |
|-----------------|-----------------|
| Retry ingest after timeout | **Server store (A2–A3)** — else retry double-indexes |
| End-to-end correlation | A4 logs correlation (Spring can still send headers alone) |

```text
S2a-1 (idempotency)  ── parallel ──  S2b client timeouts
         \                              /
          \____ join before production retries ____/
```

Do **not** encourage production ingest retry until S2a-1 is live.

---

## 12. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-11 | Initial S2a plan split from Phase 2 |
