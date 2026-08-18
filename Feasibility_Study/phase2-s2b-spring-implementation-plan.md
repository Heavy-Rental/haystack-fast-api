# Phase 2 Implementation Plan — S2b (Spring Boot REST API)

> **Spring handoff package:** The full S2b package for the Spring Boot team (wire contract, S2a dependency, resilience study, enhanced plan with **test runbook**, HANDOFF) lives in:
>
> **[`../Feasibility_Study_Spring/`](../Feasibility_Study_Spring/)**  
> especially [`../Feasibility_Study_Spring/phase2-s2b-spring-implementation-plan.md`](../Feasibility_Study_Spring/phase2-s2b-spring-implementation-plan.md) (**v2.0.0**).
>
> Copy that entire folder into the Spring Boot repository. This file remains a **pointer + short summary** so the haystack `Feasibility_Study/` index stays navigable.

| Field | Value |
|-------|--------|
| **Document type** | Implementation plan (stage-scoped) — **summary / pointer** |
| **Stage** | **S2b** — Resilience C1, Spring Boot client half |
| **Repo** | Spring Boot REST API (portal / domain SoT) |
| **Canonical implementer doc** | [`../Feasibility_Study_Spring/phase2-s2b-spring-implementation-plan.md`](../Feasibility_Study_Spring/phase2-s2b-spring-implementation-plan.md) |
| **Version** | **2.0.1** (pointer; Spring canonical **2.1.1**) |
| **Date** | 2026-08-13 |
| **Status** | **As-built** in [heavy-rental-spring-rest-api `develop`](https://github.com/Heavy-Rental/heavy-rental-spring-rest-api) |
| **Sibling** | [`phase2-s2a-haystack-implementation-plan.md`](./phase2-s2a-haystack-implementation-plan.md) — **as-built** |
| **Parent** | [`implementation-plan.md`](./implementation-plan.md) Phase 2 |
| **Study (haystack copy)** | [`spring-boot-fastapi-integration-resilience.md`](./spring-boot-fastapi-integration-resilience.md) |
| **Study (Spring export)** | [`../Feasibility_Study_Spring/spring-boot-fastapi-integration-resilience.md`](../Feasibility_Study_Spring/spring-boot-fastapi-integration-resilience.md) |

---

## Goal (summary)

Harden Spring as the **orchestrating client** of haystack-fast-api: per-op timeouts, Resilience4j CB + bulkhead, `Idempotency-Key` on ingest (reuse on retry), correlation headers, and the **portal project-spec saga**:

```text
React POST /api/recommendations/project-spec
  → Call 1 submitprojectspecification → persist ingest_id
  → Call 2 getassetrecommendations → **recommend quote** primary to React
  → optional Call 3 project-knowledge/query → chatbot Q&A
```

Never re-ingest on Call 2 failure. Full table: [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md).

## Shared wire (summary)

| Item | Convention |
|------|------------|
| Ingest | `POST /internal/v1/recommendations/submitprojectspecification` |
| Call 2 recommend | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` |
| Call 3 chatbot | `POST /internal/v1/recommendations/project-knowledge/query` |
| Health | `GET /health` |
| Headers | `Idempotency-Key`, `X-Correlation-Id`, optional `traceparent` |
| Errors | `{"error","message"}` |

## Dependency on S2a

**Do not enable production ingest retry until S2a is live** (as-built on haystack: process-local store + correlation). Parallel OK for client timeouts; **join before prod retries**.

## PR packing (summary)

| PR | Content |
|----|---------|
| S2b-1 | Client + timeouts + DTOs + WireMock |
| S2b-2 | Resilience4j + retry-with-key |
| S2b-3 | Correlation (may fold into S2b-1) |
| S2b-4 | Saga + persist `ingest_id` |
| S2b-5 | Runbook |

## Exit criteria (as-built in Spring — 2026-08-13 verify)

- [x] Per-op timeouts tested  
- [x] CB opens on forced 5xx and recovers  
- [x] Bulkhead limits concurrency  
- [x] Ingest always sends `Idempotency-Key`; retries reuse key  
- [x] Correlation on every call (`X-Correlation-Id`; `traceparent` deferred)  
- [x] Saga does not re-ingest after Call 2 recommend failure  
- [x] Runbook + WireMock suite green  

Canonical checklist + artifact map: Spring `Feasibility_Study_Spring/phase2-s2b-spring-implementation-plan.md` **v2.1.1**. Prod ingest retry remains `haystack.retry.ingest-enabled=false`.  

---

## Document control

| Version | Date | Notes |
|---------|------|--------|
| **2.0.1** | 2026-08-13 | Status → **As-built** (verified Spring `develop` plan v2.1.1 + client/Resilience4j/saga) |
| **1.2.1** | 2026-08-12 | Pointer version matches Spring export v1.2.1 |
| **1.2.0** | 2026-08-12 | Portal dual-hop saga summary (Call 1 then Call 2 → React) |
| **1.1.0** | 2026-08-12 | Pointer to `Feasibility_Study_Spring/` export (full plan + runbook) |
| **1.0.0** | 2026-08-11 | Initial S2b plan split from Phase 2 |
