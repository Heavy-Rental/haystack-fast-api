# Equipment Recommendation Design (OpenSPDD REASONS Canvas)

## R — Requirements

See [`spec.md`](./spec.md) Purpose, FRs FR-001+, NFRs, acceptance criteria, domain constraints, demo scenarios A/B/C.

**Child capabilities (do not restate full contracts):**

| Child | Owns |
|-------|------|
| [`../indexing/spec.md`](../indexing/spec.md) | Live HTTP index dual-branch |
| [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md) | Mandatory KG-1 + Stage-1 multi-agent |
| [`../recommendation-intake/spec.md`](../recommendation-intake/spec.md) | Deferred recommend envelope |
| [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md) | FR-010.1–8 service graph |
| [`../dynamic-pricing/spec.md`](../dynamic-pricing/spec.md) | Production `predict_price` |

## E — Entities

| Concept | Role |
|---------|------|
| Project input | Free-text and/or file + optional rental window |
| Need / unit-need | Decomposed + expanded ranking unit |
| Asset | Fleet unit from real schema (seed OK Day 1) |
| Booking / BookingItem | Availability overlap truth (read-only) |
| RecommendationItem | Singular ranked choice per unit-need |
| Pricing prediction | From `predict_price()` |
| Knowledge graph | Ragas KG-1 (as-built after indexing) / KG-2 target |
| Tool | Named in-process agent tool (S7.1 fleet catalog as-built; S7.3 graph invokes them) |
| RecommendAgentState | Phase 7 STM partitions + F-2 validation (**S7.0 as-built**) |
| Recommend A–L prompts | Isolated Coordinator / Delegator / Worker contracts (**S7.7 as-built**) |

## A — Approach

### Pipeline design practices (Haystack Chapter 4)

Haystack 2.0 pipelines are **directed multigraphs** (branching, loops). Canonical construction:

1. Select and initialize components  
2. Create `Pipeline()` or `AsyncPipeline()`  
3. `.add_component(name, component)`  
4. `.connect("producer.output_socket", "consumer.input_socket")`  
5. `.run({...})`  
6. `.draw(path=...)` for validation  

**Two pipeline roles:**

| Role | When | Purpose |
|------|------|---------|
| **Indexing (offline)** | Target / as-built live | Catalog / project knowledge (FileTypeRouter → preprocess → embed → DocumentWriter) |
| **Query / recommendation (online)** | MVP + target | Per-need: candidates → availability → price → rank/rationale |

**Hybrid retrieval (target enrichment):** sparse BM25 + dense embedding → DocumentJoiner → optional reranker → generation.

### MVP pipeline (6-day) — pipeline-first

```text
  Intake (free-text box and/or file + optional dates)
           │
           ▼
  Resolve text → LLM NeedDecomposer → expand quantity → unit-needs
           │
           ▼
  app/pipelines/  (per unit-need loop; Haystack Pipeline where ranking is composed)
           │
           ├─► Custom component / repo: Asset SQL filter
           │
           ├─► (parallelizable branches — prefer AsyncPipeline when latency-bound)
           │      ├─► Booking/BookingItem availability
           │      └─► predict_price()  [ml_experiments/ → app/services/pricing/]
           │
           └─► Haystack: PromptBuilder → Generator (Bedrock)
                    select ONE best match + rationale
           │
           ▼
  results_by_need: { need_id, item: RecommendationItem | null }
```

### Target hybrid knowledge path (Chapter 4)

```text
  need / query text
           │
           ├─► dense retriever (embeddings)  ─┐
           │                                  ├─► DocumentJoiner ─► reranker ─► PromptBuilder ─► Generator
           └─► sparse retriever (BM25)       ─┘
  (candidates still constrained by Asset SQL + availability + approved equipment types)
```

### Target hybrid graph (LangGraph + Haystack tools)

```text
  POST recommendation
           │
           ▼
  RecommendationService
           │
           ▼
  LangGraph (stateful orchestration)  ──calls──►  Haystack Tools
           │                                         │
           │                                         ├─ check_availability
           │                                         ├─ recommend_prices (predict_price)
           │                                         ├─ rank_with_rationale
           │                                         └─ trigger_pricing_model_training (async)
           ▼
  Assemble RecommendationItem[]
```

### Tools the agent may call (target)

| Tool name | Purpose | Sync/async |
|-----------|---------|------------|
| `retrieve_equipment_knowledge` | Haystack retrieval over catalog / past projects | Sync |
| `check_availability` | Date-window overlap / adapter | Sync |
| `recommend_prices` | `predict_price()` / rules | Sync |
| `rank_with_rationale` | PromptBuilder + Generator | Sync |
| `trigger_pricing_model_training` | Start training; return `job_id` | Async |

Safeguards:
- Do not retrain on every user recommendation by default.
- `predict_price()` performs no input validation (`ml-experiments/predict_price.py` docstring, 2026-08-11): an unrecognized `category` raises `KeyError`, an unrecognized `condition` raises pandas' `IntCastingNaNError` — neither is a clean, LLM-legible error. Whoever builds `recommend_prices` must validate `category`/`condition` against `feature_schema.CATEGORIES`/`CONDITION_ORDER` *before* calling — either in the tool wrapper itself or via the calling agent's own schema-constrained tool-call args — not assume the underlying function will fail usefully on bad input.

### Knowledge graph pattern (Chapter 5 + as-built)

**As-built:** mandatory user-scoped KG after indexing joiner — see knowledge-graph capability.

**Target offline sketch:**

```text
  catalog PDFs / TXT / web notes
           │
           ▼
  FileTypeRouter → converters → DocumentSplitter
           │
           ▼
  DocumentToLangChainConverter
           │
           ▼
  KnowledgeGraphGenerator (Ragas + optional apply_transforms)
           │
           ├─► KnowledgeGraphSaver → KG_ARTIFACT_DIR/*.json
           └─► (optional) synthetic test generation
```

Storage: in-memory during build → JSON file; no Neo4j by default.

**KG deps (when implementing target):** `ragas>=0.3.7`, `ragas-haystack>=1.0.0`, langchain-core/community, nltk; optional PDF/embed stacks. Env: LLM credentials, embedder, `KG_ARTIFACT_DIR`.

## S — Structure

### Haystack 2.0 building blocks mapped

| Concept (Ch. 3–4) | Use in this feature |
|-------------------|---------------------|
| **Component** (`@component`, `run()` → `dict`, typed sockets) | Rank/rationale; custom SQL, availability, `predict_price` wrappers |
| **`__init__` / `warm_up()` / `run()` life cycle** | Config only in `__init__`; load models/clients in `warm_up()` |
| **Bridge components** | Domain records ↔ Haystack Document / external types |
| **Pipeline** / **AsyncPipeline** | Ranking subgraph; full recommend graph; parallel branches |
| **`.add_component` / `.connect` / `.run` / `.draw`** | Mandatory construction & validation |
| **Routers** | Target/as-built: branch project-spec files by type |
| **SuperComponent** | Package “rank + rationale” or “retrieve + join + rerank” |
| **Tool** | `recommend_prices`, `check_availability`, `rank_with_rationale`, train |
| **Agent** | Optional; prefer **LangGraph** for stateful multi-tool policy |
| **Indexing pipeline** | Live + target catalog/project docs → DocumentStore |
| **Sparse + dense**, **DocumentJoiner**, **reranker** | Target hybrid RAG |
| **Hayhooks** (optional later) | Deploy serialized pipeline as REST/MCP microservice |

### Custom component inventory

| Component (suggested name) | MVP / target | Responsibility | Heavy resources |
|----------------------------|--------------|----------------|-----------------|
| `AssetCandidateFilter` | MVP | SQL filter on Asset schema for a need | DB via `warm_up` or injected factory |
| `BookingAvailabilityFilter` | MVP | Booking/BookingItem overlap | DB |
| `PredictPriceAdapter` | MVP | Call ml_experiments then production pricing | Optional model handle |
| `RankRationaleGenerator` (or stock PromptBuilder+Generator) | MVP | Rank; emit assumption / refinement / schema-gap | LLM via `warm_up` |
| `ProjectSpecPreprocessor` | Target | FileTypeRouter → extract → structured needs | Converters |
| `CatalogHybridRetriever` | Target | BM25 + dense → join → optional rerank | Embedder / reranker |
| `TriggerPricingTrainTool` | Target | Enqueue training; return `job_id` | Queue/DB |
| `DocumentToLangChainConverter` | Target (KG) | Bridge Haystack → LangChain Document | None |
| `KnowledgeGraphGenerator` | Target (KG) / as-built KG-1 | Ragas KG build | LLM + embedder |
| `KnowledgeGraphSaver` | Target (KG) / as-built | Persist graph JSON | Filesystem |

### As-built recommend file map (service)

See [`../recommendation-pipeline/design.md`](../recommendation-pipeline/design.md) full inventory. Key: `app/pipelines/*`, `app/services/recommendations.py`, `app/services/pricing_client.py`.

### As-built multi-agent building blocks (Phase 7 S7.0–S7.7)

| Module | Role |
|--------|------|
| `app/agents/recommend_state.py` | **S7.0** `RecommendAgentState` + F-2 `validate_state_transition` / partition writes; optional `graph_notes` |
| `app/agents/fleet_tools.py` | **S7.1** fleet tools; **S4** `LiveSqlFleetBackend` |
| `app/repositories/fleet_repository.py` | **S4** allowlisted ORM reads; `asset_id` = `assets.name` |
| `app/agents/neo4j_tools.py` | **S7.2 + S8.3** templates + `FakeNeo4jBackend` / `BoltNeo4jBackend` / populate HTTP |
| `app/agents/tool_factory.py` | **S7.1** DI catalog (`fake` seed default \| `sql` DTO backend); **S7.2** Neo4j tools; **S7.7** `ALLOWED_WORKER_KINDS` + `build_recommend_runtime` |
| `app/agents/tools.py` | S3 `run_indexing_from_request`; S6 `predict_asset_price` |
| `app/agents/recommend_graph.py` | **S7.3** `build_recommend_graph` / `run_recommend_graph` (isolated from Q&A) |
| `app/agents/recommend_nodes.py` | **S7.3** gate, project worker, delegator, fleet/price workers, `execute_needs`; **S7.2** K-3 Neo4j skip; **S7.7** `validate_work_plan`; **S7.8** Worker [5] KG-1 tools |
| `app/agents/recommend_synthesis.py` | **S7.4** tool-free stub Coordinator [8]; **S7.7** prompt-backed rationale |
| `app/agents/recommend_prompts.py` | **S7.7** A–L contracts (Coordinator / Delegator / Workers [5][6][7]) |
| `app/services/session_recommend.py` | **S7.5** Call 2 flag `RECOMMEND_VIA_AGENT_GRAPH` → graph → same quote DTO |
| `app/agents/recommend_traces.py` | **S7.6** G-1 `append_tool_trace` / `duration_ms` |
| Tests | `tests/test_recommend_agent_state.py`, `test_fleet_tools.py`, `test_tool_factory.py`, `test_neo4j_tools.py`, `test_neo4j_tools_integration.py` (optional), `test_recommend_graph_order.py`, `test_recommend_fanout.py`, `test_recommend_synthesis.py`, `test_recommend_http_call2.py`, `test_tool_traces.py`, `test_recommend_prompts.py`, `test_agent_tool_di.py`, `test_recommend_project_worker.py` |

Live Neo4j **job + T4 triggers** are as-built in the config pack (`neo4j-populate`, post-sync HTTP, admin `:8089`). App **S8.3** wires `NEO4J_BACKEND=bolt` (`BoltNeo4jBackend`) and `trigger_neo4j_populate` → `NEO4J_POPULATE_URL`. Default CI stays fake.

## O — Operations

### Implementation tasks (ordered) — 6-day plan

#### Day 1 — Prototype (`feature/agent-1-prototype`)

- Build under `app/pipelines/` only; standalone script or one-off test.
- Import `predict_price()` from `ml_experiments/` (no local stub).
- Implement ranking with Haystack PromptBuilder/Generator (stub-LLM if Bedrock blocks).
- Prefer early custom `@component` for Asset filter, availability, predict_price adapter.
- Validate each custom component **standalone** before `Pipeline.connect`.
- **Half-day path**: hardcoded single need, SQL filter, stubbed availability, real `predict_price()`, Haystack ranking, Scenario A.
- **Full-day path**: + Scenarios B/C, real Booking query, real Bedrock, rehearse two clean demos.
- **Exit**: Scenario A end-to-end with honest rationale. Do not start Day 2 until this holds.
- Once ranking is a Pipeline, call `.draw()` to validate edges.

#### Day 2 — Spec checkpoint + scaffolding (`feature/agent-2-spec-and-scaffold`)

- Lock this SPEC against proven pipeline.
- Resolve refine/reject and persistence scope questions.
- Scaffold free-text/file intake; confirm `POST .../submitprojectspecification`; wire decomposer + quantity expansion + singular `item`.

#### Day 3 — Real candidates + availability (`feature/agent-3-candidates-availability`)

- Port SQL filter to real Asset schema.
- Real availability overlap; seed data so Scenario C fires.
- Wire per-need loop to real endpoint; verify independent rankings.

#### Day 4 — Ranking + pricing sync (`feature/agent-4-ranking-pricing-sync`)

- Production Haystack Bedrock ranking + rationale/assumption/schema-gap text.
- `warm_up()` generators if process is long-lived.
- Sync with pricing team (`feature/ml-3-pricing-service`): start production swap if ready; else keep ml_experiments and log.

#### Day 5 — E2E + price swap (`feature/agent-5-e2e-integration`)

- Complete import swap if ready; else flag fast-follow.
- Full A/B/C through real intake → availability → pricing → ranking.
- Unit tests: standalone components, empty candidates, socket contracts.

#### Day 6 — Persistence decision, polish, demo (`feature/agent-6-demo-prep`)

- Implement minimal cart write **or** document deferred.
- README, polish, rehearse A+B live; C for Q&A.

#### Target follow-ons

- FileTypeRouter + preprocessing (as-built indexing path already ships dual-branch).
- Offline catalog indexing; hybrid retrieval; SuperComponents; AsyncPipeline; LangGraph tools; training job API; Docker multi-stage; optional Hayhooks/MCP; auth on LLM routes.

### Jira subtasks / branches

| # | Status | Branch | Covers | Day |
|---|--------|--------|--------|-----|
| 1 | ☐ | `feature/agent-1-prototype` | Pipeline proof, Scenario A | 1 |
| 2 | ☐ | `feature/agent-2-spec-and-scaffold` | SPEC lock, free-text/file intake | 2 |
| 3 | ☐ | `feature/agent-3-candidates-availability` | Real Asset SQL, booking overlap | 3 |
| 4 | ☐ | `feature/agent-4-ranking-pricing-sync` | Bedrock ranking, pricing Day 4 sync | 4 |
| 5 | ☐ | `feature/agent-5-e2e-integration` | Price swap, A/B/C, unit tests | 5 |
| 6 | ☐ | `feature/agent-6-demo-prep` | Cart or defer, polish, rehearsal | 6 |

### Troubleshooting checklist (Chapter 3 adapted)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Ingest/parse failures | Bad paths, converter errors | Check converter logs; validate paths/sizes |
| Wrong branch for file type | Missing FileTypeRouter mapping | Verify MIME/router outputs |
| `PipelineConnectError` | Incompatible sockets | Map I/O; use `.draw()` |
| Empty or weak retrieval | Dense-only miss | Add BM25 + DocumentJoiner; consider reranker |
| Slow first request | Model loaded in `run()` / heavy `__init__` | Move load to `warm_up()` |
| Mutated data mid-branch | In-place mutation | Immutable transforms |
| Crash on Scenario C | Empty list not handled | Return empty structured output |
| Serial latency | Independent work in series | Parallel branches / AsyncPipeline |
| Odd agent tool use (target) | Ambiguous tool description | Refine name/description |
| Credential leakage | Hardcoded keys | Env / secrets only |

### PR / review convention

- Subtask 1 (prototype): lighter review, merge fast.
- Subtasks 2–5: full review.
- Subtask 4: hard external dependency on pricing Day 4—log experimental vs production.

### Deployment (Haystack Chapter 7)

**Primary:** FastAPI + Uvicorn (Method 1). **Optional:** Hayhooks + serialized YAML (Method 2) for pure pipelines / MCP — not second authority for availability/pricing.

#### Production needs

| Need | Meaning |
|------|---------|
| Scalability | Concurrent recommend; containerize |
| Accessibility | Stable REST + OpenAPI for portal/Spring |
| Resource management | LLM I/O-bound — async FastAPI; `warm_up` at process start |
| Security | No anonymous abuse of LLM routes; secrets via env; Pydantic bodies |
| Operability | Health, structured logs, CI |

#### Deployment requirements (FR-D01–D15)

- **FR-D01**: Endpoints via existing FastAPI app factory; thin routers.
- **FR-D02**: Pydantic models (snake_case JSON).
- **FR-D03**: Lifespan SHOULD call `warm_up()` on heavy components once per process.
- **FR-D04**: Pipeline/service instances via DI or app.state, not rebuilt every request.
- **FR-D05**: Config from environment/settings only.
- **FR-D06**: When auth lands, protect LLM-backed routes; keep health public.
- **FR-D07**: Production SHOULD use multi-stage container image.
- **FR-D08**: Run ASGI binding `app.main:app`; secrets at runtime.
- **FR-D09**: Health usable by orchestrators (`GET /health`).
- **FR-D10**: CI tests + build on pipeline/API changes.
- **FR-D11–D13**: If Hayhooks adopted — version artifacts; no second fleet/price truth; proxy auth/rate limits/timeouts.
- **FR-D14–D15**: Optional MCP maps to same tool contracts + security.

#### Explicitly out of scope for Day 1–6 demo

- Full Kubernetes manifests  
- Mandatory Hayhooks for primary recommend API  
- Replacing Spring/React with Hayhooks  

#### Deployment checklist (post-MVP)

1. Lifespan `warm_up` for generators/embedders (and KG workers if any).  
2. Pydantic validation on all public recommend bodies.  
3. Multi-stage Docker image + env-based config.  
4. Auth strategy for LLM routes when constitution adds auth.  
5. CI: pytest + image build (+ optional smoke `/health` + fixture).  
6. Optional: serialize rank subgraph + Hayhooks/MCP only if a consumer needs pure-pipeline tool.

## N — Norms

- Pipeline-first: deterministic components before agent loops.
- Singular `item` per unit-need; quantity only on internal needs.
- Hard catalog filter to four types.
- Pricing only via `predict_price`; deposit 30% / SGD defaults.
- Live HTTP conflict: indexing/KG win over deferred recommend envelope.
- Fix prompt/spec first (OpenSPDD); architecture lives in this design.

## S — Safeguards

- Do not invent fleet units without Asset SQL (or seed).
- Do not invent prices outside `predict_price` path.
- Do not return top-N alternatives as public `items[]`.
- Do not put SQL/graph construction in routers.
- Do not retrain on every recommendation by default.
- Do not make Hayhooks a second source of truth for availability/pricing.
- Do not commit secrets or bake them into images.
- Do not treat live ingest response as recommend envelope without reattach decision.
