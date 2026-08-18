# Proposal: S2b Spring resilience as-built stamp

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (Spring repo — not this app) |
| **Date** | 2026-08-13 |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 2 / **S2b** |
| **Verified** | [heavy-rental-spring-rest-api `develop`](https://github.com/Heavy-Rental/heavy-rental-spring-rest-api) |
| **Spring plan** | `Feasibility_Study_Spring/phase2-s2b-spring-implementation-plan.md` **v2.1.1** |

## Why

Haystack docs still said S2b was **Ready to implement**. Spring has shipped the client, Resilience4j, saga, and WireMock pack. This archive stamps haystack Feasibility_Study / OpenSpec.

## What was verified

| Item | Spring artifact |
|------|-----------------|
| Client + timeouts | `HaystackRecommenderClient`, `HaystackProperties` |
| Resilience4j | CB `haystack`; bulkheads ingest/recommend/qa; retry (`pom.xml`) |
| Headers | `Idempotency-Key` (Call 1); `X-Correlation-Id` (all) |
| Saga | `RecommenderSagaService` + `RecommendationController` |
| Tests | WireMock client / retry / CB / bulkhead / saga dual-hop |

## Out of scope (still open)

- Multi-replica haystack idempotency store (S2a leftover)
- Spring prod ingest retry (`haystack.retry.ingest-enabled=false`)
- `traceparent` / OTel
- Phase 9 C2 (`202` / SSE)
