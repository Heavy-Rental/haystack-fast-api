# Portal Dual-Hop Design (OpenSPDD REASONS Canvas)

| Field | Value |
|-------|--------|
| **Status** | as-built |
| **Behaviour** | [`spec.md`](./spec.md) (FR-PDH-001…011) |
| **ADR** | [`../../adrs/0003-dual-hop-call1-ingest-call2-recommend-call3-qa.md`](../../adrs/0003-dual-hop-call1-ingest-call2-recommend-call3-qa.md) |

## R — Requirements

See [`spec.md`](./spec.md). This canvas records *how* Call 1 → Call 2 (optional Call 3) is implemented across planes.

Call 1 MUST write project-only knowledge. Call 2 MUST load `(user_id, ingest_id)`, MUST NOT invent `equipment.id` or rates, and MUST return the quote envelope Spring maps to React. Call 2 failure MUST NOT re-ingest.

## E — Entities

| Concept | Role |
|---------|------|
| Ingest session | `(user_id, ingest_id)` registry after Call 1 |
| KG-1 | Project Ragas graph + DocumentStore chunks |
| KG-2 | Optional fleet Neo4j (`:Asset` / `:Booking` / `:Category`) |
| Quote envelope | Call 2 `quoteRef` + `items[]` (FR-P-013 collapse) |
| Spring saga | Owns React `project-spec` → Call 1 then Call 2 |

## A — Approach

Spring owns the public portal route. Haystack exposes internal hops only:

```text
React POST /api/recommendations/project-spec
  → Call 1 POST /internal/v1/recommendations/submitprojectspecification
  → Call 2 POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
  → optional Call 3 POST /internal/v1/recommendations/project-knowledge/query
```

- **Call 1:** `IndexingIngestService` (optional S3 gate). Dual-branch index → DocumentStore + mandatory KG-1. Lean FR-IX-023 body.
- **Call 2:** `SessionRecommendService` → `RecommendationService` (MVP). Optional `RECOMMEND_VIA_AGENT_GRAPH`. Quote identity per ADR-0006. Collapse per ADR-0010.
- **Call 3:** LangGraph research → graph → synthesis; tools `project_vector_search` + `project_kg_query` only.

Data planes stay split: project vectors/KG-1 never ingest fleet table dumps; fleet SQL/Neo4j never write project chunks.

## S — Structure

| Path | Role |
|------|------|
| `app/api/recommendations.py` | Thin Call 1 / Call 2 / Call 3 routers |
| `app/services/indexing.py` | Call 1 ingest |
| `app/services/session_recommend.py` | Call 2 session + quote map + FR-P-013 |
| `app/services/recommendations.py` | FR-010 service |
| `app/services/project_knowledge_qa.py` | Call 3 Q&A |
| Child contracts | ingest + get-asset-recommendations + project-knowledge-query |

## O — Operations

```bash
cd haystack-fast-api
uv run pytest tests/test_recommendations_intake.py tests/test_recommend_http_call2.py \
  tests/test_quote_duplicate_collapse.py tests/test_project_knowledge_api.py -q
```

Live smoke: [`../../../QUICKSTART.md`](../../../QUICKSTART.md). Process checklist: [`spec.md`](./spec.md).

## N — Norms

- RFC 2119 in FR-PDH-* and child contracts.
- Field-level HTTP → child contract wins; saga/order/planes → this capability.
- Structured prompts: Call 3 `app/agents/prompts.py`; Call 2 graph `app/agents/recommend_prompts.py`.

## S — Safeguards

- Do not treat Call 2 as chatbot Q&A (superseded 2026-08-12).
- Do not re-ingest on Call 2 failure.
- Do not invent `equipment.id` or rates.
- Do not put `tool_traces` on the Call 2 quote body.
- Do not use hostname `db` for haystack Postgres (ADR-0002).
