# Phase 2 Implementation Plan — S2b (Spring Boot REST API)

| Field | Value |
|-------|--------|
| **Document type** | Implementation plan (stage-scoped) |
| **Stage** | **S2b** — Resilience C1, Spring Boot client half |
| **Repo** | Spring Boot REST API (portal / domain SoT) |
| **Phase** | Phase 2 (main plan) · Track **C1** (resilience study) |
| **Version** | **2.0.1** |
| **Date** | 2026-08-12 |
| **Status** | **Ready to implement** |
| **Sibling** | S2a haystack — **as-built** (see [`s2a-haystack-dependency.md`](./s2a-haystack-dependency.md)) |
| **Study** | [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) |
| **Wire** | [`wire-contract-call1-call2.md`](./wire-contract-call1-call2.md) |
| **Portal saga** | [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md) |
| **Standards** | TDD/BDD · WireMock · Resilience4j · stage PR template |
| **Package** | Spring export under `Feasibility_Study_Spring/` |

---

## 1. Goal

Harden Spring as the **orchestrating client** of haystack-fast-api:

- Per-operation **timeouts** (ingest ≫ recommend ≫ Q&A ≫ health)
- **Circuit breaker + bulkhead** (Resilience4j)
- **Idempotent** ingest retries (`Idempotency-Key`)
- **Correlation** headers on every call
- **Portal project-spec saga:** React `POST /api/recommendations/project-spec` → **Call 1 then Call 2 recommend** → return **Call 2 quote** to React; optional Call 3 chatbot Q&A; never re-ingest on Call 2 failure

Spring does **not** implement C/W/D multi-agent roles — those stay inside FastAPI.

---

## 2. Shared wire contract (agree with haystack)

| Item | Convention |
|------|------------|
| Ingest | `POST /internal/v1/recommendations/submitprojectspecification` |
| Call 2 recommend | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| Call 3 chatbot | `POST /internal/v1/recommendations/project-knowledge/query` |
| Health | `GET /health` |
| Idempotency header | `Idempotency-Key` (UUID per logical ingest) |
| Correlation | `X-Correlation-Id` and/or W3C `traceparent` |
| Error body | `{"error":"<code>","message":"<text>"}` |
| Success ingest body | FR-IX-023 lean — see [`call1-ingest-response-for-spring.md`](./call1-ingest-response-for-spring.md) |

Full tables: [`wire-contract-call1-call2.md`](./wire-contract-call1-call2.md).

---

## 3. As-built baseline (FastAPI today → Spring implications)

| FastAPI today | Implication for Spring |
|---------------|------------------------|
| Unary REST Call 1 ingest + Call 2 recommend + Call 3 Q&A | Blocking WebClient / RestClient OK for C1 |
| No 202 / job API yet | Long **read timeout** on ingest; measure p95 → may force C2 later |
| Process-local sessions (InMemory) | Sticky session **or** single FastAPI instance for Call 1→2 until Pgvector |
| Error `{"error","message"}` | Map to domain exceptions; distinguish **4xx** vs **5xx** |
| **S2a as-built** | Process-local `Idempotency-Key` store + correlation echo — **required** before production ingest **retry** |

---

## 4. In scope vs out of scope

### In scope (maps to main plan steps)

| Step | Work | Priority |
|------|------|----------|
| **2.1** | WebClient (or RestClient) + **per-operation timeouts** | **P0** |
| **2.2** | Resilience4j **circuit breaker + bulkhead** | **P0** |
| **2.3 (Spring half)** | Generate/send `Idempotency-Key`; retry only with same key | **P0** |
| **2.4 (Spring half)** | Propagate `X-Correlation-Id` / `traceparent` | **P0** |
| **2.5** | Saga: Call 1 → persist → Call 2 recommend → React; optional Call 3 chatbot | **P1** |
| **2.6 (Spring half)** | Ops runbook: timeouts, max file size, p95, CB thresholds | **P1** |

### Out of scope

- FastAPI idempotency store → **S2a** (already shipped)  
- 202 + poll / SSE (C2 / Phase 9)  
- C/W/D roles inside Spring  
- Full multi-agent Call 2 enrich beyond MVP (S7.x; wire stub OK)
- gRPC / queues (C3)  

---

## 5. Architecture

```text
React  POST /api/recommendations/project-spec
  │
  ▼
RecommenderSaga / ApplicationService
  │  correlationId = UUID (or from inbound request)
  │  idempotencyKey = UUID per logical portal submit
  │
  ├─1─ HaystackRecommenderClient.ingest(file|text, userId, idempotencyKey)
  │       RestClient/WebClient + timeout(ingest)
  │       POST .../submitprojectspecification
  │       headers: Idempotency-Key, X-Correlation-Id, traceparent
  │       Resilience4j: CB + bulkhead (+ retry only if idempotent)
  │       → persist ingestId on booking/session entity
  │
  ├─2─ client.recommend(userId, ingestId, query?)   // required portal hop
  │       POST .../project-knowledge/getassetrecommendations
  │       timeout(recommend); retry transient 5xx; NEVER re-ingest
  │       → map Call 2 quote body to React
  │
  └─3─ client.chatQa(userId, ingestId, query)  × 0..N  // Call 3 optional
          POST .../project-knowledge/query
```

### Design rules

1. **One `Idempotency-Key` per logical portal “submit project-spec”** — generate at saga start; **reuse on timeout retry**.  
2. **Retry ingest only with the same key**; do not rotate the key on retry.  
3. **Call 2/3 failure ≠ re-ingest** — saga holds `ingest_id` from step 1.  
4. **Timeouts** are config properties (health short; Q&A medium; recommend medium–long; ingest long).  
5. **Bulkhead** caps concurrent haystack calls.  
6. **CB open** → fail fast to portal (“recommender unavailable”) — no silent wrong equipment.  
7. **4xx** → do not retry as success path.  
8. Document **sticky / single instance** until Phase 5 Pgvector for Call 2 session affinity.  

### Suggested modules (non-normative — adapt to your package layout)

```text
…/client/haystack/HaystackProperties.java
…/client/haystack/HaystackRecommenderClient.java
…/client/haystack/dto/IngestFromProjectSpecResponse.java
…/client/haystack/dto/ProjectKnowledgeQueryRequest.java
…/client/haystack/dto/HaystackErrorBody.java
…/application/RecommenderSaga.java   // or existing booking application service
```

---

## 6. Implementation steps

### B1 — Client module skeleton

| Artifact | Notes |
|----------|--------|
| `HaystackProperties` | baseUrl, timeouts (connect/read per op), CB/bulkhead names, max file size |
| `HaystackRecommenderClient` | `health()`, `ingest(...)`, `queryProjectKnowledge(...)` |
| DTOs | Lean Call 1 ingest + Call 2 quote + Call 3 Q&A; error DTO `{error,message}` |
| WebClient bean | Codec max in-memory size ≥ max upload |

### B2 — Timeouts (2.1)

| Operation | Config example (tune with spike) |
|-----------|----------------------------------|
| Connect | 2–5s |
| Health read | 2–5s |
| Recommend (Call 2) read | 60–120s |
| Q&A (Call 3) read | 30–60s |
| Ingest read | 120–300s+ (measure p95) |

Exit: values in `application.yml` + runbook.

Example property sketch:

```yaml
haystack:
  base-url: http://localhost:8000
  timeouts:
    connect: 5s
    health-read: 5s
    qa-read: 45s
    ingest-read: 180s
  max-in-memory-size: 20MB
```

### B3 — Resilience4j (2.2)

| Pattern | Guidance |
|---------|----------|
| CircuitBreaker | On haystack client; open on error rate / slow calls |
| Bulkhead | Prefer separate limits for ingest vs recommend vs Q&A |
| Retry | Exponential backoff + jitter; **ingest only with Idempotency-Key**; limited attempts |
| TimeLimiter | Align with read timeouts if reactive |

### B4 — Headers (2.3 + 2.4 Spring)

| Header | When |
|--------|------|
| `Idempotency-Key` | Every ingest POST (UUID per logical submit) |
| `X-Correlation-Id` | All haystack calls; from MDC / inbound gateway |
| `traceparent` | If Micrometer / Brave / OTel already present |

### B5 — Saga orchestrator (2.5)

Portal entrypoint: **`POST /api/recommendations/project-spec`** (React).  
Haystack hops: Call 1 then Call 2 — see [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md).

```text
Given React posts project-spec to Spring
When  saga runs
Then  Call 1 ingest once (or idempotent retry) and store ingest_id
And   Call 2 recommend uses stored user_id + ingest_id (+ optional query)
And   the portal response body is primarily the Call 2 quote payload
And   Call 2 5xx does not trigger a second ingest
And   optional Call 3 chatbot Q&A uses same identity
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
| 4 | Saga: ingest 200 then Call 2 recommend 500 | `ingest_id` persisted; **no second ingest** |
| 5 | Idempotent retry | WireMock sees same key header on retry |
| 6 | Correlation | Outbound requests include `X-Correlation-Id` on Call 1 **and** Call 2 |
| 7 | 400 from FastAPI | Mapped; not retried as success |
| 8 | **Portal dual-hop happy path** | `POST /api/recommendations/project-spec` → 1× Call 1 + 1× Call 2 recommend; **portal body** has `quoteRef` / `items`; WireMock path `.../getassetrecommendations` |
| 9 | **Call 3 chatbot** | Optional `.../project-knowledge/query` returns `answer` (not quote) |

### BDD sketches

```text
Scenario: Saga does not re-ingest on Call 2 recommend failure
  Given ingest succeeded and ingest_id was persisted
  When  Call 2 recommend returns HTTP 500
  Then  the saga surfaces a retryable recommend error
  And   WireMock records exactly one ingest request

Scenario: Ingest retry reuses Idempotency-Key
  Given ingest times out once
  When  the client retries
  Then  both attempts send the same Idempotency-Key header

Scenario: Portal project-spec dual-hop returns Call 2 recommend quote
  Given React posts to POST /api/recommendations/project-spec
  When  the saga completes successfully
  Then  WireMock records one submitprojectspecification and one getassetrecommendations
  And   the HTTP response to React is mapped from the Call 2 quote (quoteRef / items)
  And   Call 2 request includes user_id and ingest_id from Call 1
```

### How to test this stage (runbook)

Commands assume a typical Spring Boot multi-module or single-module layout. Adjust package/module names to your repo.

#### 7.1 Automated (WireMock / MockWebServer) — recommended first

```bash
# Gradle examples (adjust module path)
./gradlew test --tests '*HaystackRecommenderClient*'
./gradlew test --tests '*RecommenderSaga*'
./gradlew test --tests '*Haystack*Resilience*'

# Maven examples
mvn -Dtest=HaystackRecommenderClientTest,RecommenderSagaTest test
```

**Suggested test classes (names illustrative):**

| Class | Covers |
|-------|--------|
| `HaystackRecommenderClientTest` | Timeouts, headers, DTO mapping, 4xx/5xx error body |
| `HaystackRetryIdempotencyTest` | Same `Idempotency-Key` on retry; WireMock `verify(2, …)` with same header |
| `HaystackCircuitBreakerTest` | N× 500 → open; fail-fast |
| `HaystackBulkheadTest` | Concurrent limit |
| `RecommenderSagaTest` | Ingest once + Call 2 fail → no second ingest; happy path quote body |

**WireMock sketch — delayed ingest + same key on retry:**

```text
stub POST /internal/v1/recommendations/submitprojectspecification
  → first: delay > ingest-read timeout (or ConnectionException)
  → second: 200 lean JSON with ingest_id

client.ingest(..., idempotencyKey=K)
// retry policy fires with same K

verify: both requests had header Idempotency-Key: K
verify: both requests had header X-Correlation-Id
```

**WireMock sketch — saga no re-ingest:**

```text
stub ingest → 200 { ingest_id: "ing_1", user_id: "u", ... }
stub Call 2 getassetrecommendations → 500 { error: "internal_error", message: "..." }

saga.submit(projectSpec)
assert exception is retryable recommend failure
verify ingest count == 1
verify Call 2 count >= 1
assert repository.savedIngestId == "ing_1"
```

No live FastAPI required for default Spring CI. Prefer fixed JSON fixtures for lean Call 1 body (FR-IX-023 fields).

#### 7.2 Manual — Spring + real haystack (optional)

1. Start haystack: `uv run uvicorn app.main:app --port 8000` (from haystack repo).  
2. Confirm S2a: double POST same `Idempotency-Key` → same `ingest_id` (see [`s2a-haystack-dependency.md`](./s2a-haystack-dependency.md)).  
3. Point Spring `haystack.base-url` at `http://localhost:8000`.  
4. Trigger portal “submit project-spec” twice with same logical submit (or force client timeout + retry).  
5. Check: one logical `ingest_id`; Call 2 returns `quoteRef`/`items`; logs share `X-Correlation-Id`; optional Call 3 Q&A works with stored ids.  

#### 7.3 Expected results

| Scenario | Expect |
|----------|--------|
| Ingest timeout retry | Same `Idempotency-Key` on every attempt |
| CB open | Fast failure to portal; no invented equipment |
| Saga Call 2 500 | Stored `ingest_id`; **one** ingest on WireMock |
| FastAPI 400 | Mapped domain error; **no** success retry loop |
| Correlation | Outbound `X-Correlation-Id` on health, Call 1, Call 2, Call 3 |

#### 7.4 Config checklist for tests

| Property area | Test tip |
|---------------|----------|
| Short ingest timeout | Force timeout scenarios in unit tests |
| CB sliding window | Low `minimumNumberOfCalls` in test profile |
| Bulkhead max concurrent | 1–2 in test profile |
| Retry max attempts | 2–3 for deterministic WireMock counts |

#### 7.5 Optional joint integration test

Not required for either CI, but useful once both land:

- Spring + real FastAPI (or Testcontainers network)  
- Same `Idempotency-Key` twice → one `ingest_id`  
- Saga Q&A fail → single ingest  

---

## 8. Suggested PR packing

| PR | Content |
|----|---------|
| **S2b-1** | Client + properties + timeouts + DTOs + WireMock happy path (2.1) |
| **S2b-2** | Resilience4j CB + bulkhead + retry-with-key (2.2 + 2.3 headers) |
| **S2b-3** | Correlation propagation (2.4) — may fold into S2b-1 |
| **S2b-4** | Portal `project-spec` saga: Call 1 → Call 2 quote → React; optional Call 3 (2.5) |
| **S2b-5** | Runbook + config docs (2.6) |

**Minimum combine:** S2b-1 + S2b-2 + headers in one PR; dual-hop saga second; docs third.

Use stage PR body: **What & Why** + **Key Changes**; link haystack S2a under Dependent PRs.

---

## 9. Exit criteria

- [ ] Per-op timeouts configured and tested  
- [ ] CB opens on forced 5xx and recovers  
- [ ] Bulkhead limits concurrency  
- [ ] Ingest always sends `Idempotency-Key`; retries reuse key  
- [ ] Correlation on every call  
- [ ] Saga does not re-ingest after Call 2 recommend failure  
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
| Correlation end-to-end | S2a logging + echo (as-built) |

```text
S2a (as-built)  ── parallel ──  S2b-1 (client timeouts)
         \                         /
          \____ join before production retries ____/
                          │
                          ▼
              Enable aggressive retry + full saga in prod
```

**Do not enable production ingest retry until S2a is live** (or accept dual-index risk).  
Details: [`s2a-haystack-dependency.md`](./s2a-haystack-dependency.md).

---

## 12. C2 trigger (explicit non-goal here)

If gateway idle timeout kills long blocking ingest POSTs in production measurement, schedule **Phase 9 / C2** (202 + poll/SSE). Do not expand this plan into C2.

---

## 13. Document control

| Version | Date | Notes |
|---------|------|--------|
| **2.0.1** | 2026-08-12 | S2b tests/timeouts use Call 2 recommend (not Q&A as second hop) |
| **2.0.0** | 2026-08-12 | Call 2 recommend quote; Call 3 chatbot Q&A |
| **1.2.1** | 2026-08-12 | Dual-hop WireMock/BDD case; align Call 2 path with Feasibility_Study |
| **1.2.0** | 2026-08-12 | Portal project-spec: Call 1 then Call 2; React receives Call 2 body |
| **1.1.0** | 2026-08-12 | Spring export: §7 test runbook; S2a as-built; package cross-links |
| **1.0.0** | 2026-08-11 | Initial S2b plan split from Phase 2 (haystack Feasibility_Study) |
