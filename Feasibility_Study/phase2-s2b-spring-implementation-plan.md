# Phase 2 Implementation Plan — S2b (Spring Boot REST API)

| Field | Value |
|-------|--------|
| **Document type** | Implementation plan (stage-scoped) |
| **Stage** | **S2b** — Resilience C1, Spring Boot client half |
| **Repo** | Spring Boot REST API (portal / domain SoT) |
| **Phase** | Phase 2 (main plan) · Track **C1** (resilience study) |
| **Version** | 1.0.0 |
| **Date** | 2026-08-11 |
| **Status** | Ready to implement |
| **Sibling plan** | [`phase2-s2a-haystack-implementation-plan.md`](./phase2-s2a-haystack-implementation-plan.md) |
| **Parent** | [`implementation-plan.md`](./implementation-plan.md) Phase 2 |
| **Study** | [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) |
| **Standards** | TDD/BDD · WireMock · Resilience4j · stage PR template |

---

## 1. Goal

Harden Spring as the **orchestrating client** of haystack-fast-api:

- Per-operation **timeouts** (ingest ≫ Q&A ≫ health)
- **Circuit breaker + bulkhead** (Resilience4j)
- **Idempotent** ingest retries (`Idempotency-Key`)
- **Correlation** headers on every call
- **Saga** that never re-ingests on Q&A failure

Spring does **not** implement C/W/D multi-agent roles — those stay inside FastAPI.

---

## 2. Shared wire contract (agree with haystack)

| Item | Convention |
|------|------------|
| Ingest | `POST /internal/v1/recommendations/submitprojectspecification` |
| Q&A | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| Health | `GET /health` |
| Idempotency header | `Idempotency-Key` (UUID per logical ingest) |
| Correlation | `X-Correlation-Id` and/or W3C `traceparent` |
| Error body | `{"error":"<code>","message":"<text>"}` |
| Success ingest body | FR-IX-023 lean: `ingest_id`, `user_id`, summary, dates, needs, budget, warnings |

---

## 3. As-built baseline (FastAPI today → Spring implications)

| FastAPI today | Implication for Spring |
|---------------|------------------------|
| Unary REST ingest + Q&A | Blocking WebClient / RestClient OK for C1 |
| No 202 / job API yet | Long **read timeout** on ingest; measure p95 → may force C2 later |
| Process-local sessions (InMemory) | Sticky session **or** single FastAPI instance for Call 1→2 until Pgvector (Phase 5) |
| Error `{"error","message"}` | Map to domain exceptions; distinguish **4xx** vs **5xx** |
| S2a idempotency (sibling) | **Required** before production ingest **retry** |

---

## 4. In scope vs out of scope

### In scope (maps to main plan steps)

| Step | Work | Priority |
|------|------|----------|
| **2.1** | WebClient (or RestClient) + **per-operation timeouts** | **P0** |
| **2.2** | Resilience4j **circuit breaker + bulkhead** | **P0** |
| **2.3 (Spring half)** | Generate/send `Idempotency-Key`; retry only with same key | **P0** |
| **2.4 (Spring half)** | Propagate `X-Correlation-Id` / `traceparent` | **P0** |
| **2.5** | Saga: ingest → persist `ingest_id` → Q&A (0..N) → (later recommend stub) | **P1** |
| **2.6 (Spring half)** | Ops runbook: timeouts, max file size, p95, CB thresholds | **P1** |

### Out of scope

- FastAPI idempotency store → **S2a plan**
- 202 + poll / SSE (C2 / Phase 9)
- C/W/D roles inside Spring
- Full Call 3 recommend product (wire stub OK)
- gRPC / queues (C3)

---

## 5. Architecture

```text
Portal
  │
  ▼
RecommenderSaga / ApplicationService
  │  correlationId = UUID (or from inbound request)
  │
  ├─1─ HaystackRecommenderClient.ingest(file|text, userId, idempotencyKey)
  │       WebClient + timeout(ingest)
  │       headers: Idempotency-Key, X-Correlation-Id, traceparent
  │       Resilience4j: CB + bulkhead (+ retry only if idempotent)
  │       → persist ingestId on booking/session entity
  │
  ├─2─ client.qa(userId, ingestId, query)  × 0..N
  │       timeout(qa); retry transient 5xx; NEVER call ingest again
  │
  └─3─ client.recommend(...)  // later / no-op stub
```

### Design rules

1. **One `Idempotency-Key` per logical portal “submit project-spec”** — generate at saga start; **reuse on timeout retry**.
2. **Retry ingest only with the same key**; do not rotate the key on retry.
3. **Q&A failure ≠ re-ingest** — saga holds `ingest_id` from step 1.
4. **Timeouts** are config properties (health short; Q&A medium; ingest long).
5. **Bulkhead** caps concurrent haystack calls.
6. **CB open** → fail fast to portal (“recommender unavailable”) — no silent wrong equipment.
7. **4xx** → do not retry as success path.
8. Document **sticky / single instance** until Phase 5 Pgvector for Call 2 session affinity.

---

## 6. Implementation steps

### B1 — Client module skeleton

| Artifact | Notes |
|----------|--------|
| `HaystackProperties` | baseUrl, timeouts (connect/read per op), CB/bulkhead names, max file size |
| `HaystackRecommenderClient` | `health()`, `ingest(...)`, `queryProjectKnowledge(...)` |
| DTOs | Lean ingest response + Q&A response; error DTO `{error,message}` |
| WebClient bean | Codec max in-memory size ≥ max upload |

### B2 — Timeouts (2.1)

| Operation | Config example (tune with spike) |
|-----------|----------------------------------|
| Connect | 2–5s |
| Health read | 2–5s |
| Q&A read | 30–60s |
| Ingest read | 120–300s+ (measure p95) |

Exit: values in `application.yml` + runbook.

### B3 — Resilience4j (2.2)

| Pattern | Guidance |
|---------|----------|
| CircuitBreaker | On haystack client; open on error rate / slow calls |
| Bulkhead | Prefer separate limits for ingest vs Q&A |
| Retry | Exponential backoff + jitter; **ingest only with Idempotency-Key**; limited attempts |
| TimeLimiter | Align with read timeouts if reactive |

### B4 — Headers (2.3 + 2.4 Spring)

| Header | When |
|--------|------|
| `Idempotency-Key` | Every ingest POST (UUID per logical submit) |
| `X-Correlation-Id` | All haystack calls; from MDC / inbound gateway |
| `traceparent` | If Micrometer / Brave / OTel already present |

### B5 — Saga orchestrator (2.5)

```text
Given portal submits project-spec
When  saga runs
Then  ingest once (or idempotent retry) and store ingest_id
And   Q&A uses stored ingest_id
And   Q&A 5xx does not trigger a second ingest
And   later recommend uses same identity (stub OK)
```

Persist `ingest_id` (+ `user_id`, correlation id) on Spring-side session/booking aggregate.

### B6 — Runbook (2.6)

Document:

- Endpoint list + `/internal/v1/recommendations` prefix  
- Timeout matrix  
- Max multipart size (Spring + gateway + FastAPI) — **same number everywhere**  
- Expected p95 ingest (fill after spike)  
- CB thresholds and portal fallback copy  
- Sticky session note until Phase 5  
- Error mapping: FastAPI `error` code → Spring exception  

---

## 7. Test pack (WireMock / MockWebServer)

| # | Scenario | Assert |
|---|----------|--------|
| 1 | Delayed ingest > timeout | Client times out; retry uses **same** `Idempotency-Key` |
| 2 | N× 500 on ingest | CB opens; subsequent calls fail fast |
| 3 | Excess concurrent calls | Bulkhead rejects / queues per config |
| 4 | Saga: ingest 200 then Q&A 500 | `ingest_id` persisted; **no second ingest** recorded |
| 5 | Idempotent retry | WireMock sees same key header on retry |
| 6 | Correlation | Outbound requests include `X-Correlation-Id` |
| 7 | 400 from FastAPI | Mapped; not retried as success |

### BDD sketches

```text
Scenario: Saga does not re-ingest on Q&A failure
  Given ingest succeeded and ingest_id was persisted
  When  Q&A returns HTTP 500
  Then  the saga surfaces a retryable Q&A error
  And   WireMock records exactly one ingest request

Scenario: Ingest retry reuses Idempotency-Key
  Given ingest times out once
  When  the client retries
  Then  both attempts send the same Idempotency-Key header
```

---

## 8. Suggested PR packing

| PR | Content |
|----|---------|
| **S2b-1** | Client + properties + timeouts + DTOs + WireMock happy path (2.1) |
| **S2b-2** | Resilience4j CB + bulkhead + retry-with-key (2.2 + 2.3 headers) |
| **S2b-3** | Correlation propagation (2.4) — may fold into S2b-1 |
| **S2b-4** | Saga + persist `ingest_id` (2.5) |
| **S2b-5** | Runbook + config docs (2.6) |

**Minimum combine:** S2b-1 + S2b-2 + headers in one PR; saga second; docs third.

---

## 9. Exit criteria

- [ ] Per-op timeouts configured and tested
- [ ] CB opens on forced 5xx and recovers
- [ ] Bulkhead limits concurrency
- [ ] Ingest always sends `Idempotency-Key`; retries reuse key
- [ ] Correlation on every call
- [ ] Saga does not re-ingest after Q&A failure
- [ ] Runbook published; WireMock suite green

---

## 10. Effort estimate

| Slice | Rough |
|-------|--------|
| B1–B2 client + timeouts | 1–2 d |
| B3 Resilience4j | 1–2 d |
| B4 headers | 0.5 d |
| B5 saga + persist | 1–2 d |
| B6 runbook + WireMock polish | 0.5–1 d |
| **Total S2b** | **~4–7 eng-days** |

---

## 11. Dependency on S2a (haystack)

| Spring behavior | Needs FastAPI (S2a) |
|-----------------|---------------------|
| Retry ingest after timeout | Server idempotency store — else **double-index** |
| Correlation end-to-end | S2a logging (nice-to-have) |

```text
S2a-1 (idempotency)  ── parallel ──  S2b-1 (client timeouts)
         \                              /
          \____ join before production retries ____/
                          │
                          ▼
              Enable aggressive retry + full saga in prod
```

**Do not enable production ingest retry until S2a is live** (or accept dual-index risk).

---

## 12. Optional joint integration test

Not required for either CI, but useful once both land:

- Spring Testcontainers / local Spring + real FastAPI  
- Same `Idempotency-Key` twice → one `ingest_id`  
- Saga Q&A fail → single ingest  

---

## 13. C2 trigger (explicit non-goal here)

If gateway idle timeout kills long blocking ingest POSTs in production measurement, schedule **Phase 9 / C2** (202 + poll/SSE). Do not expand this plan into C2.

---

## 14. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-11 | Initial S2b plan split from Phase 2 |
