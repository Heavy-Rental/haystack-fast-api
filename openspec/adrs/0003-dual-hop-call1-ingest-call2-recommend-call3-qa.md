# Call 1 ingest, Call 2 recommend quote, Call 3 chatbot Q&A

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Deciders** | haystack-fast-api + Spring portal |
| **Trace** | `openspec/specs/portal-dual-hop/spec.md` (FR-PDH-001…011) |

## Context and Problem Statement

React `POST /api/recommendations/project-spec` is a Spring-owned saga. How many haystack hops, and what does each return? An earlier draft made Call 2 chatbot Q&A.

## Considered Options

* Single hop: ingest + recommend in one POST
* Dual-hop with Call 2 = Q&A (superseded 2026-08-12)
* Dual-hop with Call 2 = recommend quote; optional Call 3 = Q&A

## Decision Outcome

Chosen option: **Call 1 ingest → Call 2 recommend quote → optional Call 3 Q&A**.

```text
Call 1  POST /internal/v1/recommendations/submitprojectspecification
Call 2  POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
Call 3  POST /internal/v1/recommendations/project-knowledge/query
```

Call 1 returns the lean FR-IX-023 summary (not `results_by_need`). Call 2 is the primary body Spring maps back to React. Call 2 failure MUST NOT re-ingest.

### Consequences

* Good: portal gets a commercial quote without blocking ingest; Q&A stays optional.
* Bad / accepted: two round-trips; Spring saga owns hop order and resilience (S2b).
