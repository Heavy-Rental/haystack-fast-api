# S2a dependency — haystack-fast-api (FastAPI half of C1)

| Field | Value |
|-------|--------|
| **Document type** | Dependency note for Spring S2b |
| **Version** | **1.2.0** |
| **Date** | 2026-08-12 |
| **Status** | **S2a as-built** on haystack — plan **v1.1.2 Implemented** (2026-08-12) |
| **Trace** | FR-IX-024 (`Idempotency-Key`) · FR-IX-025 (`X-Correlation-Id` / `traceparent`) |
| **Sibling Spring plan** | [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md) |
| **Portal saga** | [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md) |
| **Haystack plan** | `Feasibility_Study/phase2-s2a-haystack-implementation-plan.md` (when haystack clone present) |

---

## 1. Why Spring cares

Without server-side idempotency, a Spring **timeout retry** of Call 1 can **double-index** the same project-spec (two `ingest_id`s, wasted work, confused sessions).

S2a on haystack makes Call 1 **safe to retry** when Spring reuses the same `Idempotency-Key`.

---

## 2. What S2a shipped (FastAPI)

| Item | Behaviour |
|------|-----------|
| **FR-IX-024** `Idempotency-Key` | **Call 1 only.** Optional header; scoped with `user_id`; successful lean **200** stored process-locally and **replayed** (same `ingest_id`); **4xx/5xx not cached**; concurrent same key uses **single-flight** |
| **FR-IX-025** correlation | **All routes** (Call 1, Call 2 recommend, Call 3 Q&A, health): optional `X-Correlation-Id` (mint if missing); log + **echo** |
| Error body | Unchanged `{"error","message"}` |
| FR-IX-023 body | Unchanged lean summary fields on Call 1 |

**Hard limit:** store is **process-local memory** (optional TTL, default 24h via `IDEMPOTENCY_TTL_SECONDS`). **Not multi-replica shared.** Multiple FastAPI pods without a sticky/shared store can still double-index across instances.

---

## 3. Headers Spring must send

| Header | Call 1 | Call 2 recommend | Call 3 Q&A / health |
|--------|--------|-------------------|---------------------|
| `Idempotency-Key` | **Yes** (every logical submit; **reuse on retry**) | N/A | N/A |
| `X-Correlation-Id` | Yes (recommended) | Yes | Yes |
| `traceparent` | Optional | Optional | Optional |

Rules:

1. Generate **one** UUID per React `POST /api/recommendations/project-spec` (logical submit) at saga start.  
2. Send that key only on **Call 1** (`submitprojectspecification`). Call 2 does not use `Idempotency-Key`.  
3. On timeout / 5xx retry of **ingest**, send the **same** key — do not mint a new one.  
4. Do not reuse a key for a **different** logical project-spec.  
5. **4xx** → fix input; do not treat as successful cache hit.

---

## 4. Join gate (production retries)

```text
S2a (haystack) — as-built     ── parallel OK ──  S2b client timeouts (Spring)
         \                                              /
          \__________ join before production ingest retries __________/
                                    │
                                    ▼
                    Enable aggressive retry + full saga in prod
```

| Work | Parallel? | Prod ingest retry? |
|------|-----------|---------------------|
| Spring timeouts + WireMock | Yes | No until S2a available |
| Spring CB / bulkhead | Yes | No until S2a for **ingest** retry |
| Correlation headers alone | Yes | Safe anytime (logging) |
| **Ingest retry with key** | — | **Only with S2a live** |

---

## 5. Session affinity (Call 1 → Call 2 / Call 3)

Call 2 recommend and Call 3 chatbot both use the **process-local** session registered on successful Call 1.

| C1 practice | Until |
|-------------|--------|
| Sticky session to one FastAPI instance **or** single instance | Phase 5 Pgvector / shared session |
| Persist `ingest_id` in Spring regardless | Always |

S2a idempotency does **not** replace session affinity for Call 2/3.

---

## 6. How to verify FastAPI S2a

If you have the haystack repo (plan **v1.1.2** §7 runbook):

```bash
cd haystack-fast-api
uv run pytest tests/test_ingest_idempotency.py tests/test_correlation_middleware.py -q
```

| Module | Checks |
|--------|--------|
| `tests/test_ingest_idempotency.py` | Same key → same `ingest_id`; multipart; failure not cached; single-flight; blank key; TTL |
| `tests/test_correlation_middleware.py` | Echo/mint; Call 2 recommend + Call 3 Q&A echo `X-Correlation-Id` |

Manual: double POST same `Idempotency-Key` on Call 1 → same `ingest_id`.

```bash
KEY=$(uuidgen)
BODY='{"user_id":"user_demo","project_text":"Need scissors lift"}'
curl -s -X POST "$HAYSTACK/internal/v1/recommendations/submitprojectspecification" \
  -H "Content-Type: application/json" -H "Idempotency-Key: $KEY" -d "$BODY"
# repeat with same KEY → same ingest_id
```

---

## 7. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.2.0** | 2026-08-12 | Call 2 recommend + Call 3 Q&A in header/session tables |
| **1.1.1** | 2026-08-12 | S2a v1.1.2 as-built; FR tags; Call 2 correlation; pytest modules |
| **1.1.0** | 2026-08-12 | Portal project-spec saga; key at P0 covers Call 1 only |
| **1.0.0** | 2026-08-12 | Spring export; S2a as-built dependency |
