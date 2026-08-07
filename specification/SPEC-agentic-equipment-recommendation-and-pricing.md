# Specification: Agentic Equipment Recommendation & Pricing Recommender

| Field | Value |
|-------|--------|
| **Document type** | Feature SDD |
| **Status** | Draft — target state (6-day plan + Haystack Ch. 3–5, 7 deployment patterns; KG target) |
| **Feature id** | `agentic-equipment-recommendation-pricing` |
| **Workspace** | `/workspaces/haystack-fast-api` |
| **Application module** | `haystack-fast-api` |
| **Python package** | `app` |
| **Spec location** | `specification/SPEC-agentic-equipment-recommendation-and-pricing.md` (also tracked locally as this file) |
| **Related** | [`SPEC-project.md`](./SPEC-project.md), [`SPEC-project-setup.md`](./SPEC-project-setup.md); **child stages:** [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) (intake API + Postman); [`SPEC-recommendation-intake-and-pipeline-front.md`](./SPEC-recommendation-intake-and-pipeline-front.md) (stage notes + LLM guide); [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) (**as-built FR-010.1–8 pipeline**); [`SPEC-recommendation-pipeline-testing-guide.md`](./SPEC-recommendation-pipeline-testing-guide.md) (how to test); companion docs: `recommendation-agent-masterplan.md` (decisions/rationale), `recommendation-agent-decided-approach.md` (prototype hour-by-hour), `recommendation-agent-execution-plan.md` (schedule only), `dynamic-pricing-execution-plan.md` / `SPEC-dynamic-pricing.md` (pricing team) |
| **Haystack reference** | *Building Natural Language and LLM Pipelines* — Ch. 3–5, **7** (local EPUBs). Ch. 7: FastAPI vs Hayhooks deployment, Docker, CI/CD, MCP |
| **Depends on** | `haystack-ai` (Haystack 2.0), LangGraph (declared deps), real `Asset` / `Booking` / `BookingItem` schema, pricing team’s `predict_price()`; **(target KG)** `ragas`, `ragas-haystack`, LangChain document types, LLM + embedder providers |
| **Audience** | Engineers and agents implementing agentic recommendation, pricing integration, and (post-MVP) ML training tool invocation |

**Read [`SPEC-project.md`](./SPEC-project.md) and [`SPEC-project-setup.md`](./SPEC-project-setup.md) first.** This feature SDD assumes the as-built environment, layering, and stack described there.

**Document roles (do not duplicate):**

| Document | Owns |
|----------|------|
| **This SPEC** | Normative behaviour, API contract, acceptance criteria, architecture constraints |
| `recommendation-agent-masterplan.md` | Decisions and rationale |
| `recommendation-agent-decided-approach.md` §3 | Hour-by-hour prototype task detail |
| `recommendation-agent-execution-plan.md` | Day-by-day schedule, Jira subtasks/branches only |
| Chapter 3 (Haystack by deepset) | Framework vocabulary: components, pipelines, SuperComponents, tools, agents |
| Chapter 4 (Haystack pipelines) | Pipeline construction steps, directed multigraphs, branching/routers, indexing vs RAG query paths, hybrid retrieval + rerank, SuperComponent packaging, AsyncPipeline |
| Chapter 5 (Custom components) | `@component` contract, `__init__` vs `warm_up()` vs `run()`, `@component.output_types`, immutable processing, bridge components, standalone + pipeline testing; **Ragas KnowledgeGraph** + transforms for multi-hop structure |
| Chapter 7 (Deploying Haystack apps) | FastAPI serving vs Hayhooks serialization; Docker; endpoint security; CI/CD; MCP tool exposure |

---

## 1. Purpose

This specification defines the **agentic AI decision and recommendation system** inside `haystack-fast-api` that:

1. Accepts **unstructured project input** — a **single free-text box** and/or an **uploaded file** of unstructured text — plus optional **rental start/end dates**. The portal does **not** use a repeatable structured “add another need” form for MVP.
2. **LLM-decomposes** that text into internal equipment needs (description, optional hints, optional **quantity**), then **expands quantity** into unit-needs (`RecommendationItem` has **no** `quantity` field).
3. Runs a **Haystack 2.0 pipeline-first** recommendation path (custom components + ranking generation) to select suitable equipment against the real fleet schema.
4. Filters candidates by **availability** using `Booking` / `BookingItem` overlap for the requested window.
5. Attaches **pricing** by calling the pricing team’s `predict_price()` (experimental `ml_experiments/` during prototype; production `app/services/pricing/` when ready).
6. Returns **exactly one ranked `RecommendationItem` per unit-need** (or null if no match) with honest rationales (assumptions, refinement suggestions, schema-gap callouts)—**not** a top-N list of alternatives per need.
7. **(Target / post–6-day MVP)** Exposes the same deterministic work as **tools** (and optionally a LangGraph orchestrator) and allows an agent tool or operator endpoint to **trigger the machine-learning training pipeline** asynchronously.

### 1.1 Architectural stance (from Haystack Chapter 3)

Chapter 3 frames a **hybrid architecture**: a **stateful orchestration layer (LangGraph)** directing a set of **reliable, auditable tool layers (Haystack)**. Haystack’s primary strength is as a **pipeline-first engine**—robust, measurable, deployable dataflow pipelines that later become the foundation for agents.

This feature follows that separation of concerns:

| Layer | Role in this feature |
|-------|----------------------|
| **Haystack pipelines / components** | Deterministic tool layer: SQL candidate filter, availability, pricing wrapper, ranking (`PromptBuilder` + `Generator`) |
| **Plain-Python / service loop (MVP)** | Per-need orchestration before full agent adoption |
| **LangGraph (target)** | Stateful orchestration when multi-step tool selection, memory, or retrain policy is required |
| **Haystack Agent (optional)** | Sufficient only for simpler tool loops; prefer LangGraph when context/state control matters (Chapter 3: Haystack agent loop can be opaque for advanced memory curation) |

Hierarchy used by Haystack 2.0 (Chapter 3):

```text
Component → Pipeline → SuperComponent → Tool → Agent
```

MVP builds **Components** and a **Pipeline** under `app/pipelines/`. Target may wrap ranking/pricing subgraphs as **SuperComponents**, register them as **Tools** (name + natural-language description), and optionally drive them from an **Agent** or **LangGraph**.

### 1.2 Pipeline design practices (from Haystack Chapter 4)

Chapter 4 moves from building blocks to **concrete pipeline composition**. Haystack 2.0 pipelines are **directed multigraphs**: they support simultaneous flows, **branching**, and loops—not only linear chains.

**Canonical construction steps** (apply to ranking subgraph and any future indexing/RAG subgraph):

1. **Select and initialize components** — e.g. SQL/availability adapters, `predict_price` wrapper, `PromptBuilder`, `Generator`; for catalog knowledge (target): converters, splitters, embedders, retrievers, joiners, rerankers.
2. **Create** `Pipeline()` (or `AsyncPipeline()` when parallel branches should overlap in wall-clock time).
3. **`.add_component(name, component)`** — register units without yet defining edges.
4. **`.connect("producer.output_socket", "consumer.input_socket")`** — explicit typed edges; order of connections must respect data structures (Chapter 4: only connected components exchange data).
5. **`.run({...})`** — supply mandatory inputs keyed by component name.
6. **`.draw(path=...)`** — Mermaid/visual validation of the graph (also used to debug `PipelineConnectError`).

**Branching & routers:** Use routers (e.g. `FileTypeRouter`, conditional/metadata routers) when inputs differ by type or policy. Chapter 4 indexing example routes `text/plain`, `application/pdf`, HTML, and CSV down specialized branches, then normalizes into one document store. This feature’s **target project-spec ingest** SHOULD use the same pattern (PDF vs TXT vs DOCX → converters → shared need-extraction path).

**Two pipeline roles:**

| Role | When | Purpose in this feature |
|------|------|-------------------------|
| **Indexing (offline)** | Target / ops | Prepare equipment catalog / historical project knowledge (FileTypeRouter → preprocess → embed → `DocumentWriter`) |
| **Query / recommendation (online)** | MVP + target | Per-need: candidates → availability → price → rank/rationale (`PromptBuilder` + `Generator`) |

**Hybrid retrieval (target enrichment):** When catalog text is indexed, prefer **hybrid RAG**: parallel **sparse (BM25)** + **dense (embedding)** retrievers → **`DocumentJoiner`** fusion → optional **reranker** (cross-encoder) → then generation. Sparse wins on exact model/jargon tokens; dense wins on intent/synonyms; rerank improves precision before the LLM rationale step.

**SuperComponents (Chapter 4):** Two packaging methods—(1) wrap an existing `Pipeline` instance, or (2) define a class with `@super_component` for stronger reuse. Use for `rank_with_rationale` and any retrieve+join+rerank subgraph before Tool registration.

**Parallelization:** Independent steps (e.g. availability check and `predict_price` over the same candidate set, or dual retrievers) SHOULD be modeled so they can run concurrently via branching and, when beneficial, **`AsyncPipeline`**, so slower LLM generation is not needlessly serialized behind embarrassingly parallel work.

---

## 2. Outcomes

When this specification is implemented and followed:

- A customer (or portal) can submit **free-text and/or a project file** (+ optional dates) and receive recommendations for each **unit-need** after LLM decomposition and quantity expansion.
- Recommendations use real **Asset** SQL filtering and real **availability** overlap queries when wired (Day 3+).
- Each unit-need has **exactly one** ranked **`item`** (or null if no match), with an honest **rationale** when selected (assumption stated, refinement suggestion where inference occurred; schema-gap acknowledgment for terrain/operator-required where relevant).
- Pricing is obtained via **`predict_price()`**—never a local stub once the pricing team’s temporary experimental function exists; production swap is a one-line import when `app/services/pricing/` lands.
- Public behaviour is expressed through this SPEC’s API contract and the child intake SPEC; routers stay thin; pipeline logic lives under `app/pipelines/` (prototype may start **off any registered route**).
- Haystack pieces follow 2.0 contracts: **`@component`**, typed **input/output sockets**, explicit pipeline connections (not implicit dict-passing from 1.x).
- **(Target)** Tools and/or a LangGraph graph can call `trigger_pricing_model_training`; training is asynchronous.

---

## 3. Scope

### 3.1 In scope (6-day MVP + target)

| Area | MVP (Days 1–6) | Target (post-MVP / full agentic) |
|------|----------------|----------------------------------|
| **Intake** | Single free-text box and/or file (unstructured); LLM decomposes → internal needs; quantity expansion to unit-needs; optional dates | Richer file types (PDF/DOCX converters), stronger decompose prompts, optional human edit of decomposed needs |
| **Haystack building blocks** | Custom `@component` classes + Pipeline for rank/rationale; service-level loop for SQL/availability/price | SuperComponents for reusable subgraphs; Tools with name/description; optional Agent or LangGraph |
| **Candidate selection** | SQL filter against real `Asset` schema (custom component or repository called from pipeline) | Same + optional retrieval components / document store over catalog knowledge |
| **Availability** | `Booking` / `BookingItem` overlap for date window; Scenario C (no match) must fire on real data | Same; optional adapter to Spring if availability truth moves |
| **Ranking** | Haystack `PromptBuilder` / `Generator` (Bedrock); stub-LLM only if Bedrock auth blocks prototype | Same; richer agent decide node |
| **Pricing** | Call `ml_experiments.predict_price()` then swap to `app.services.pricing.predict_price` | Same wrapped as a Tool `recommend_prices` |
| **Explainability** | Rationale text: assumptions, refinement suggestions, schema-gap (terrain/operator-required) | Optional SHAP on pricing when model supports it |
| **ML training tool** | **Out of 6-day scope** (owned by pricing workstream / later) | Tool `trigger_pricing_model_training` + `POST /api/v1/ml/train` + job status |
| **Knowledge graph** | **Out of 6-day critical path** | Offline/batch `KnowledgeGraphGenerator` (Ragas) over catalog + historical project text; multi-hop structure for ranking/eval; optional JSON persist |
| **Deployment** | Dev: Uvicorn + existing FastAPI app factory | Production patterns (Ch. 7): containerize FastAPI app; optional Hayhooks for serialized pipelines; secure endpoints; CI/CD; optional MCP for agent tools |
| **Persistence** | Resolve on Day 2/6: minimal “add to cart” **or** explicitly deferred | Recommendation request/response metadata in Postgres if retained |
| **Demo scenarios** | A (happy path), B, C (no match)—rehearse A+B live; C for Q&A | Same |

### 3.2 Out of scope

- Real payment gateway or booking lifecycle ownership (Spring REST API / portal).
- Live inventory mutation or locking of units (availability is **read-only**).
- Multi-tenant auth / JWT until a shared auth SDD exists.
- Changing the four approved equipment types (product UI constraint: Boom Lift, Scissors Lift, Fork Lift, Excavator)—hard filter in ranking/response.
- **Refine/reject flow** — in scope only if explicitly resolved yes on Day 2; otherwise deferred.
- **“Add to cart” persistence** — in scope only if resolved yes by Day 6; otherwise documented deferred/post-MVP.
- Training on arbitrary external datasets without a defined schema.
- Mobile operator app flows.
- Mandatory use of Hayhooks/MCP in the 6-day window (allowed later as a deployment option for pipeline-as-microservice).

---

## 4. Actors & user stories

| Actor | Goal |
|-------|------|
| **Customer / portal / intake UI** | Submit free-text or file (+ optional dates) → one recommended available asset per unit-need + prices. |
| **Recommendation pipeline / agent** | Decompose → expand quantity → filter → availability → price → rank (one item per unit-need); emit honest rationales. |
| **Pricing team** | Provide `predict_price()` (experimental then production); own training pipeline for the model behind it. |
| **Ops / data scientist** | (Target) Trigger or schedule ML training; poll job status. |
| **Spring REST API** (future) | May call this service or share DB read models for assets/bookings. |

### Primary user stories

1. **As a customer**, I paste a project description (or upload a file) and rental dates so that I receive **exactly one** suitable, **available** recommendation per unit-need with prices and clear reasons—without filling a multi-row needs form.
2. **As the recommendation pipeline**, I call **`predict_price()`** for each candidate path and never block the demo on a missing production pricing module if the experimental function is still in place.
3. **As an implementer**, I prove Scenario A end-to-end on Day 1 before writing the locked API contract on Day 2.
4. **(Target) As the recommendation agent**, I may call a **train_pricing_model tool** that starts training without blocking the current recommendation (default: not on every request).

---

## 5. Functional requirements

### 5.1 Intake

Normative detail also lives in [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md).

- **FR-001**: The service MUST accept recommendation requests as **unstructured** input: JSON `project_text` and/or `multipart/form-data` (`file`, optional `project_text`) plus optional `start_date` / `end_date` (ISO 8601 date). MVP UI is a **single free-text box or file upload**—**not** a repeatable structured “add another need” form.
- **FR-002**: Supported file types (MVP minimum): `text/plain`, `text/markdown`. PDF and DOCX SHOULD be supported via converters when enabled. Unsupported types → `400` shared error shape.
- **FR-003**: File ingest SHOULD prefer Haystack-style preprocessing (converters / cleaners / splitters as components) or equivalent streaming extraction; full raw bytes MUST NOT be required beyond parser needs. Source text MUST then be passed to an **LLM need decomposer** that emits internal needs (`need_id`, `description`, optional `equipment_hints`, optional `quantity` ≥ 1).
- **FR-004**: Empty `project_text` / empty file extract / empty decompose result → `400`.
- **FR-005**: After decomposition and quantity expansion, each **unit-need** MUST be processed **independently**—not a single merged/confused ranking across unit-needs (Day 3 exit condition).
- **FR-006**: If a decomposed need has **`quantity = N`** (*N* ≥ 1), the system MUST expand it into **N unit-needs** before ranking. **`RecommendationItem` MUST NOT include a `quantity` field.** Unit-need ids: `base_id` when *N* = 1; `{base_id}__u{i}` for *i* = 1..*N* when *N* &gt; 1.
- **FR-007**: For each unit-need, the response MUST expose **exactly one** ranked recommendation via singular **`item`** (`RecommendationItem | null`). When a match is selected, `item` is that single choice (typically `rank: 1`). When no match (Scenario C) or ranking not yet wired, `item` is `null` with warnings. MUST NOT return a multi-element list of ranked alternatives per need.

### 5.2 Pipeline structure (normative for MVP)

- **FR-010**: Recommendation orchestration for the 6-day build MUST follow this shape under `app/pipelines/` / services:
  1. **Resolve source text** — free-text and/or file extract (Day 1 may hardcode text for prototype).
  2. **LLM decompose** — unstructured text → internal needs (quantity allowed only on internal need).
  3. **Expand quantity** — internal needs → unit-needs (**FR-006**).
  4. **SQL candidate filter** — against real `Asset` schema (seeded subset only acceptable on Day 1).
  5. **Availability filter** — `Booking` / `BookingItem` overlap for the date window; stub only until real query is wired.
  6. **Price** — call `predict_price()` (see §5.3).
  7. **Rank / rationale** — Haystack `PromptBuilder` / `Generator` (Bedrock); select **one** best match per unit-need; include assumption callouts, refinement suggestions, and schema-gap acknowledgments (terrain / operator-required) where applicable.
  8. **Assemble** — one `item` (`RecommendationItem | null`) per unit-need.
- **FR-011**: Responses MUST only include equipment consistent with the approved product catalog (**Boom Lift, Scissors Lift, Fork Lift, Excavator**) unless product policy explicitly expands later.
- **FR-012**: Each `RecommendationItem` MUST include at least: identity/type fields needed by the UI, rank or score, **rationale** (honest: assumptions stated, refinement suggestion when specs were inferred), pricing fields derived from `predict_price()` when pricing is included, and availability outcome. MUST NOT include `quantity`. When pricing is present, expose **`daily_rate`** (scoped to the request duration window) and **`total_price`** (`daily_rate × duration_days` for that window)—MUST NOT fabricate a **`weekly_rate`** as `daily × 7` (see child pipeline **FR-P-011**).
- **FR-013**: When dates are provided, availability filtering MUST run before final ranking presentation for that unit-need.
- **FR-014**: Prototype code MUST live under `app/pipelines/` and MUST NOT be registered on a public route/entrypoint until the Day 2+ scaffold wires the real endpoint (call via standalone script or one-off test on Day 1).
- **FR-015**: Routers MUST stay thin; pipeline construction and SQL live in services/pipelines/repositories—not in route handlers. Async recommend handlers MUST offload the sync service call (e.g. `run_in_threadpool`) so LLM/pipeline I/O does not block the ASGI event loop (child pipeline **FR-P-012**, **NFR-008**).

### 5.2.1 Haystack 2.0 component rules (from Chapters 3–5)

- **FR-016**: Any Haystack-native unit of work MUST be a **component**: a Python class with the **`@component`** decorator and a **`run()`** method as the entry point (Chapter 5: decorator registers the class with the pipeline engine).
- **FR-017**: Components MUST declare **typed input and output sockets** (Haystack 2.0 explicit contracts). Inputs = typed arguments on `run()`; outputs = **`@component.output_types(...)`** keys that match the **dict** returned by `run()`. Do not rely on Haystack 1.x-style implicit dictionary passing.
- **FR-017a**: `run()` MUST **always return a `dict`** whose keys are output socket names (Chapter 5 hard rule).
- **FR-017b**: **`__init__` MUST stay lightweight** — store configuration only (model name, thresholds, connection strings, feature flags). Do **not** load multi-GB models, open heavy DB pools, or download artifacts in `__init__`.
- **FR-017c**: Heavy one-time setup (model load, persistent clients) MUST use **`warm_up()`**, called once by the pipeline engine before the first `run()`. `run()` assumes resources are already available (Chapter 5 life-cycle split: config → warm_up → process).
- **FR-017d**: Custom transforms SHOULD prefer **immutable processing** (produce new objects rather than mutating inputs in place) and **preserve metadata** when transforming Haystack `Document`s or domain records, to avoid side effects across branches.
- **FR-017e**: Where external library types differ from Haystack types, introduce thin **bridge components** whose only job is format conversion (Chapter 5 pattern), keeping domain components focused.
- **FR-018**: Domain logic that is not already a stock Haystack component (**Asset SQL filter**, **booking overlap**, **`predict_price` adapter**) SHOULD be implemented as **custom components** under `app/pipelines/` (or thin wrappers) so they share the same graph, sockets, and tests as `PromptBuilder` / `Generator`.
- **FR-018a**: Custom components MUST be **runnable standalone** (instantiate → optional `warm_up()` → `run()`) before being wired into a Pipeline, so unit tests do not require a full graph.
- **FR-018b**: Custom components MUST handle **empty candidate / empty document lists** gracefully (predictable empty outputs, no unhandled exceptions), so multi-need and Scenario C paths fail cleanly.
- **FR-019**: Ranking generation MUST use Haystack **LLM generation** components appropriate to the provider (e.g. Bedrock-backed generator) plus **`PromptBuilder`** (or equivalent) so prompts and assumptions stay inspectable.
- **FR-019a**: (Target) Recurring subgraphs (e.g. rank+rationale, or preprocess+embed+retrieve) SHOULD be packaged as **SuperComponents**—either by wrapping a `Pipeline` instance or by defining a `@super_component` class (Chapter 4)—exposing only the external sockets needed upstream/downstream.
- **FR-019b**: (Target) When exposing work to an agent, wrap component/pipeline/SuperComponent as a **Tool** with a short unique **name** and a clear natural-language **description** of capabilities, inputs, and outputs. Poor tool descriptions cause unexpected agent behaviour (Chapter 3 troubleshooting).
- **FR-019c**: Haystack `Pipeline` graphs used by this feature MUST be assembled with explicit `.add_component` / `.connect` and executed via `.run` (Chapter 4 construction steps). Implicit ad-hoc chaining that bypasses socket contracts is non-compliant.
- **FR-019d**: (Target) Project-spec **file ingest** SHOULD branch by media type (e.g. `FileTypeRouter` or equivalent) so PDF/TXT/DOCX each hit an appropriate converter before a shared extraction path.
- **FR-019e**: (Target) Catalog/knowledge retrieval, when enabled, SHOULD support **hybrid** retrieval (sparse BM25 + dense embedding → `DocumentJoiner` → optional reranker) rather than dense-only naive RAG alone, unless evaluation shows naive is sufficient.
- **FR-019f**: Independent pipeline branches (dual retrievers; or availability + pricing over candidates) SHOULD be structured for concurrent execution; prefer `AsyncPipeline` when wall-clock latency matters and branches do not share a serial data dependency.

### 5.2.2 Custom component inventory (this feature)

| Component (suggested name) | MVP / target | Responsibility | Heavy resources |
|----------------------------|--------------|----------------|-----------------|
| `AssetCandidateFilter` | MVP | SQL filter on real `Asset` schema for a need | DB engine via `warm_up` or injected session factory |
| `BookingAvailabilityFilter` | MVP | `Booking` / `BookingItem` overlap for date window | DB |
| `PredictPriceAdapter` | MVP | Call `ml_experiments.predict_price` → later `app.services.pricing.predict_price` | Optional model handle if in-process |
| `RankRationaleGenerator` (or stock `PromptBuilder`+`Generator`) | MVP | Rank candidates; emit assumption / refinement / schema-gap rationale | LLM client via `warm_up` |
| `ProjectSpecPreprocessor` | Target | FileTypeRouter branch → text extract → structured needs | Converters |
| `CatalogHybridRetriever` | Target | BM25 + dense → join → optional rerank | Embedder / reranker in `warm_up` |
| `TriggerPricingTrainTool` | Target | Enqueue training job; return `job_id` | Queue/DB client |
| `DocumentToLangChainConverter` | Target (KG) | Bridge Haystack `Document` → LangChain `Document` (`page_content` / `metadata`) for Ragas | None |
| `KnowledgeGraphGenerator` | Target (KG) | Build Ragas `KnowledgeGraph` from docs; optional `apply_transforms` (LLM entity/relation extraction + embeddings) | LLM + embedder via `warm_up` / injected generators |
| `KnowledgeGraphSaver` | Target (KG) | Persist graph to JSON (or export) for reuse without re-transform | Filesystem / object store |

Each custom component MUST ship with: unit tests (standalone `run`), empty-input behaviour, and configuration tests for `__init__` parameters (Chapter 5 testing principles).

### 5.3 Pricing integration

- **FR-020**: The recommendation path MUST obtain prices by calling **`predict_price()`**—not a hand-written local stub once `ml_experiments/predict_price` exists.
- **FR-021**: **Prototype / early full build**: import from `ml_experiments/` (pricing team’s temporary experimental-model-backed function).
- **FR-022**: **Production swap (Day 4 sync / Day 5)**: when pricing team’s `app/services/pricing/predict_price()` is ready (`feature/ml-3-pricing-service`), switch import in one place. Matching input/output shape is assumed (masterplan). If production is not ready, keep `ml_experiments/` and log explicitly that the demo runs on the **experimental** model—do not block end-to-end testing.
- **FR-023**: Pricing payload on each item SHOULD expose rates/currency/explanation (and model identity when available) consistent with the pricing service contract.
- **FR-024**: Deposit guidance for portal alignment remains **30%** default unless policy config overrides (product UI rule).

### 5.4 ML training pipeline tool (target — not 6-day MVP)

- **FR-030**: A tool e.g. `trigger_pricing_model_training` MAY be registered for a future agent graph. Invocation MUST enqueue/start training and return `job_id` immediately.
- **FR-031**: Training pipeline (owned primarily by pricing / shared module): load dataset → feature engineering compatible with inference → fit (default **XGBoost**) → persist artifact + metadata → atomic current-model pointer update.
- **FR-032**: Training MUST be asynchronous relative to the triggering HTTP request.
- **FR-033**: `GET /api/v1/ml/jobs/{job_id}` → `queued` \| `running` \| `succeeded` \| `failed`.
- **FR-034**: `POST /api/v1/ml/train` for operator trigger without the agent.
- **FR-035**: Agent MUST NOT retrain on every recommendation by default (`options.allow_retrain` default `false`, or operator-only).

### 5.5 API & errors

- **FR-040**: Public project-spec endpoint is `POST /api/v1/recommendations/from-project-spec` (JSON and/or multipart).
  - **Target / product intent:** recommend envelope (`recommendation_id`, `results_by_need`, singular `item`) per this SPEC and child intake tables.
  - **As-built override (2026-08-07):** the route currently runs the **indexing** pipeline and returns `IngestFromProjectSpecResponse`. Normative live contract: [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md). Recommend response remains **target / reattach**; FR-010 service path remains under [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md).
- **FR-041**: Optional pricing-only endpoint remains allowed if pricing team does not already expose an equivalent.
- **FR-042**: Errors use shared shape `{"error": "<code>", "message": "<human-readable>"}`.
- **FR-043**: Validation → `400`; missing → `404`; training conflict (target) → `409`; unhandled → `500`.

### 5.6 Observability & config

- **FR-050**: Log `request_id`, pricing model identity when known, latency; training `job_id` when applicable.
- **FR-051**: Bedrock / LLM credentials, model paths, and feature flags via environment only; reflect in `.env.example` when implemented (Chapter 3: never hardcode API keys).
- **FR-052**: Heavy components (embedders, generators, rankers) SHOULD call **`warm_up()`** before serving traffic when used in a long-lived process (Chapter 3 performance guidance).
- **FR-053**: Pipeline graphs SHOULD be inspectable in development via Haystack’s **`.draw()`** (or equivalent) when diagnosing `PipelineConnectError` / socket mismatches.

---

## 6. Non-functional requirements

| ID | Requirement |
|----|-------------|
| **NFR-001** | Recommendation path (without training) SHOULD complete within reasonable interactive bounds; document Bedrock/LLM latency risk; consider streaming later for UX. |
| **NFR-002** | (Target) Training MUST NOT block Uvicorn workers indefinitely. |
| **NFR-003** | No secrets in code; provider keys via env or secrets manager only. |
| **NFR-004** | Layering: routers → services → pipelines/components/repositories; no graph/SQL in routers. |
| **NFR-005** | Snake_case JSON for request/response bodies. |
| **NFR-006** | Day 1 exit: Scenario A runs end-to-end with honest rationale before Day 2 SPEC lock / full-build scaffolding proceeds. |
| **NFR-007** | Prefer **pipeline-first** validation: deterministic components testable without an agent loop (Chapter 3 roadmap). |
| **NFR-008** | Production serve path SHOULD use async-capable ASGI (Uvicorn/FastAPI) so LLM I/O does not block the whole worker process (Chapter 7). **As-built:** recommend route is `async` and offloads sync `RecommendationService` (including sync `httpx` need-decomposer) via `run_in_threadpool`. Full async decomposer / shared lifespan-warmed client remains a follow-up before high-volume `NEED_DECOMPOSER=llm` traffic. |
| **NFR-009** | Containerized deploys SHOULD be configurable solely via environment/settings; no secrets in image layers. |

---

## 7. API contract (normative sketch)

Exact path and field names are finalized on Day 2 with the intake scaffold; the following is the working contract.

### 7.1 Recommend from project specification (MVP)

`POST /api/v1/recommendations/from-project-spec`  
JSON (`project_text`) or multipart (`file` ± `project_text`). Full field tables: [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md).

**Example request (JSON)**

```json
{
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "project_text": "Need two scissors lifts for indoor elevated work ~8m.",
  "options": {
    "include_pricing": true
  }
}
```

**Example response 200** (quantity 2 → two unit-needs; **exactly one `item` per unit-need**, not `items[]`)

```json
{
  "recommendation_id": "rec_01HZX...",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12",
  "results_by_need": [
    {
      "need_id": "need_1__u1",
      "item": {
        "equipment_type": "Scissors Lift",
        "asset_id": "optional-when-unit-level",
        "rank": 1,
        "rationale": "Assumed indoor platform work near 8m; scissors preferred. Refine height/capacity if outdoor or rough terrain is required (schema does not capture terrain/operator-required).",
        "pricing": {
          "daily_rate": 180.0,
          "total_price": 1260.0,
          "currency": "SGD",
          "deposit_rate": 0.30,
          "model_version": "experimental-ml_experiments-or-production-id",
          "explanation": "From predict_price() for this duration window."
        },
        "availability": "available"
      },
      "warnings": []
    },
    {
      "need_id": "need_1__u2",
      "item": {
        "equipment_type": "Scissors Lift",
        "asset_id": "optional-second-unit",
        "rank": 1,
        "rationale": "Second unit for quantity requested in project text.",
        "pricing": {
          "daily_rate": 180.0,
          "total_price": 1260.0,
          "currency": "SGD",
          "deposit_rate": 0.30,
          "model_version": "experimental-ml_experiments-or-production-id",
          "explanation": "From predict_price() for this duration window."
        },
        "availability": "available"
      },
      "warnings": []
    }
  ]
}
```

Public structured `POST .../from-needs` with client-posted `needs[]` is **not** the MVP contract (see intake SPEC change control).

### 7.2 Trigger training (target)

`POST /api/v1/ml/train` → `202` + `job_id`  
`GET /api/v1/ml/jobs/{job_id}` → status + metrics

---

## 8. Architecture

### 8.1 MVP pipeline (6-day) — pipeline-first

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
  results_by_need: { need_id, item: RecommendationItem | null }  // exactly one item per unit-need
```

Composition MUST follow Chapter 4 steps: select components → `Pipeline()` → `add_component` → `connect` → `run`; use `.draw()` in development to validate edges.

### 8.2 Haystack 2.0 building blocks mapped to this feature

| Concept (Ch. 3–4) | Use in this feature |
|-------------------|---------------------|
| **Component** (`@component`, `run()` → `dict`, typed sockets) | Rank/rationale; custom SQL, availability, `predict_price` wrappers |
| **`__init__` / `warm_up()` / `run()` life cycle** | Config only in `__init__`; load models/clients in `warm_up()`; process in `run()` (Ch. 5) |
| **Bridge components** | Optional adapters between domain records and Haystack `Document` / external lib types |
| **Immutable + metadata-safe transforms** | Custom ranking pre/post steps must not mutate shared candidate lists in place |
| **Pipeline** / **AsyncPipeline** (directed multigraph) | Ranking subgraph; full recommend graph; parallel branches |
| **`.add_component` / `.connect` / `.run` / `.draw`** | Mandatory construction & validation workflow (Ch. 4) |
| **Routers** (`FileTypeRouter`, conditional/metadata) | Target: branch project-spec files by type; optional policy branches |
| **SuperComponent** (`@super_component` or wrap instance) | Package “rank + rationale” or “retrieve + join + rerank” |
| **Tool** (name + description wrapper) | `recommend_prices`, `check_availability`, `rank_with_rationale`, `trigger_pricing_model_training` |
| **Agent** | Optional; prefer **LangGraph** for stateful multi-tool policy |
| **Indexing pipeline** (offline) | Target: catalog/historical docs → DocumentStore |
| **Query / RAG pipeline** (online) | Recommendation path; hybrid retrieve when knowledge base exists |
| **Sparse + dense retrievers**, **DocumentJoiner**, **reranker** | Target hybrid RAG before rationale generation |
| **DocumentStore** + embedders | Catalog / historical project knowledge |
| **Preprocessing components** | File → text for project-spec ingest |
| **Generation components** | Bedrock (or configured) LLM for ranking rationales |
| **Hayhooks** (optional later) | Deploy serialized pipeline as REST/MCP tool microservice |

### 8.2.1 Target hybrid knowledge path (Chapter 4 pattern)

```text
  need / query text
           │
           ├─► dense retriever (embeddings)  ─┐
           │                                  ├─► DocumentJoiner ─► reranker ─► PromptBuilder ─► Generator
           └─► sparse retriever (BM25)       ─┘
  (candidates still constrained by Asset SQL + availability + approved equipment types)
```

Naive (dense-only) RAG is acceptable as an intermediate step; hybrid + rerank is the preferred production retrieval shape when a document corpus exists.

### 8.3 Target hybrid graph (LangGraph + Haystack tools)

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
           │                                         ├─ rank_with_rationale (PromptBuilder+Generator)
           │                                         └─ trigger_pricing_model_training (async)
           ▼
  Assemble RecommendationItem[]
```

This matches Chapter 3’s recommended separation: **LangGraph directs; Haystack executes reliable, typed tool pipelines**.

### 8.4 Tools the agent may call (target)

| Tool name | Purpose | Sync/async |
|-----------|---------|------------|
| `retrieve_equipment_knowledge` | Haystack retrieval over catalog / past projects | Sync |
| `check_availability` | Date-window overlap / adapter | Sync |
| `recommend_prices` | `predict_price()` / rules | Sync |
| `rank_with_rationale` | PromptBuilder + Generator | Sync |
| `trigger_pricing_model_training` | Start training; return `job_id` | Async |

Safeguard: do not retrain on every user recommendation by default.

---

## 9. Domain constraints (product alignment)

- Approved types: **Boom Lift, Scissors Lift, Fork Lift, Excavator**.
- Shared rental window when dates supplied.
- Deposit guidance default **30%**; currency default **SGD**.
- Availability truth from fleet bookings data; this service recommends and filters, does not own bookings.
- Rationale MUST acknowledge **schema gaps** (e.g. terrain, operator-required) with team-agreed phrasing before Day 4 prompt lock.
- **Quantity** exists only on **internal** decomposed needs; expand to unit-needs. **`RecommendationItem` has no quantity.**
- **Exactly one** ranked recommendation per unit-need (`item`), not a list of alternatives.

---

## 10. Demo scenarios (normative for acceptance)

| Scenario | Intent | Build notes |
|----------|--------|-------------|
| **A** | Happy path — matches with honest rationale | Day 1 exit condition; primary live demo |
| **B** | Second clean path (alternate need / partial inference) | Full-day Day 1 + Day 5; live demo with A |
| **C** | No match / empty availability | Requires seeded overlapping bookings; Q&A back pocket |

Day 6 rehearsal: run **A + B** live; keep **C** for questions.

---

## 11. Data, models, and Haystack data types

| Concern | Guidance |
|---------|----------|
| Assets | Real `Asset` schema for SQL filter (Day 3); Day 1 may use small seed |
| Bookings | `Booking` / `BookingItem` overlap for availability |
| Pricing model | Owned by pricing team; recommendation only **calls** `predict_price()` |
| Training artifacts | Pricing workstream; this SPEC’s training tool section is target integration |
| Algorithm default (training) | XGBoost (+ joblib) already in stack |
| Haystack **Document** / **ByteStream** | Use when indexing catalog text or ingesting uploaded project files (target) |
| DocumentStore | Choose per environment (in-memory for prototype; production-grade store when retrieval is added) |
| **Knowledge graph** | Ragas `KnowledgeGraph` (nodes/edges); built offline from catalog + historical project text; optional JSON snapshot via saver component |

## 11.1 Knowledge graph (target capability)

**As-built (HR-76):** Optional user-scoped KG after project-spec **indexing** (`final_doc_joiner` chunks). Normative child: [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md). Default `KG_APPLY_TRANSFORMS=false` (document nodes); full Ragas transforms only inside `KnowledgeGraphGenerator` when enabled. Live HTTP still owned by [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) (`user_id` required). Sequential reading map: [`README.md`](./README.md).

**Target (this section):** broader offline catalog/historical-project KG, multi-hop for ranking/eval, optional online agent tools — not a substitute for Asset SQL / availability / `predict_price`.

**Source:** *Building Natural Language and LLM Pipelines*, **Chapter 5 — Haystack Pipeline Development with Custom Components** (local EPUB: `Chapter 5_ Haystack Pipeline Development with Custom Components.epub`). Implementation reference in the book’s repo: `ch5/jupyter-notebooks/scripts/knowledge_graph_component.py` (`KnowledgeGraphGenerator`, `KnowledgeGraphSaver`) and `ch5/pyproject.toml` for the dependency set used with that chapter.

### Purpose in this feature

A **knowledge graph** structures equipment catalog text, use-case notes, and historical project descriptions as **entities and relationships** so recommendation can support:

- Multi-hop suitability (“mezzanine install” → elevated work + material handling → Scissors Lift + Fork Lift)
- Clearer **rationale** paths (need → constraint → approved equipment type)
- **Schema-gap** callouts when relations the product cares about (e.g. terrain, operator-required) are absent from data
- Higher-quality **synthetic needs** for evaluation (optional follow-on with Ragas query synthesizers / testset generation)

The KG does **not** replace `Asset` SQL filtering, `Booking` availability, or `predict_price()`. Online recommendation remains: needs → candidates → availability → price → rank. The graph is an **offline enrichment and evaluation** asset unless a later SDD promotes graph traversal to an online tool.

### How Ragas stores KG data (Chapter 5 pattern)

| Stage | Storage |
|-------|---------|
| During `KnowledgeGraphGenerator.run` | **In-memory** `ragas.testset.graph.KnowledgeGraph` (nodes, then entities/relations after transforms) |
| After batch job | **JSON file** via `KnowledgeGraphSaver` (path under `KG_ARTIFACT_DIR`) |
| Synthetic tests (optional) | Tabular export (e.g. CSV) generated from the graph—not a Ragas DB |
| Default | **No** embedded graph database |

Neo4j is cited only in Chapter 5 *further reading*; it is **not** required to install or run the book’s KG component pattern.

### Pattern (Chapter 5 custom components + Ragas)

Aligned with the EPUB / book script:

1. Ingest Haystack documents (catalog chunks, project history) via indexing/preprocessing (`FileTypeRouter`, converters, `DocumentSplitter` as in Ch. 4–5 pipelines).
2. **Bridge** Haystack `Document` → LangChain `Document` (`page_content`, `metadata`) via **`DocumentToLangChainConverter`** (Chapter 5 “bridge component” pattern).
3. **`KnowledgeGraphGenerator`** (Haystack `@component`):
   - Construct `KnowledgeGraph()`; append `Node(type=NodeType.DOCUMENT, properties={...})` per document.
   - Wrap the Haystack LLM and embedder with **`HaystackLLMWrapper`** / **`HaystackEmbeddingsWrapper`** (`ragas-haystack`).
   - If `apply_transforms=True`, call **`default_transforms(...)`** then **`apply_transforms(kg, ...)`** so the LLM extracts entities/relations and embeddings support coherent links.
   - `run()` returns a **dict**: `knowledge_graph`, `node_count`, `transform_applied` (Chapter 5 output-socket rules).
4. **`KnowledgeGraphSaver`**: write the graph to JSON for reuse without re-running expensive transforms.
5. Downstream (optional): hybrid RAG over graph-derived text; `SyntheticTestGenerator`-style needs; Ragas metrics (faithfulness, context precision/recall, answer relevancy) on recommendation rationales.

**Life cycle (Chapter 5):** keep `__init__` lightweight (store generator/embedder references and flags); perform any heavy client/model setup in **`warm_up()`** if the component owns loading; never reload models inside every `run()` on a batch document stream.

Domain graph content SHOULD remain constrainable to the four approved types: Boom Lift, Scissors Lift, Fork Lift, Excavator.

### Technical dependencies (install)

Install **only** when implementing the KG target path (**not** required for Days 1–6 MVP). Prefer **uv** (haystack-fast-api standard).

**Minimum for Chapter 5 KG components:**

```bash
cd haystack-fast-api   # application module with pyproject.toml
uv add "ragas>=0.3.7" "ragas-haystack>=1.0.0" "langchain-core" "langchain-community>=0.4"
uv add nltk            # commonly required by Ragas text transforms
```

**Recommended parity with the book’s `ch5/pyproject.toml`** (ingest + local models + eval helpers used alongside KG in that chapter):

```bash
uv add "pandas>=2.3" "pypdf>=6" "pymupdf>=1.26" "trafilatura>=2" "rapidfuzz>=3"
uv add "sentence-transformers>=5" "transformers[sentencepiece,torch]>=4.57"
# Optional providers used in Ch.5 samples (choose what this project actually runs):
# uv add langchain-openai ollama-haystack
```

`haystack-ai` is already a project dependency; use project-consistent generators/embedders (Bedrock ranking stack and/or OpenAI/Ollama as configured).

| Package | Role (Chapter 5) |
|---------|------------------|
| **`ragas`** (≥ 0.3.7) | `KnowledgeGraph`, `Node`, `NodeType`, `default_transforms`, `apply_transforms`; synthetic testset utilities |
| **`ragas-haystack`** (≥ 1.0.0) | `HaystackLLMWrapper`, `HaystackEmbeddingsWrapper` |
| **`langchain-core`** / **`langchain-community`** | LangChain `Document` inputs to the KG component |
| **`nltk`** | Support for Ragas transforms |
| **`pypdf`** / **`pymupdf`** / **`trafilatura`** | PDF and web/catalog extraction before KG build |
| **`sentence-transformers`** / **`transformers`** | Local embeddings if not using cloud embedders only |
| **`pandas`** / **`rapidfuzz`** | Tabular synthetic-test handling / fuzzy helpers as in Ch.5 tooling |
| **`haystack-ai`** | `@component`, generators, embedders, pipeline wiring |

**Provider / runtime env** (document concrete keys in `.env.example` when implementing):

| Env | Purpose |
|-----|---------|
| LLM credentials for transforms (e.g. `OPENAI_API_KEY`, or existing Bedrock vars) | Entity/relation extraction in `apply_transforms` |
| Embedding model id + credentials | Semantic links in the graph |
| `KG_ARTIFACT_DIR` | Directory for JSON graph snapshots from `KnowledgeGraphSaver` |

**Not required for this pattern:** Neo4j (or other graph DB) packages/servers. Adding them needs a separate SDD.

**Python:** application targets **≥ 3.12**; Chapter 5 examples use **≥ 3.11**. After adds: `uv lock` && `uv sync --all-groups`. Never commit secrets.

### Suggested offline pipeline sketch (Chapter 5 assembly)

```text
  catalog PDFs / TXT / web notes
           │
           ▼
  FileTypeRouter → converters → DocumentSplitter
           │
           ▼
  DocumentToLangChainConverter     # bridge (Ch. 5)
           │
           ▼
  KnowledgeGraphGenerator          # Ragas KG + apply_transforms
         (HaystackLLMWrapper + HaystackEmbeddingsWrapper)
           │
           ├─► KnowledgeGraphSaver → KG_ARTIFACT_DIR/*.json
           └─► (optional) synthetic test generation → CSV/fixtures for eval
```

Wire online recommendation to KG signals only after batch quality is accepted (manual review or Ragas faithfulness on held-out needs). MVP recommend routes MUST remain import-safe if KG optional deps are not installed (lazy import or optional extra).

---

## 12. Acceptance criteria (GIVEN / WHEN / THEN)

1. **Given** Day 1 prototype setup, **when** Scenario A is run from a script/test against `app/pipelines/`, **then** end-to-end completes with rationale that states assumptions and includes a refinement suggestion where applicable.
2. **Given** free-text that decomposes into multiple unit-needs (or quantity expansion), **when** results are returned, **then** each unit-need has an independent entry with singular **`item`** (no cross-need merge; no multi-rank `items[]`).
2a. **Given** a decomposed need with `quantity = 2`, **when** expansion and ranking run, **then** two unit-need rows are returned and neither `RecommendationItem` carries a `quantity` field.
3. **Given** dates and seeded overlapping bookings, **when** Scenario C is exercised, **then** the no-match path sets `item: null` (with warnings) against real availability data.
4. **Given** `predict_price` from `ml_experiments/` (or production after swap), **when** ranking completes, **then** the selected `item` includes pricing fields from that function—not a local stub.
5. **Given** production `app/services/pricing/predict_price` is available, **when** Day 5 swap is done, **then** a single import change switches the pipeline; if not available, demo notes state experimental model explicitly.
6. **Given** Bedrock ranking is enabled, **when** specs are inferred or schema gaps apply, **then** rationale text includes assumption / refinement / schema-gap callouts per agreed phrasing.
7. **Given** empty project text / empty extract (and no file), **when** posted to the public endpoint, **then** `400` with shared error JSON.
8. **Given** Haystack ranking or custom domain components are used, **when** they are composed in a Pipeline, **then** connections use typed sockets via `.connect`, each custom `run()` returns a `dict` matching `@component.output_types`, and wiring does not depend on Haystack 1.x implicit dict passing.
8a. **Given** a custom component that needs a model or DB client, **when** it is used in a long-lived process, **then** heavy initialization occurs in `warm_up()` (not in `__init__` or every `run()`).
8b. **Given** empty candidates (Scenario C), **when** filter/rank components run, **then** they return predictable empty outputs without raising.
9. **Given** a ranking (or retrieve) Pipeline is defined in development, **when** engineers debug connectivity, **then** `.draw()` (or equivalent graph export) is available to inspect the multigraph.
10. **(Target)** **Given** catalog indexing is enabled, **when** hybrid retrieval is configured, **then** sparse and dense results are joined (and optionally reranked) before generation.
11. **(Target)** **Given** `POST /api/v1/ml/train`, **when** accepted, **then** `202` + `job_id` and job status progresses without blocking the recommendation path.
12. **(Target KG)** **Given** catalog/project documents and configured LLM + embedder, **when** `KnowledgeGraphGenerator` runs with `apply_transforms=True`, **then** a Ragas `KnowledgeGraph` is produced and can be saved to the configured artifact directory without affecting the online recommend path.
13. **(Target KG)** **Given** KG dependencies are not installed, **when** only MVP recommendation runs, **then** the service still operates (KG is optional target, not import-time hard failure on the recommend route).
14. **(Deployment)** **Given** the FastAPI app is started for serving, **when** the first recommend request uses a warmed generator/embedder path, **then** heavy model load was performed at lifespan/startup (`warm_up`), not re-initialized on every request.
15. **(Deployment / target)** **Given** a container image of the app, **when** run with required env vars, **then** `/health` succeeds and recommend config is read from environment rather than baked-in secrets.

---

## 13. Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Spec timing | Day 2 after Day 1 pipeline proof | Spec written against proven shape, not hope |
| Framework stance | **Pipeline-first Haystack**; LangGraph for stateful agent later | Chapter 3 hybrid architecture; reliability of typed tool layer |
| Pipeline API | `Pipeline` / `AsyncPipeline` + `add_component` / `connect` / `run` / `draw` | Chapter 4 directed multigraph construction |
| Retrieval (target) | Hybrid BM25 + dense → join → rerank | Chapter 4 hybrid RAG; better precision than naive dense-only |
| File ingest (target) | Router-based branching by type | Chapter 4 indexing `FileTypeRouter` pattern |
| Prototype location | `app/pipelines/`, no public route | Masterplan / execution plan |
| Pricing call | `ml_experiments.predict_price` → `app.services.pricing.predict_price` | Avoid local stub; non-blocking if production slips |
| Ranking | Haystack `PromptBuilder` + `Generator` (Bedrock) | Stock generation components; inspectable prompts |
| Custom domain steps | Custom `@component` with Ch. 5 life cycle (`__init__` / `warm_up` / `run`) | Extensibility; testable standalone; future Tool packaging |
| Component testing | Standalone + empty-input + config tests before full graph | Chapter 5 engineering discipline |
| Knowledge graph library | **Ragas** `KnowledgeGraph` + transforms (Ch. 5 pattern) | Matches book component; multi-hop + synthetic tests |
| KG storage (v1 target) | In-memory build + **JSON** artifact; no Neo4j by default | Simpler ops; Neo4j only via future SDD |
| KG in 6-day demo | **Out of critical path** | Demo uses SQL + availability + price + rank |
| Primary deploy | **FastAPI app in haystack-fast-api** (Ch. 7 Method 1) | Already the project stack; full control over SQL/pricing wiring |
| Hayhooks / MCP | Optional sidecar or tool export (Ch. 7 Method 2) | Velocity for pure pipelines; not second source of truth for fleet/price |
| Intake UX | Free-text box and/or file; LLM decomposes | Not a structured multi-need form (product correction) |
| Quantity | Expand to unit-needs; no qty on RecommendationItem | Item rows = units requested |
| One item per need | Singular `item` (not top-N `items[]`) | Clear portal binding; one selected recommendation |
| Multi unit-need | Independent per unit-need loop | Prevents merged/confused answers |
| Haystack Agent vs LangGraph | LangGraph preferred when state/memory policy grows | Chapter 3: Haystack agent loop can hide state (context opacity) |
| Training tool | Post–6-day / pricing-owned pipeline | Keeps demo focused; SPEC retains target contract |
| Catalog | Hard filter to 4 SG types | Portal product SPEC |
| Auth | Deferred | haystack-fast-api constitution |

---

## 14. Open questions

| # | Question | Resolve by |
|---|----------|------------|
| 1 | Refine/reject flow in scope for this build? | Day 2 |
| 2 | Persistence (“add to cart”) in scope or deferred? | Day 2 preferred; hard deadline Day 6 |
| 3 | Exact schema-gap rationale wording (terrain/operator-required)? | Before Day 4 ranking prompt lock |
| 4 | Does Day 5 demo run on experimental or production `predict_price`? | Log at Day 4 sync + Day 5 swap |
| 5 | Availability: in-process SQL only vs future Spring HTTP adapter? | Day 3; document here |
| 6 | Multipart project-spec ingest in MVP or target-only? | **Resolved: MVP** (free-text and/or file; see FR-001/002) |
| 7 | LLM/Bedrock model id and env key names? | Day 1/4 as wiring proceeds |
| 8 | When retrieval is added, which DocumentStore and embedder pair? | Before target retrieval work |
| 9 | Naive dense-only vs hybrid+rerank for catalog—what does evaluation require before locking? | Before target retrieval productionize |
| 10 | Prefer `AsyncPipeline` in MVP for availability∥pricing, or keep serial until measured latency pain? | Day 3–5 implementation choice; document here |
| 11 | KG LLM/embedder: same Bedrock stack as ranking, or separate OpenAI/Ollama as in Ch.5 samples? | Before first KG batch job |
| 12 | Persist KG only as JSON artifacts, or also promote triples into DocumentStore/hybrid index? | Before online use of graph signals |
| 13 | Is Neo4j (or other graph DB) ever required, or is Ragas in-memory + JSON enough for v1 target? | Default: **no Neo4j** until a dedicated SDD |
| 14 | Dockerize only the FastAPI monolith, or also a Hayhooks sidecar for rank-only MCP tools? | Post-demo; default: monolith first |
| 15 | Auth for recommend routes: API key, interim portal JWT, or network policy only until shared auth SDD? | When leaving open-dev posture |

---

## 15. Deployment (from Haystack Chapter 7)

**Source:** *Building Natural Language and LLM Pipelines*, **Chapter 7 — Deploying Haystack-Based Applications** (local EPUB: `Chapter 7_ Deploying Haystack-Based Applications.epub`).

This feature is hosted in **`haystack-fast-api`**, which already uses **FastAPI + Uvicorn + Pydantic** (`app.main:app`). Chapter 7’s **Method 1 (custom FastAPI)** is therefore the **primary** deployment path. **Method 2 (Hayhooks + serialized YAML)** is an optional velocity path for exporting pure Haystack pipelines (e.g. rank-only or offline KG/index jobs) as disposable services or **MCP tools**.

### 15.1 Production needs (apply to recommendation API)

| Need (Ch. 7) | Meaning for this feature |
|--------------|--------------------------|
| **Scalability / elasticity** | Serve concurrent recommend requests; containerize so replicas can scale (Docker; orchestrator optional later) |
| **Accessibility** | Stable REST API consumed by React portal / Spring; OpenAPI via FastAPI |
| **Resource management** | LLM/embedder calls are I/O-bound—async FastAPI helps; `warm_up()` heavy components at process start, not per request |
| **Security** | No open anonymous abuse of LLM-backed routes; secrets via env; validate bodies with Pydantic |
| **Operability** | Health checks, structured logs, CI that builds/tests the image or app |

### 15.2 Method 1 — FastAPI (normative for this repo)

Chapter 7 rationale: FastAPI on **Starlette (ASGI)** + **Uvicorn** for concurrent I/O while waiting on LLM/`predict_price`; **Pydantic** for request/response validation and OpenAPI.

**Requirements for this feature’s HTTP surface:**

- **FR-D01**: Recommendation (and future KG/train admin) endpoints MUST be exposed through the existing FastAPI app factory pattern (`create_app` / router inclusion)—thin routers, services/pipelines behind them (unchanged layering).
- **FR-D02**: Request/response bodies MUST use **Pydantic** models (snake_case JSON as elsewhere in this SPEC).
- **FR-D03**: Application **lifespan** (or equivalent startup hook) SHOULD call **`warm_up()`** on heavy Haystack components (generators, embedders, rerankers) once per process before serving traffic (aligns Ch. 5 life cycle + Ch. 7 serve path).
- **FR-D04**: Pipeline or service instances used by recommend routes SHOULD be provided via **dependency injection** (or app.state), not re-built on every request.
- **FR-D05**: Configuration (model ids, `KG_ARTIFACT_DIR`, pricing paths, provider keys) MUST come from **environment / settings** (pydantic-settings)—never hardcoded secrets (Ch. 7 + prior FR-051).
- **FR-D06**: When auth is introduced (currently deferred per constitution), protect LLM-backed recommend routes (e.g. API key or shared JWT with portal/Spring); keep **health** publicly reachable for probes.

**Docker (Ch. 7 packaging):**

- **FR-D07**: Production deploy SHOULD use a **container image** of the FastAPI app (multi-stage build preferred: build deps → lean runtime image).
- **FR-D08**: Run with an ASGI server (Uvicorn or compatible) binding `app.main:app`; pass secrets and config as env vars or a secret store at runtime.
- **FR-D09**: Health endpoint(s) MUST remain usable by orchestrators (`GET /health` as already specified in project setup).

**CI/CD (Ch. 7):**

- **FR-D10**: Changes to recommendation pipelines/API SHOULD pass automated test + build in CI (project’s existing pipelines / GitHub Actions as applicable). Container build on mainline releases is recommended when Docker is adopted.

### 15.3 Method 2 — Hayhooks + pipeline serialization (optional)

Chapter 7 **Hayhooks**: serialize a Haystack `Pipeline` to YAML (or supported artifact), load it in Hayhooks, which generates a FastAPI front door without hand-writing boilerplate.

**When to use for this feature:**

- Exporting a **self-contained** ranking or hybrid-retrieve pipeline as a sidecar
- Exposing a pipeline as an **MCP tool** for an external agent (Ch. 7 MCP support via Hayhooks)
- Rapid demos of pure Haystack graphs without the full domain SQL/pricing app

**Requirements if adopted:**

- **FR-D11**: Serialized artifacts MUST be versioned with the code that built them; document how to re-serialize after pipeline changes.
- **FR-D12**: Hayhooks (or similar) deployments MUST NOT become a second source of truth for **availability or pricing**—those stay in the main app calling `predict_price` and DB/SQL components.
- **FR-D13**: If Hayhooks is fronted by a reverse proxy (Ch. 7 Nginx sample), apply auth (e.g. basic auth or API gateway), **rate limiting**, upload size limits, and extended timeouts for long LLM runs; keep probe/health paths appropriately open.

### 15.4 MCP (optional agent integration)

Chapter 7: **MCP** lets external agents discover deployed Haystack pipelines as tools. Relevant if LangGraph or another orchestrator consumes `rank_with_rationale` / retrieve tools over the network.

- **FR-D14**: MCP exposure is **optional** and MUST map to the same tool contracts as §8.4 (name + description + deterministic Haystack work).
- **FR-D15**: MCP/Hayhooks tool endpoints are subject to the same security and timeout expectations as Method 1 LLM routes.

### 15.5 Explicitly out of scope for Day 1–6 demo

- Full Kubernetes manifests (may follow once Docker path is stable)
- Mandatory Hayhooks for the primary recommend API (FastAPI app remains canonical)
- Replacing Spring or React deployment with Hayhooks

### 15.6 Deployment checklist (post-MVP / production hardening)

1. Lifespan `warm_up` for generators/embedders used in rank (and KG batch workers if any).
2. Pydantic validation on all public recommend bodies.
3. Multi-stage Docker image + env-based config.
4. Auth strategy for LLM routes when constitution adds auth.
5. CI: pytest + image build (and optional smoke against `/health` + one recommend fixture).
6. Optional: serialize rank subgraph + Hayhooks/MCP only if a consumer needs a pure-pipeline tool.

---

## 16. Implementation tasks (ordered) — 6-day plan + Haystack practices


### Day 1 — Prototype (outside SDD; branch `feature/agent-1-prototype`)

- Build under `app/pipelines/` only; standalone script or one-off test.
- Import `predict_price()` from `ml_experiments/` (no local stub).
- Implement ranking with Haystack `PromptBuilder` / `Generator` (stub-LLM if Bedrock auth blocks).
- Prefer early **custom `@component`** for Asset filter, availability, and `predict_price` adapter: `@component` + lightweight `__init__` + `run()` → `dict` + `@component.output_types`; add `warm_up()` if a client/model is held.
- Validate each custom component **standalone** before `Pipeline.connect` (Chapter 5).
- **Half-day path**: hardcoded single need, SQL filter, stubbed availability, real `predict_price()`, Haystack ranking, Scenario A.
- **Full-day path**: + Scenarios B/C, real `Booking`/`BookingItem` query, real Bedrock, rehearse two clean demos.
- **Exit**: Scenario A end-to-end with honest rationale. Do not start Day 2 until this holds.
- Once ranking is a Haystack `Pipeline`, call `.draw()` to validate `PromptBuilder` → `Generator` edges (Chapter 4 visualization step).

### Day 2 — Spec checkpoint + scaffolding (`feature/agent-2-spec-and-scaffold`)

- Lock this SPEC against proven pipeline; link masterplan for rationale.
- Resolve refine/reject and persistence scope questions.
- Scaffold free-text / file intake UI contract and confirm `POST .../from-project-spec` in §7 + child intake SPEC; wire LLM (or stub) decomposer + quantity expansion + singular `item`.

### Day 3 — Real candidates + availability (`feature/agent-3-candidates-availability`)

- Port SQL filter to real `Asset` schema.
- Real availability overlap if not done Day 1; seed data so Scenario C fires.
- Wire per-need loop to real endpoint; verify independent rankings.
- Keep domain steps component-shaped for later SuperComponent packaging.

### Day 4 — Ranking + pricing sync (`feature/agent-4-ranking-pricing-sync`)

- Production Haystack Bedrock ranking + rationale/assumption/schema-gap text.
- **`warm_up()`** generators if process is long-lived.
- **Sync with pricing team Day 4** (`feature/ml-3-pricing-service`): start production `predict_price` swap if ready; else keep `ml_experiments/` and log the decision.
- Confirm tool **description** wording if any step is already Tool-wrapped (avoid ambiguous agent prompts later).

### Day 5 — E2E + price swap (`feature/agent-5-e2e-integration`)

- Complete import swap if ready; else flag fast-follow and note experimental model on demo.
- Full A/B/C through real intake → availability → pricing → ranking.
- Unit tests (Chapter 5 principles): SQL filter, availability overlap, per-need independence, rationale callouts; **standalone component tests**; **empty candidate list** behaviour; `__init__` configuration; mock external pricing/LLM where needed; socket contracts on Pipeline connect.

### Day 6 — Persistence decision, polish, demo (`feature/agent-6-demo-prep`)

- Implement minimal cart write **or** document deferred in SPEC + demo notes.
- README, polish, rehearse A+B live; C for Q&A.

### Target follow-ons (not required for 6-day demo)

- Multipart / project-text ingest via **FileTypeRouter** + preprocessing branches (Ch. 4 indexing pattern).
- Offline **indexing pipeline** for equipment catalog / historical projects into a DocumentStore.
- **Knowledge graph batch job**: `DocumentToLangChainConverter` → `KnowledgeGraphGenerator` → `KnowledgeGraphSaver`; install deps in §11.1.
- **Hybrid retrieval** (BM25 + dense → DocumentJoiner → reranker) feeding rationale generation; optionally index graph-derived text.
- SuperComponents via **wrap-instance** or **`@super_component`** for rank+rationale and retrieve+join+rerank.
- Full Chapter 5 test suite pattern for every custom component (mock LLM/pricing, life-cycle tests, edge cases).
- **AsyncPipeline** for parallel availability/pricing or dual retrievers.
- LangGraph tool registry including `trigger_pricing_model_training`.
- Training job API and background runner integration with pricing artifacts.
- **Docker multi-stage image** + CI build for the FastAPI app (Chapter 7 Method 1).
- Optional **Hayhooks** deployment of a serialized rank/retrieve pipeline as REST/MCP tool (Chapter 7 Method 2)—not a second availability/price authority.
- Auth on LLM-backed routes when project-wide auth SDD lands; rate limits / proxy timeouts for long recommend calls.

### Troubleshooting checklist (from Chapter 3, adapted)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Ingest/parse failures | Bad paths, chunk/config, converter errors | Check converter/preprocessor logs; validate paths and sizes |
| Wrong branch for file type | Missing/incorrect `FileTypeRouter` mapping | Verify MIME/router outputs; add branch for DOCX/PDF/TXT |
| `PipelineConnectError` | Incompatible or missing sockets; wrong connect order | Map inputs/outputs per component; use `.draw()` (Ch. 4) |
| Empty or weak retrieval | Naive dense-only miss on jargon/model codes | Add BM25 branch + `DocumentJoiner`; consider reranker |
| Slow first request / reload every run | Model or client loaded in `run()` or heavy work in `__init__` | Move load to `warm_up()`; keep `__init__` config-only (Ch. 5) |
| Pipeline gets mutated/wrong data mid-branch | In-place mutation of shared documents/candidates | Immutable transforms; copy metadata explicitly |
| Type/integration errors at connect or run | Output dict keys ≠ `@component.output_types`; wrong `run()` annotations | Align sockets; test component standalone before connect |
| Crash on Scenario C / no matches | Empty list not handled | Return empty structured output; no exception on empty candidates |
| Serial latency on independent work | Availability/price or dual retrieve run strictly in series | Restructure as parallel branches / `AsyncPipeline` |
| Odd agent tool use (target) | Ambiguous tool description | Refine name/description; inspect reasoning traces |
| Credential leakage / auth failures | Hardcoded keys | Env / secrets only |

### PR / review convention

- Subtask 1 (prototype): lighter review, merge fast.
- Subtasks 2–5: full review (demo + `RecommendationItem` consumers depend on this).
- Subtask 4: hard external dependency on pricing Day 4—log experimental vs production pricing for the demo.

---

## 17. Jira subtasks / branches

| # | Status | Jira subtask | Branch | Covers | Day |
|---|--------|--------------|--------|--------|-----|
| 1 | ☐ | Prototype — pipeline shape proof | `feature/agent-1-prototype` | Hardcoded need(s), SQL filter, stubbed/real availability, `ml_experiments/predict_price`, Haystack ranking components, Scenario A (+B/C if full-day) | 1 |
| 2 | ☐ | Spec + full-build scaffolding | `feature/agent-2-spec-and-scaffold` | This SPEC locked, free-text/file intake, decomposer, quantity expansion, singular item | 2 |
| 3 | ☐ | Real candidate selection & availability | `feature/agent-3-candidates-availability` | Real `Asset` SQL, real booking overlap, per unit-need loop | 3 |
| 4 | ☐ | Ranking integration & pricing sync | `feature/agent-4-ranking-pricing-sync` | Bedrock ranking, rationale text, pricing Day 4 sync, `warm_up` | 4 |
| 5 | ☐ | End-to-end integration & price swap | `feature/agent-5-e2e-integration` | Production price swap if ready, A/B/C, unit tests | 5 |
| 6 | ☐ | Persistence decision, polish, demo prep | `feature/agent-6-demo-prep` | Cart or defer, README, rehearsal | 6 |

---

## 18. Change control

| Version | Date | Notes |
|---------|------|--------|
| 0.1.0 | 2026-08-04 | Initial draft: agentic recommendation, pricing recommender, tool-triggered ML training for haystack-fast-api |
| 0.2.0 | 2026-08-05 | Merged recommendation-agent execution plan: 6-day schedule, `predict_price` path, Scenarios A/B/C, Jira branches; MVP vs target clarified |
| 0.3.0 | 2026-08-05 | Incorporated Haystack Chapter 3 (deepset): hybrid LangGraph + Haystack tool-layer stance; Component → Pipeline → SuperComponent → Tool → Agent hierarchy; `@component` / typed sockets / `PromptBuilder`+`Generator`; SuperComponents & Tools; `warm_up()`, `.draw()`, troubleshooting; pipeline-first MVP with agent/LangGraph as target |
| 0.4.0 | 2026-08-05 | Incorporated Haystack Chapter 4: pipeline design steps (`Pipeline`/`add_component`/`connect`/`run`/`draw`); directed multigraphs; branching & `FileTypeRouter`; indexing vs query pipelines; hybrid RAG (BM25+dense → DocumentJoiner → reranker); SuperComponent packaging methods; `AsyncPipeline` parallelization; expanded troubleshooting & acceptance criteria |
| 0.5.0 | 2026-08-05 | Incorporated Haystack Chapter 5 (custom components): `@component` / `__init__` (config-only) / `warm_up()` / `run()`→dict / `@component.output_types`; immutable processing & metadata preservation; bridge components; standalone testing; empty-input & config tests; custom component inventory for Asset/availability/pricing/rank |
| 0.6.0 | 2026-08-05 | Added **Knowledge Graph** target capability (Ragas `KnowledgeGraph` + `apply_transforms`, Ch. 5): purpose for multi-hop/rationale/schema gaps; components `DocumentToLangChainConverter`, `KnowledgeGraphGenerator`, `KnowledgeGraphSaver`; **uv install deps** (`ragas`, `ragas-haystack`, langchain-*, optional PDF/embed stacks); env keys; JSON persistence; Neo4j explicitly optional/not default; AC 12–13 |
| 0.6.1 | 2026-08-05 | Strengthened §11.1 against Chapter 5 EPUB + book `knowledge_graph_component.py` / `ch5/pyproject.toml`: explicit storage model (in-memory → JSON); `HaystackLLMWrapper` / `HaystackEmbeddingsWrapper`; full install tables; lazy-import note for MVP routes |
| 0.7.0 | 2026-08-05 | Incorporated Chapter 7 (Deploying Haystack-Based Applications): Method 1 FastAPI primary (lifespan/`warm_up`, Pydantic, DI); Docker multi-stage; CI/CD; security; optional Method 2 Hayhooks serialization + MCP; deployment NFRs and AC 14–15; section renumber 15–18 |
| 0.8.0 | 2026-08-05 | **Intake correction:** MVP is free-text/file + LLM decompose (not structured multi-need form); quantity expansion to unit-needs; **exactly one** `item` per unit-need (no top-N `items[]`); public API `POST .../from-project-spec`; child intake SPEC v0.2.0 |
| 0.9.0 | 2026-08-06 | **PR review alignment:** pricing on recommend items is `daily_rate` + `total_price` (no fabricated `weekly_rate`); **FR-012/015** + **NFR-008** note threadpool offload; warm-up DI still follow-up |
| 0.9.1 | 2026-08-07 | **As-built override on FR-040:** public `/from-project-spec` is indexing ingest per child indexing SPEC; recommend envelope deferred for reattach |
| 0.9.2 | 2026-08-07 | §11.1 as-built pointer to SPEC-knowledge-graph (HR-76); sequential README map |

When behaviour, API paths, tool names, or schedule gates change, bump this table and align OpenAPI / tests / execution plan in the same change set.
