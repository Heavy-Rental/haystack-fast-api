# Portal → Spring → haystack mapping (project-spec submit saga)

| Field | Value |
|-------|--------|
| **Document type** | Integration mapping (Spring-facing) |
| **Version** | **2.0.0** |
| **Date** | 2026-08-12 |
| **Status** | Normative — Call 2 = **recommend**; Call 3 = **chatbot Q&A** |
| **Package** | [`README.md`](./README.md) |

---

## 1. Normative flow

```text
React web portal
  POST /api/recommendations/project-spec
       │  (project specification file and/or text)
       ▼
Spring Boot REST API
       │
       │  1) Call 1 — INGEST
       │     POST /internal/v1/recommendations/submitprojectspecification
       │     headers: Idempotency-Key, X-Correlation-Id
       │     ← lean FR-IX-023 body; persist user_id + ingest_id
       │
       │  2) Call 2 — RECOMMEND / QUOTE  (primary body for React)
       │     POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
       │     body: user_id + ingest_id + optional query
       │     ← quoteRef, items[].equipment, rates, estimatedTotal, …
       │
       │  3) Call 3 — CHATBOT Q&A  (optional follow-ups, not required for submit UX)
       │     POST /internal/v1/recommendations/project-knowledge/query
       │     body: user_id + ingest_id + query
       │     ← answer, sources_used, hits, tool_traces
       ▼
React  ← primary submit response = Call 2 recommend quote
```

---

## 2. Hop table

| Step | Direction | Method / path | Purpose |
|------|-----------|---------------|---------|
| **P0** | React → Spring | `POST /api/recommendations/project-spec` | User submits project-spec |
| **H1 — Call 1** | Spring → haystack | `POST /internal/v1/recommendations/submitprojectspecification` | Index + KG; lean summary |
| **H2 — Call 2** | Spring → haystack | `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` | **Recommend / quote** |
| **H3 — Call 3** | Spring → haystack | `POST /internal/v1/recommendations/project-knowledge/query` | **Chatbot Q&A** (optional) |
| **P1** | Spring → React | Response to **P0** | **Primarily Call 2 quote** |

**Code (Call 2):** prefix `/internal/v1/recommendations` + `"/project-knowledge/getassetrecommendations"`.  
**Code (Call 3):** same prefix + `"/project-knowledge/query"`.

---

## 3. Call 2 response (recommend) — fields for React

| Field | Notes |
|-------|--------|
| `user_id`, `ingest_id`, `query` | Echo |
| `quoteRef` | `QUO-…` (Spring may own commercial quote id) |
| `confidenceScore` | Optional score |
| `days`, `estimatedTotal` | Rental window × rates when known |
| `specSummary` | From Call 1 summary |
| `rationale` | Tool-backed text |
| `items[]` | Ranked equipment; `equipment.id` = catalog asset only |
| `warnings` | Soft issues |

Full contract: `openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md`.

**Safeguard:** never invent asset ids or rates; empty fleet → empty `items` + warning.

---

## 4. Call 3 response (chatbot Q&A)

| Field | Notes |
|-------|--------|
| `answer` | Markdown synthesis |
| `sources_used`, `research_hits`, `graph_hits`, `tool_traces` | Evidence |

Contract: `openspec/specs/knowledge-graph/contracts/project-knowledge-query.md`.

---

## 5. Headers

| Header | Call 1 | Call 2 | Call 3 |
|--------|--------|--------|--------|
| `Idempotency-Key` | Yes (S2a) | No | No |
| `X-Correlation-Id` | Yes | Yes | Yes |

---

## 6. Anti-patterns

| Anti-pattern | Why wrong |
|--------------|-----------|
| Portal submit → Call 3 Q&A only | No equipment quote |
| Portal submit → Call 2 without Call 1 | No session |
| Expect Q&A `answer` on Call 2 | Call 2 is recommend |
| Invent fleet on Call 2 | Forbidden |

---

## 7. Document control

| Version | Date | Notes |
|---------|------|--------|
| **2.0.0** | 2026-08-12 | Call 2 recommend; Call 3 chatbot Q&A |
| **1.0.1** | 2026-08-12 | Prior dual-hop with Call 2 as Q&A (superseded) |
