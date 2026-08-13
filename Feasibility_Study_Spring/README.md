# Feasibility studies — Spring Boot (export package)

| Field | Value |
|-------|--------|
| **Version** | **2.0.2** |
| **Date** | 2026-08-12 |
| **Audience** | Spring Boot engineers integrating with `haystack-fast-api` |

**Behaviour SoT:** haystack OpenSpec + this package for Spring orchestration.

### Aligned with haystack `Feasibility_Study/` (Call numbering)

| Call | Path | Role |
|------|------|------|
| **1** | `.../submitprojectspecification` | Ingest |
| **2** | `.../project-knowledge/getassetrecommendations` | **Recommend / quote** |
| **3** | `.../project-knowledge/query` | **Chatbot Q&A** |

| Topic | Haystack | This package |
|-------|----------|--------------|
| Portal saga | `implementation-plan.md` §1.2.0 (v3.5+) | [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md) **2.0** |
| Call 2 recommend | OpenSpec recommend contract | [`wire-contract-call1-call2.md`](./wire-contract-call1-call2.md) **2.0** |
| Call 3 Q&A | KG contract `project-knowledge-query.md` | Same wire doc § Call 3 |
| S2a | `phase2-s2a-*.md` v1.1.2 | [`s2a-haystack-dependency.md`](./s2a-haystack-dependency.md) |
| S2b | pointer | [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md) **2.0** — **as-built in Spring repo** (canonical **2.1.1**) |

```text
React  POST /api/recommendations/project-spec
  → Call 1 ingest → Call 2 recommend quote → React
  → optional Call 3 chatbot Q&A
```

## Reading order

1. [`portal-to-haystack-mapping.md`](./portal-to-haystack-mapping.md)  
2. [`wire-contract-call1-call2.md`](./wire-contract-call1-call2.md)  
3. [`call1-ingest-response-for-spring.md`](./call1-ingest-response-for-spring.md)  
4. [`s2a-haystack-dependency.md`](./s2a-haystack-dependency.md)  
5. [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md)  
6. [`HANDOFF.md`](./HANDOFF.md)  

## Documents

| Document | Version |
|----------|---------|
| portal-to-haystack-mapping.md | **2.0.0** |
| wire-contract-call1-call2.md | **2.0.0** |
| call1-ingest-response-for-spring.md | **2.0.0** |
| phase2-s2b-spring-implementation-plan.md | **2.0.1** |
| spring-boot-fastapi-integration-resilience.md | **2.2.1** |
| s2a-haystack-dependency.md | **1.2.0** |
| HANDOFF.md | **2.0.0** |

## Copy into Spring repo

```bash
cp -R Feasibility_Study_Spring /path/to/spring-boot/docs/Feasibility_Study
```
