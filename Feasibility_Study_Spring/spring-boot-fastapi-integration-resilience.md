# Feasibility Study: Spring Boot ↔ haystack-fast-api Integration  
## Robust, resilient connectivity for the equipment recommender (Spring export)

| Field | Value |
|-------|--------|
| **Document type** | Architecture / integration feasibility study |
| **Status** | Complete (study) — Spring-primary export adaptation |
| **Date** | 2026-08-12 |
| **Version** | **2.2.1** |
| **Application (caller)** | Spring Boot REST API (portal / domain system of record) |
| **Dependency** | `haystack-fast-api` (recommender / project-knowledge feature) |
| **Package** | [`README.md`](./README.md) |
| **Implementer plan** | [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md) |
| **Wire contract** | [`wire-contract-call1-call2.md`](./wire-contract-call1-call2.md) |
| **Portal mapping** | [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md) |
| **Upstream study** | Adapted from haystack `Feasibility_Study/spring-boot-fastapi-integration-resilience.md` v1.3.1 |

---

## 1. Executive summary

### Problem

Spring Boot will invoke haystack-fast-api **multiple times** per recommender journey (project-spec **ingest**, **Call 2 recommend/quote**, optional **Call 3 chatbot Q&A**). Work on FastAPI can be **long-running** (indexing, KG, agents, LLM). The connection must be:

- **Robust** — correct contracts, multi-call orchestration, correlation  
- **Resilient** — timeouts, retries, circuit breaking, backpressure  
- **High-performant** — efficient connections and acceptable user-perceived latency  

### Verdicts

| Claim | Result |
|-------|--------|
| Streaming required for all Spring → FastAPI traffic | **No** — split by use case |
| SSE is a good way to **upload** project-spec files | **No** — SSE is server → client |
| SSE useful for progress after accept | **Yes** — later (C2); not S2b |
| Best default for file + structured API | **HTTP multipart/JSON REST** + **client resilience** |
| gRPC / queues day one | **No** — optional later (C3) |

**Overall recommendation:**  
Use **REST multipart/JSON** for uploads and recommender RPCs; orchestrate **multiple calls** as an explicit **saga in Spring**; harden with **timeouts, circuit breakers, bulkheads, idempotency keys, and correlation**. Treat SSE as a **progress channel** (Phase C2), not a file pipe.

**C1 split:**

| Stage | Owner | Status |
|-------|--------|--------|
| **S2a** | haystack-fast-api | **As-built** — server `Idempotency-Key` + correlation ([`s2a-haystack-dependency.md`](./s2a-haystack-dependency.md)) |
| **S2b** | Spring Boot | **As-built** — client, Resilience4j, saga, headers ([heavy-rental-spring-rest-api](https://github.com/Heavy-Rental/heavy-rental-spring-rest-api)) |

---

## 2. Multi-call journey

**Portal project-spec submit** (normative product path):

```text
React  POST /api/recommendations/project-spec
    │
    ▼
Spring Boot REST API          (auth, booking SoT, orchestration)  ← YOU
    │  Call 1: ingest  (submitprojectspecification)
    │  Call 2: RECOMMEND quote  (getassetrecommendations) → React primary
    │  Call 3: CHATBOT Q&A  (project-knowledge/query) optional
    ▼
haystack-fast-api
```

See [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md).

| Call | Path | Latency profile |
|------|------|-----------------|
| **1 Ingest** | `POST /internal/v1/recommendations/submitprojectspecification` | Seconds–tens of seconds |
| **2 Recommend** | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` | Seconds (fleet + price MVP) |
| **3 Chatbot Q&A** | `POST /internal/v1/recommendations/project-knowledge/query` | Seconds if LLM; fast if stub |
| **Health** | `GET /health` | Milliseconds |

### FastAPI-internal (out of Spring scope)

After a request arrives, FastAPI may run indexing gate, multi-agent Workers, and synthesis. Spring does **not** implement Coordinator / Worker / Delegator roles — those stay inside FastAPI. Spring only needs stable REST + saga + resilience.

---

## 3. Streaming and SSE (short)

| Need | Mechanism |
|------|-----------|
| Spring sends file bytes | **HTTP POST** multipart or JSON — **not** SSE |
| Progress while job runs | SSE / poll job status — **C2**, not C1/S2b |
| Large PDF without huge heap | Stream multipart body; or object storage + URL later |

---

## 4. Options (summary)

| Option | Role in C1 |
|--------|------------|
| **Sync REST + multipart/JSON** | **Baseline** — implement S2b against this |
| **202 + poll / SSE** | Phase **C2** if gateway kills long blocking POSTs |
| **gRPC / queues** | Phase **C3** only if metrics justify |

---

## 5. Resilience patterns (Spring-centric)

### 5.1 WebClient / RestClient + Resilience4j

| Pattern | Guidance |
|---------|----------|
| **Timeouts** | Connect vs read separate; **ingest ≫ recommend ≫ Q&A ≫ health**; never infinite |
| **Retry** | Exponential backoff + jitter; **ingest only with same `Idempotency-Key`**; limited attempts |
| **Circuit breaker** | Open on error rate / slow calls; fail fast to portal |
| **Bulkhead** | Cap concurrent haystack calls (prefer separate ingest vs recommend vs Q&A limits) |
| **Fallback** | “Recommender unavailable / delayed” — never invent equipment |
| **Connection pool** | Tune max connections per host |

### 5.2 Idempotency and multi-call safety

| Header / field | Purpose |
|----------------|---------|
| `Idempotency-Key` | UUID per logical ingest; **reuse on timeout retry**; FastAPI S2a replays same `ingest_id` |
| `X-Correlation-Id` / `traceparent` | End-to-end logs |
| `user_id` + `ingest_id` | Handles for Call 2 / later Call 3 |

Without S2a + same key, **retry after timeout may double-index**.

### 5.3 Saga in Spring

Triggered by React **`POST /api/recommendations/project-spec`**:

```text
1. INGEST (Call 1)
   - POST .../submitprojectspecification with Idempotency-Key + correlation
   - Persist ingest_id on booking/session

2. RECOMMEND (Call 2) — required hop for portal submit UX
   - POST .../project-knowledge/getassetrecommendations
   - user_id + ingest_id + optional query
   - Returns quote / items[]; map to React as primary response
   - Retry transient 5xx; NEVER re-ingest on Call 2 failure

3. CHATBOT Q&A (Call 3) — optional follow-ups
   - POST .../project-knowledge/query
   - user_id + ingest_id + query required
```

### 5.4 FastAPI side (context only)

Threadpool offload, stable `{"error","message"}`, process-local sessions until Pgvector. Spring maps 4xx vs 5xx correctly.

---

## 6. Performance & platform

| Factor | Recommendation |
|--------|----------------|
| Perceived latency | Spinner OK for C1; progress UI → C2 |
| Proxy idle timeout | Measure; long POST may force C2 |
| Body size | Align gateway + Spring + FastAPI |
| Sticky sessions | Process-local Call 2 until Phase 5 shared session |
| Private VPC | Preferred for Spring → FastAPI |

---

## 7. Phased roadmap (connection track “C”)

| Phase | Outcome | Spring work |
|-------|---------|-------------|
| **C1 / S2b** | Resilient REST client + saga + keys | **This package** |
| **C2** | 202 jobs + poll/SSE | Later plan |
| **C3** | Queue / gRPC if needed | Metrics-driven |

---

## 8. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| SSE used as upload | High | Multipart only for files |
| Blocking multi-minute POST through gateway | High | Measure; C2 if needed |
| Double ingest on retry | High | S2a + same `Idempotency-Key` |
| Q&A hits wrong replica | High | Sticky / single instance until shared session |
| Circuit open storms portal | Medium | Fallback copy + bulkhead |
| Missing correlation | Medium | Headers on every call |

---

## 9. Suggested spikes (Spring)

1. WebClient multipart ingest; measure p50/p95; break with short timeout → motivates retry + C2.  
2. Same `Idempotency-Key` twice against haystack with S2a → one `ingest_id`.  
3. Resilience4j: kill FastAPI mid-call; CB opens and recovers.  
4. Saga: ingest OK, Call 2 recommend 500 → WireMock shows **one** ingest only.  

---

## 10. Open questions (ops)

1. Expected **p95** ingest duration in production?  
2. Max project file **size** and types?  
3. Live progress UI required, or spinner until done?  
4. Spring→FastAPI **private VPC** only?  
5. Target concurrent ingests?  
6. Preference: **WebClient** reactive vs **RestClient** blocking?  

---

## 11. Document control

| Version | Date | Notes |
|---------|------|--------|
| **2.2.1** | 2026-08-12 | Timeouts/bulkhead/saga wording: recommend not Q&A as second hop |
| **2.2.0** | 2026-08-12 | Call 2 recommend + Call 3 chatbot Q&A |
| **2.1.0** | 2026-08-12 | Portal dual-hop (Call 2 was Q&A; superseded) |
| **2.0.0** | 2026-08-12 | Spring export package; S2a as-built; internal routes; C1 = S2a+S2b |
| **1.3.1** | 2026-08-10 | Upstream haystack-centric study (source) |
