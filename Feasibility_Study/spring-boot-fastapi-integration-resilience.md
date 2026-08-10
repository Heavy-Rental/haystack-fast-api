# Feasibility Study: Spring Boot ↔ haystack-fast-api Integration  
## Robust, resilient, and high-performance connectivity for the equipment recommender

| Field | Value |
|-------|--------|
| **Document type** | Architecture / integration feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 1.2.0 |
| **Application** | `haystack-fast-api` (equipment recommendation / project-spec AI feature) |
| **Caller** | Spring Boot REST API (portal / domain system of record) |
| **Related** | [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) (data planes, agent→indexing, Pgvector) |
| **As-built routes** | `POST .../from-project-spec`, `POST .../project-knowledge/query`, `GET /health` |

---

## 1. Executive summary

### Problem

Spring Boot will invoke haystack-fast-api **many times** for the recommender journey (at least: project-spec **ingest**, multi-agent **Q&A**, later **rank/price recommend**). Work on the FastAPI side can be **long-running** (indexing, KG, agents, LLM). The connection must be:

- **Robust** — correct contracts, multi-call orchestration, correlation  
- **Resilient** — timeouts, retries, circuit breaking, backpressure under failure  
- **High-performant** — efficient use of connections, CPU, and user-perceived latency  

### Hypothesis under review

> Streaming is necessary, and **HTTP/SSE** helps **file transfer** while expecting multiple Spring → FastAPI calls.

### Verdicts

| Claim | Result |
|-------|--------|
| Streaming is required for **all** Spring → FastAPI traffic | **No** — split by use case |
| **SSE is a good way to upload** project-spec files Spring → FastAPI | **No** — SSE is **server → client**; wrong direction for uploads |
| SSE / response streaming is useful | **Yes** — for **progress**, heartbeats, and optional token streaming **after** accept |
| Best default for **file + structured API** | **HTTP multipart/JSON REST** (as-built compatible) + **client resilience** |
| Best pattern for **long agent/index work** under multi-call load | **202 Accepted + job status** and/or **SSE progress**; not a single multi-minute blocking POST without care |
| Better than raw “hope the connection survives”? | **Resilience4j (or equivalent) on Spring WebClient**, idempotency keys, trace ids, bulkheads |
| gRPC / queues required day one? | **No** — optional scale-out later |

**Overall recommendation:**  
Use **REST multipart/JSON for uploads and most recommender RPCs**; use **SSE or polling for long-running progress**; orchestrate **multiple calls** as an explicit **saga** in Spring; harden with **timeouts, circuit breakers, idempotency, and correlation**. Treat SSE as a **progress channel**, not a **file pipe**.

---

## 2. Context: equipment recommender multi-call journey

haystack-fast-api is the **recommender / project-knowledge feature** next to Spring’s domain API.

```text
Portal / user
    │
    ▼
Spring Boot REST API          (auth, booking SoT, orchestration)
    │  call 1: ingest project file
    │  call 2: project-knowledge Q&A (0..N)
    │  call 3: recommend / rank+price (later reattach)
    ▼
haystack-fast-api             (Haystack pipelines, agents, stores)
```

| Call | Typical payload | Latency profile (today / target) |
|------|-----------------|----------------------------------|
| **Ingest** `POST /from-project-spec` | Multipart file or JSON text + `user_id` | Seconds–tens of seconds (index + KG + optional agent orchestration) |
| **Q&A** `POST /project-knowledge/query` | JSON `user_id`, `ingest_id`, `query` | Seconds if LLM; fast if stub |
| **Recommend** (service / future HTTP) | Needs / dates / options | Seconds–tens; multi unit-need loop via **Multi-Agent Orchestrator** after ingest **[4]** |
| **Health** `GET /health` | — | Milliseconds |

**Implication:** One protocol choice will not optimize all four. Design **per interaction type**.

Related internal flow (after request arrives) — target (dual-plane study §4.1):

1. Multi-Agent **indexing tool [4]** (project → Pgvector + KG-1).  
2. **After [4]**, Multi-Agent Orchestrator agents invoke **in-process tools** (target): project context, **Postgres-Haystack** fleet SQL, **Neo4j** graph, **ML pricing** (`predict_asset_price`).  
3. Orchestrator **synthesizes recommendation** (merge of tool results).  

Spring still uses **REST** to FastAPI. Wire resilience (this doc) stays focused on the **Spring ↔ FastAPI** connection.
---

## 3. Clarifying streaming and SSE

### 3.1 What SSE is

**Server-Sent Events (SSE)** = long-lived HTTP response where the **server pushes** `text/event-stream` events to the **client**.

| Direction | Supported well by SSE? |
|-----------|-------------------------|
| FastAPI → Spring (progress, tokens, “kg_built”) | **Yes** |
| Spring → FastAPI (upload PDF/CSV body) | **No** (not the design center) |

### 3.2 What file transfer needs

| Need | Mechanism |
|------|-----------|
| Client sends file bytes to server | **HTTP request body**: `multipart/form-data` or raw stream **upload** |
| Optional large-object offload | Upload to **object storage**, pass URL |
| Server reports progress while processing | **SSE**, chunked JSON, or **poll job status** |

### 3.3 “Streaming” means several different things

| Kind of streaming | Purpose | Fit for this project |
|-------------------|---------|----------------------|
| **Request body streaming upload** | Send large file without buffering entire file in Spring heap | Useful for large PDFs; still **HTTP POST**, not SSE |
| **Response streaming (SSE / NDJSON)** | Progress & partial results while job runs | **Yes** after accept |
| **gRPC streaming** | Chunked RPC both ways | Optional later |
| **WebSocket** | Bidirectional messages | Usually overkill for Spring service client |

**Conclusion:** Streaming **can** help resilience and UX for **long-running recommender steps**, but **SSE is not the file-transfer protocol**. Prefer **multipart POST** (or object storage) for the project specification file.

---

## 4. Options matrix

### 4.1 Synchronous REST + multipart / JSON (baseline)

```text
Spring WebClient
  .post()
  .uri("/api/v1/recommendations/from-project-spec")
  .body(MultipartBody...)  // or JSON project_text
  .retrieve()
  .bodyToMono(IngestResponse.class)
```

| Pros | Cons |
|------|------|
| Matches **as-built** FastAPI | Long jobs hold the HTTP connection |
| Simple OpenAPI, Postman, LB | Gateway/proxy idle timeouts kill slow index+agent |
| Easy auth headers, retries with care | Naive retry may double-ingest without idempotency |

**Feasibility:** **GO — default for uploads and most unary calls.**

### 4.2 SSE (Server-Sent Events)

```text
Spring: open SSE to GET/POST stream endpoint
FastAPI: yield events: step=indexing, step=kg, step=done, data={ingest_id}
```

| Pros | Cons |
|------|------|
| Good UX / ops visibility | Not for uploading files |
| Heartbeats keep proxies happier *if* events keep flowing | Spring must consume Flux carefully; reconnect semantics |
| Natural for agent token streaming | Sticky/long connections; scale considerations |

**Feasibility:** **GO for progress and answer streaming; NO as primary file upload.**

### 4.3 Chunked HTTP / NDJSON response stream

Same idea as SSE without `EventSource` framing: `application/x-ndjson` lines.

**Feasibility:** **GO** — often easier with Spring `WebClient` body flux than browser-centric SSE APIs.

### 4.4 Async job pattern (202 Accepted) — strongly recommended for robustness

```text
[1] Spring POST /ingest          → 202 { job_id }
[2] Spring GET  /jobs/{job_id}   → 200 { status: running|succeeded|failed, ingest_id?, error? }
    or SSE /jobs/{job_id}/events → progress stream
[3] Spring POST /project-knowledge/query  with ingest_id
[4] Spring POST /recommend (later)
```

| Pros | Cons |
|------|------|
| Decouples **LB timeout** from **pipeline duration** | Extra endpoints + job store (Redis/DB/memory) |
| Natural multi-call saga | Client must poll or subscribe |
| Retries on “start job” vs “get status” are clearer | Operational complexity |

**Feasibility:** **GO — best resilience for multi-step recommender under real traffic.**

### 4.5 Object storage offload (large files)

```text
Spring → Spaces/S3 PUT file
Spring → FastAPI POST { user_id, file_url, filename, content_type }
FastAPI fetches object (or shared volume) → ByteStream → indexing
```

| Pros | Cons |
|------|------|
| Small API payloads; easy retry of “start ingest” | Extra infra (Spaces); IAM/presign |
| Avoids double memory buffering in Spring+FastAPI | Latency of fetch; virus scan policy |

**Feasibility:** **GO when project files are routinely multi-MB**; optional for small text/csv.

### 4.6 WebSocket

Full duplex. Sticky sessions, harder horizontal scaling for pure service-to-service.

**Feasibility:** **Not recommended** for Spring→FastAPI recommender unless product needs interactive bidirectional sessions.

### 4.7 gRPC (HTTP/2 + Protobuf)

Unary and streaming RPCs; efficient for high QPS internal APIs. Java and Python both supported with investment in stubs, observability, and mesh config. File upload = client streaming of chunks.

**Feasibility:** **Optional Phase C3** if REST is measured bottleneck on small JSON RPCs. **Not required** to achieve resilience for the current recommender shape.

### 4.8 Message queue (RabbitMQ / Kafka / cloud queue)

```text
Spring publish ProjectSpecSubmitted { user_id, file_ref }
haystack worker consume → index → emit ProjectSpecIndexed
Spring consumes or polls result
```

| Pros | Cons |
|------|------|
| Peak isolation; FastAPI restart tolerance | Eventual consistency; more moving parts |
| Natural backpressure | Harder synchronous UX without status API |

**Feasibility:** **GO for spike absorption / async product modes**; complement REST status API.

### 4.9 HTTP/2 multiplexing

Multiple Spring calls share connections (multiplex). Improves connection efficiency; still REST or gRPC underneath.

**Feasibility:** **Enable where platform allows** — complementary, not a full architecture.

### 4.10 Comparison summary

| Option | File upload | Long job | Multi-call saga | Complexity | Priority |
|--------|-------------|----------|-----------------|------------|----------|
| REST multipart/JSON | **Excellent** | Fair (timeouts) | Good | Low | **P0 default** |
| SSE progress | Poor as upload | **Excellent** | Good | Medium | **P1 with jobs** |
| NDJSON stream | Poor as upload | **Excellent** | Good | Medium | **P1 alt** |
| 202 + poll | Via REST body | **Excellent** | **Excellent** | Medium | **P0/P1** |
| Object storage + ref | **Excellent large** | N/A | Good | Medium | **P1 if large files** |
| WebSocket | Possible | Good | Medium | High | Avoid |
| gRPC | Streaming possible | Good | Good | High | P2 optional |
| Queue | Via ref/event | **Excellent** | Event-driven | High | P2 spike/isolation |

---

## 5. Resilience patterns (must-haves)

Resilience is **mostly orthogonal** to SSE vs REST. A fragile client will fail on both.

### 5.1 Spring Boot client (WebClient + Resilience4j or equivalent)

| Pattern | Guidance |
|---------|----------|
| **Timeouts** | Separate connect vs response; **longer** for ingest than health/Q&A; never infinite |
| **Retry** | Exponential backoff + jitter; **only** with **idempotency key** on POST ingest |
| **Circuit breaker** | Open when haystack error rate/latency exceeds threshold; fail fast to portal |
| **Bulkhead / concurrency limit** | Cap parallel calls into recommender so one traffic spike cannot exhaust Tomcat/Netty + FastAPI workers |
| **Fallback** | Degrade UX (“recommendation delayed”) not silent wrong equipment |
| **Health-aware routing** | Optional: check `/health` before batch jobs |
| **Connection pool** | Tune WebClient max connections per host |

### 5.2 Idempotency and multi-call safety

| Header / field | Purpose |
|----------------|---------|
| `Idempotency-Key` or `X-Client-Request-Id` | Spring generates UUID per logical ingest; FastAPI stores and returns same `ingest_id` on retry |
| `X-Correlation-Id` / W3C `traceparent` | End-to-end logs across Spring and FastAPI |
| `user_id` + `ingest_id` | Stable handles for subsequent Q&A / recommend calls |

Without idempotency, **retry after timeout** may **double-index** the same project file.

### 5.3 FastAPI / haystack-fast-api server

| Pattern | Guidance |
|---------|----------|
| **Threadpool offload** | Keep as-built: sync Haystack/agent work off the event loop (`run_in_threadpool`) |
| **Worker limits** | Bound concurrent indexing jobs |
| **Explicit errors** | Stable `{"error","message"}`; distinguish 4xx (client) vs 5xx (retryable) |
| **503 + Retry-After** | When saturated |
| **Readiness** | `/health` reflects Postgres (and later Pgvector) so Spring/LB can drain |
| **Job store** (if 202 pattern) | Persist job state outside process memory for multi-replica |

### 5.4 Multi-call orchestration (saga in Spring)

```text
1. INGEST
   - POST ingest (multipart) with Idempotency-Key
   - Wait: blocking with long timeout  OR  202 + poll/SSE until succeeded
   - Persist ingest_id against user/session in Spring

2. Q&A (0..N)
   - POST query with user_id + ingest_id
   - Retry transient 5xx; do not re-ingest on Q&A failure

3. RECOMMEND (later)
   - POST recommend with same identity + needs/dates
   - Prefer one batched call over N chatty calls per unit-need when possible
```

**Compensation:** If ingest succeeded but business cancels, Spring may call a future “discard session” API (TTL on Pgvector also helps — see dual-plane study).

---

## 6. Performance considerations

| Factor | Recommendation |
|--------|----------------|
| **Perceived latency** | Return early progress (SSE/job events): `accepted` → `indexing` → `kg` → `ready` |
| **Actual latency** | Dominated by embed/KG/LLM — protocol choice won’t remove that |
| **Chatty multi-call** | Prefer coarse APIs (one recommend for all needs) over per-need HTTP |
| **Payload size** | Small text: JSON OK; large PDF: multipart stream or object storage |
| **Horizontal scale** | After **Pgvector** cutover, multiple FastAPI replicas share store; avoid process-local-only sessions for prod multi-instance |
| **Connection reuse** | HTTP/2 + pooled WebClient |
| **LLM streaming** | SSE for token stream only if product needs live typing; else unary final answer |

**SSE does not speed up indexing.** It improves observability and can avoid idle-timeout drops **if** heartbeats are sent while work continues server-side (often still better with **202 + background worker** so the upload request can finish quickly).

---

## 7. Platform / load balancer implications (incl. DigitalOcean)

| Concern | Implication |
|---------|-------------|
| **Proxy idle timeout** | Blocking 5–15+ min POSTs fail; use job pattern or continuous SSE heartbeats |
| **Body size limits** | Configure ingress/nginx/App Platform max body for PDF uploads |
| **Sticky sessions** | Needed for process-local InMemory across Q&A calls **or** move to Pgvector + shared session/job store |
| **HTTP/2** | Helpful for multiplexed multi-call; verify end-to-end support |
| **mTLS / private VPC** | Preferred for Spring → FastAPI internal traffic on DO VPC |
| **Timeouts at every hop** | Gateway < Spring client read timeout should be designed deliberately (or use 202) |

---

## 8. Mapping to as-built haystack-fast-api

| As-built | Integration note |
|----------|------------------|
| `POST /from-project-spec` | Unary REST ingest — **keep** as file/JSON entry; optionally add 202 mode later |
| `POST /project-knowledge/query` | Unary REST — second Spring call after ingest |
| `GET /health` | Resilience probe |
| `run_in_threadpool` | Correct for sync pipelines under async FastAPI |
| No job API / no SSE today | Gap for long-running robustness — Phase C2 |

---

## 9. Recommended target shapes

### 9.1 Near-term (robust enough, low change) — Phase C1

```text
Spring  --multipart REST-->  FastAPI ingest  -->  200 IngestResponse
Spring  --JSON REST------->  FastAPI Q&A     -->  200 Answer
Spring  --JSON REST------->  FastAPI recommend (later)
```

**Hardening (required):**

- WebClient timeouts per operation  
- Circuit breaker + bulkhead  
- `Idempotency-Key` on ingest  
- Trace/correlation headers  
- Document max file size and expected p95 latency for ops  

### 9.2 Production recommender (resilient long jobs) — Phase C2

```text
Spring  --multipart or file_url-->  POST /ingest  -->  202 { job_id }
Spring  --SSE or poll----------->  job events/status until ready { ingest_id }
Spring  --JSON------------------>  Q&A / recommend using ingest_id
```

Optional: large files via **Spaces** + URL.

### 9.3 Scale / internal mesh — Phase C3 (optional)

- HTTP/2 everywhere practical  
- Queue for async ingest under peak  
- gRPC only if metrics justify  

---

## 10. Phased roadmap (connection track “C”)

| Phase | Outcome | Depends on |
|-------|---------|------------|
| **C1** | Resilient REST client + idempotent ingest + multi-call saga in Spring | As-built FastAPI |
| **C2** | 202 jobs + poll and/or SSE progress; optional object storage | Job store; timeout policy |
| **C3** | Queue and/or gRPC if needed | Metrics from C1/C2 |

**Independence:** C1–C2 do **not** require Neo4j or CDC. They compose with agent-first indexing and Pgvector cutover from the other study.

---

## 11. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Treating SSE as upload mechanism | High | Multipart/object storage for files; SSE for progress only |
| Blocking multi-minute POST through gateway | High | C2 job pattern; tune timeouts consciously |
| Double ingest on retry | High | Idempotency-Key + server-side dedupe |
| Q&A hits wrong replica (InMemory) | High | Sticky sessions **or** Pgvector + shared session (I1) |
| Circuit open storms portal | Medium | Fallback messaging; bulkhead |
| Over-building gRPC early | Medium | Measure REST first |
| No backpressure | Medium | 503 + limits + Spring bulkhead |
| Missing trace correlation | Medium | W3C trace context on every call |

---

## 12. Suggested spikes

1. **Spring WebClient** multipart ingest against local FastAPI; measure p50/p95; break with 60s proxy timeout → motivates C2.  
2. **Idempotency:** same key twice → one logical ingest.  
3. **Resilience4j:** kill FastAPI mid-call; verify CB opens and recovers.  
4. **SSE or NDJSON:** stream three fake steps after accept; Spring consumes to completion.  
5. **202 job:** in-memory job dict single worker; poll until `succeeded`.  
6. **Large file:** 20MB PDF multipart vs Spaces URL path.  

---

## 13. Open questions

1. Expected **p95 duration** of ingest (index+KG+agent) in production?  
2. Max project file **size** and types in the portal?  
3. Does the portal need **live progress UI**, or is “spinner until done” enough?  
4. Is Spring→FastAPI only **private VPC**, or public edge?  
5. Target **concurrency** (simultaneous ingests)?  
6. Must recommend wait for **Neo4j fleet graph**, or only project KG-1 + SQL mirror?  
7. Preference: Spring **WebClient** reactive vs **RestClient** blocking for this client?  

---

## 14. References

### In-repo

- [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) — agent→indexing, Pgvector, multi-user stores  
- `openspec/specs/indexing/` — ingest contract  
- `openspec/specs/knowledge-graph/` — Q&A contract  
- `openspec/AGENTS.md` — live path map  

### Industry patterns

- REST request/response for uploads and RPCs  
- SSE for server→client event streams (not classic file upload)  
- Async job / 202 Accepted for long-running work  
- Resilience4j (Spring): timeout, retry, circuit breaker, bulkhead  
- gRPC for internal high-QPS service meshes (optional)  
- Object storage for large binary handoff between services  

### Haystack / FastAPI as-built

- FastAPI async routes + `run_in_threadpool` for sync pipelines  
- Multipart and JSON ingest already implemented  

---

## 15. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial study: Spring↔FastAPI resilience; SSE vs upload; multi-call recommender; C1–C3 |
| **1.1.0** | 2026-08-10 | Call 3 recommend maps to Multi-Agent after [4] + tools (pricing, Neo4j, Postgres-Haystack) |
| **1.2.0** | 2026-08-10 | Remove FastMCP; in-process tools only |

---

## 16. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| File transfer Spring → FastAPI | **HTTP multipart/JSON** (or **object storage + URL**) |
| Use SSE for file upload? | **No** |
| Use SSE / NDJSON for? | **Progress, heartbeats, optional token stream** |
| Multiple Spring calls | **Explicit saga**: ingest → (wait) → Q&A → recommend |
| Long index/agent work | **202 + poll/SSE** (C2) when timeouts hurt |
| Resilience | **Timeouts + CB + bulkhead + idempotency + traces** on Spring client |
| Performance first win | Coarse APIs, pool HTTP/2, don’t chat per unit-need; Pgvector for multi-replica |
| gRPC / queue day one? | **No** — C3 if measured need |
| First ship | **C1 resilient REST** on as-built endpoints; design C2 before heavy agent latency in prod |

### Direct answer to the streaming/SSE idea

| Idea | Verdict |
|------|---------|
| “Streaming is necessary” | **Sometimes** — for **progress** and **large upload body streaming**, not for every call |
| “HTTP/SSE helps file transfer” | **SSE does not replace multipart upload**; use SSE **alongside** REST for status |
| “Multiple calls from Spring” | **Yes, expected** — make them **orchestrated, idempotent, and correlated**, not one fragile mega-connection |
| Better overall approach | **REST + resilience + async job/progress channel** beats “one long SSE that also tries to carry the file” |
