# Equipment Recommendation Specification

| Field | Value |
|-------|--------|
| **Status** | Draft — target state (6-day plan + Haystack Ch. 3–5, 7 deployment patterns; KG target); as-built HTTP override on live ingest |
| **Feature id** | `agentic-equipment-recommendation-pricing` |
| **Standards** | OpenSpec · Spec-kit user stories · OpenSPDD (see [`design.md`](./design.md)) |
| **Parent product capability** | Yes — owns end-to-end product SDD |
| **Child capabilities** | [`../indexing/spec.md`](../indexing/spec.md); [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md); [`../recommendation-intake/spec.md`](../recommendation-intake/spec.md); [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md); [`../dynamic-pricing/spec.md`](../dynamic-pricing/spec.md) |
| **Map** | [`../../AGENTS.md`](../../AGENTS.md) Path D |
| **Haystack reference** | *Building Natural Language and LLM Pipelines* — Ch. 3–5, **7** |
| **Depends on** | `haystack-ai` (Haystack 2.0), LangGraph, real `Asset` / `Booking` / `BookingItem` schema, pricing `predict_price()`; (target KG) `ragas`, `ragas-haystack`, LangChain document types |
| **Legacy source** | `specification/SPEC-agentic-equipment-recommendation-and-pricing.md` (removed 2026-08-13; see [`../../TRACEABILITY.md`](../../TRACEABILITY.md)) |

**Read** [`../../project.md`](../../project.md) and [`../project-setup/spec.md`](../project-setup/spec.md) first. Domain: [`../domain/spec.md`](../domain/spec.md).

## Document roles (do not duplicate)

| Document | Owns |
|----------|------|
| **This capability** | Normative product behaviour, FRs, NFRs, ACs, API sketch, domain constraints, demo scenarios, key decisions, open questions |
| [`design.md`](./design.md) | Architecture, Haystack mapping, day plan, deployment (REASONS) |
| `recommendation-agent-masterplan.md` (docs if present) | Decisions and rationale trail |
| Child stage capabilities | Live indexing, KG, deferred intake envelope, FR-010 pipeline, production pricing |

---

## Purpose

This capability defines the **agentic AI decision and recommendation system** inside `haystack-fast-api` that:

1. Accepts **unstructured project input** — a **single free-text box** and/or an **uploaded file** of unstructured text — plus optional **rental start/end dates**. The portal does **not** use a repeatable structured “add another need” form for MVP.
2. **LLM-decomposes** that text into internal equipment needs (description, optional hints, optional **quantity**), then **expands quantity** into unit-needs (`RecommendationItem` has **no** `quantity` field).
3. Runs a **Haystack 2.0 pipeline-first** recommendation path (custom components + ranking generation) to select suitable equipment against the real fleet schema.
4. Filters candidates by **availability** using `Booking` / `BookingItem` overlap for the requested window.
5. Attaches **pricing** by calling the pricing team’s `predict_price()` (experimental `ml-experiments/` during prototype; production `app/services/pricing/` when ready).
6. Returns **exactly one ranked `RecommendationItem` per unit-need** (or null if no match) with honest rationales (assumptions, refinement suggestions, schema-gap callouts)—**not** a top-N list of alternatives per need.
7. **(Target / post–6-day MVP)** Exposes the same deterministic work as **tools** (and optionally a LangGraph orchestrator) and allows an agent tool or operator endpoint to **trigger the machine-learning training pipeline** asynchronously.

### Architectural stance (from Haystack Chapter 3)

Chapter 3 frames a **hybrid architecture**: a **stateful orchestration layer (LangGraph)** directing a set of **reliable, auditable tool layers (Haystack)**. Haystack’s primary strength is as a **pipeline-first engine**.

| Layer | Role in this feature |
|-------|----------------------|
| **Haystack pipelines / components** | Deterministic tool layer: SQL candidate filter, availability, pricing wrapper, ranking (`PromptBuilder` + `Generator`) |
| **Plain-Python / service loop (MVP)** | Per-need orchestration before full agent adoption |
| **LangGraph (target)** | Stateful orchestration when multi-step tool selection, memory, or retrain policy is required |
| **Haystack Agent (optional)** | Sufficient only for simpler tool loops; prefer LangGraph when context/state control matters |

Hierarchy: `Component → Pipeline → SuperComponent → Tool → Agent`.

MVP builds **Components** and a **Pipeline** under `app/pipelines/`. Target may wrap ranking/pricing subgraphs as **SuperComponents**, register them as **Tools**, and optionally drive them from an **Agent** or **LangGraph**.

---

## Outcomes

- A customer (or portal) can submit **free-text and/or a project file** (+ optional dates) and receive recommendations for each **unit-need** after LLM decomposition and quantity expansion (**product target**; live HTTP is indexing — see FR-040 as-built override).
- Recommendations use real **Asset** SQL filtering and real **availability** overlap queries when wired (Day 3+); MVP as-built uses seed fleet (pipeline capability).
- Each unit-need has **exactly one** ranked **`item`** (or null if no match), with an honest **rationale** when selected.
- Pricing is obtained via **`predict_price()`**—never a local stub once the pricing team’s temporary experimental function exists; production swap is a one-line import when `app/services/pricing/` lands.
- Public behaviour is expressed through this capability and child intake; routers stay thin; pipeline logic lives under `app/pipelines/`.
- Haystack pieces follow 2.0 contracts: **`@component`**, typed **input/output sockets**, explicit pipeline connections.
- **(Target)** Tools and/or a LangGraph graph can call `trigger_pricing_model_training`; training is asynchronous.

---

## Scope

### In scope (6-day MVP + target)

| Area | MVP (Days 1–6) | Target (post-MVP / full agentic) |
|------|----------------|----------------------------------|
| **Intake** | Single free-text box and/or file; LLM decomposes → internal needs; quantity expansion; optional dates | Richer file types, stronger decompose prompts, optional human edit of decomposed needs |
| **Haystack building blocks** | Custom `@component` + Pipeline for rank/rationale; service-level loop for SQL/availability/price | SuperComponents; Tools; optional Agent or LangGraph |
| **Candidate selection** | SQL filter against real `Asset` schema (seeded subset OK Day 1) | Same + optional retrieval / document store over catalog |
| **Availability** | `Booking` / `BookingItem` overlap; Scenario C on real data | Same; optional Spring adapter |
| **Ranking** | Haystack `PromptBuilder` / `Generator` (Bedrock); stub-LLM if Bedrock blocks | Same; richer agent decide node |
| **Pricing** | Call `ml_experiments.predict_price()` then swap to production | Same wrapped as Tool `recommend_prices` |
| **Explainability** | Rationale: assumptions, refinement, schema-gap | Optional SHAP on pricing |
| **ML training tool** | **Out of 6-day scope** | Tool `trigger_pricing_model_training` + `POST /api/v1/ml/train` + job status |
| **Knowledge graph** | **Out of 6-day critical path** (as-built: mandatory KG after indexing — see knowledge-graph capability) | Offline catalog/historical KG-2; multi-hop for ranking/eval |
| **Deployment** | Dev: Uvicorn + FastAPI app factory | Ch. 7: containerize; optional Hayhooks; CI/CD; optional MCP |
| **Persistence** | Resolve Day 2/6: minimal cart or deferred | Recommendation metadata in Postgres if retained |
| **Demo scenarios** | A (happy), B, C (no match)—rehearse A+B live; C for Q&A | Same |

### Out of scope

- Real payment gateway or booking lifecycle ownership (Spring / portal).
- Live inventory mutation or locking of units (availability is **read-only**).
- Multi-tenant auth / JWT until a shared auth SDD exists.
- Changing the four approved equipment types (hard filter).
- **Refine/reject flow** — only if explicitly resolved yes on Day 2; otherwise deferred.
- **“Add to cart” persistence** — only if resolved yes by Day 6; otherwise deferred.
- Training on arbitrary external datasets without a defined schema.
- Mobile operator app flows.
- Mandatory Hayhooks/MCP in the 6-day window.

---

## User Scenarios & Testing

### User Story 1 - Customer free-text / file recommend (Priority: P1)

As a customer, I paste a project description (or upload a file) and rental dates so that I receive **exactly one** suitable, **available** recommendation per unit-need with prices and clear reasons—without filling a multi-row needs form.

**Independent Test:** Service-level FR-010 e2e (`tests/test_recommend_pipeline_mvp.py`); live HTTP is ingest until reattach.

**Acceptance Scenarios:** See § Acceptance criteria items 1–7 below.

### User Story 2 - Pipeline uses predict_price (Priority: P1)

As the recommendation pipeline, I call **`predict_price()`** for each candidate path and never block the demo on a missing production pricing module if the experimental function is still in place.

### User Story 3 - Day 1 Scenario A proof (Priority: P1)

As an implementer, I prove Scenario A end-to-end on Day 1 before writing the locked API contract on Day 2.

### User Story 4 - Train pricing model tool (Priority: P3) — TARGET

As the recommendation agent, I may call a **train_pricing_model tool** that starts training without blocking the current recommendation (default: not on every request).

### Actors

| Actor | Goal |
|-------|------|
| **Customer / portal / intake UI** | Submit free-text or file (+ optional dates) → one recommended available asset per unit-need + prices. |
| **Recommendation pipeline / agent** | Decompose → expand quantity → filter → availability → price → rank; emit honest rationales. |
| **Pricing team** | Provide `predict_price()`; own training pipeline. |
| **Ops / data scientist** | (Target) Trigger or schedule ML training; poll job status. |
| **Spring REST API** (future) | May call this service or share DB read models. |

---

## Requirements

### Requirement: Unstructured intake (FR-001)

The service MUST accept recommendation requests as **unstructured** input: JSON `project_text` and/or `multipart/form-data` (`file`, optional `project_text`) plus optional `start_date` / `end_date` (ISO 8601 date). MVP UI is a **single free-text box or file upload**—**not** a repeatable structured “add another need” form.  
Normative detail: [`../recommendation-intake/spec.md`](../recommendation-intake/spec.md).

#### Scenario: Free-text and/or file
- **WHEN** a portal submits project needs for recommend (product target)
- **THEN** input is free-text and/or file, not multi-row structured form

### Requirement: Supported file types (FR-002)

MVP minimum: `text/plain`, `text/markdown`. PDF and DOCX SHOULD be supported via converters when enabled. Unsupported types → `400` shared error shape. Live indexing expands MIME map (see indexing capability).

#### Scenario: Unsupported type
- **WHEN** an unsupported file type is posted on recommend extract rules
- **THEN** response is **400** shared error shape

### Requirement: File ingest and LLM decompose (FR-003)

File ingest SHOULD prefer Haystack-style preprocessing. Source text MUST then be passed to an **LLM need decomposer** that emits internal needs (`need_id`, `description`, optional `equipment_hints`, optional `quantity` ≥ 1).

#### Scenario: Decompose emits needs
- **WHEN** non-empty source is decomposed
- **THEN** internal needs include description and optional quantity/hints

### Requirement: Empty input rejected (FR-004)

Empty `project_text` / empty file extract / empty decompose result → `400`.

#### Scenario: Empty project text
- **GIVEN** empty project text and no file
- **WHEN** posted
- **THEN** **400** with shared error JSON

### Requirement: Independent unit-need processing (FR-005)

After decomposition and quantity expansion, each **unit-need** MUST be processed **independently**—not a single merged/confused ranking across unit-needs.

#### Scenario: Multi-need independence
- **WHEN** multiple unit-needs are ranked
- **THEN** each has an independent result entry

### Requirement: Quantity expansion (FR-006)

If a decomposed need has **`quantity = N`** (*N* ≥ 1), the system MUST expand it into **N unit-needs** before ranking. **`RecommendationItem` MUST NOT include a `quantity` field.** Unit-need ids: `base_id` when *N* = 1; `{base_id}__u{i}` for *i* = 1..*N* when *N* > 1.

#### Scenario: Quantity two
- **GIVEN** `quantity = 2`
- **WHEN** expansion and ranking run
- **THEN** two unit-need rows and neither RecommendationItem has `quantity`

### Requirement: Singular item per unit-need (FR-007)

For each unit-need, the response MUST expose **exactly one** ranked recommendation via singular **`item`** (`RecommendationItem | null`). MUST NOT return a multi-element list of ranked alternatives per need.

#### Scenario: Not top-N alternatives
- **WHEN** a unit-need is assembled
- **THEN** key is singular `item`, not `items[]`

### Requirement: FR-010 pipeline structure

Recommendation orchestration for the 6-day build MUST follow this shape under `app/pipelines/` / services:

1. **Resolve source text** — free-text and/or file extract  
2. **LLM decompose** — unstructured text → internal needs  
3. **Expand quantity** — internal needs → unit-needs (**FR-006**)  
4. **SQL candidate filter** — against real `Asset` schema (seeded subset acceptable Day 1)  
5. **Availability filter** — `Booking` / `BookingItem` overlap  
6. **Price** — call `predict_price()`  
7. **Rank / rationale** — select **one** best match per unit-need; assumptions / refinement / schema-gap  
8. **Assemble** — one `item` (`RecommendationItem | null`) per unit-need  

As-built service detail: [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md).

#### Scenario: Eight-step shape present
- **WHEN** recommend service runs
- **THEN** steps 1–8 are implemented (seed fleet acceptable for 4–5 MVP)

### Requirement: Approved catalog only (FR-011)

Responses MUST only include equipment consistent with **Boom Lift, Scissors Lift, Fork Lift, Excavator** unless product policy expands later.

#### Scenario: Catalog membership
- **WHEN** an item is selected
- **THEN** equipment type is in the approved catalog

### Requirement: RecommendationItem fields (FR-012)

Each `RecommendationItem` MUST include at least: identity/type fields, rank or score, **rationale** (honest), pricing fields from `predict_price()` when included, and availability outcome. MUST NOT include `quantity`. When pricing is present, expose **`daily_rate`** (scoped to request duration) and **`total_price`** (`daily_rate × duration_days`)—MUST NOT fabricate **`weekly_rate`** as `daily × 7`.

#### Scenario: Pricing fields
- **WHEN** pricing is included on a selected item
- **THEN** `daily_rate` and `total_price` are present without fabricated weekly rate

### Requirement: Availability before ranking (FR-013)

When dates are provided, availability filtering MUST run before final ranking presentation for that unit-need.

#### Scenario: Dates force availability first
- **GIVEN** both dates set
- **WHEN** unit-need is processed
- **THEN** availability runs before rank

### Requirement: Prototype location (FR-014)

Prototype code MUST live under `app/pipelines/` and MUST NOT be registered on a public route until Day 2+ scaffold wires the real endpoint (Day 1: standalone script/test).

### Requirement: Thin routers (FR-015)

Routers MUST stay thin; pipeline construction and SQL live in services/pipelines/repositories. Async recommend handlers MUST offload sync service (e.g. `run_in_threadpool`) so LLM/pipeline I/O does not block the ASGI event loop (child **FR-P-012**, **NFR-008**).

#### Scenario: Threadpool offload
- **WHEN** async recommend/ingest handler runs
- **THEN** sync service is offloaded from the event loop

### Requirement: Haystack component rules (FR-016–FR-019f)

- **FR-016**: Haystack-native units MUST be `@component` classes with `run()` entry point.
- **FR-017**: Typed input/output sockets; `run()` returns **dict** matching `@component.output_types` (**FR-017a**).
- **FR-017b**: `__init__` lightweight (config only).
- **FR-017c**: Heavy setup in **`warm_up()`**, not every `run()`.
- **FR-017d**: Prefer immutable processing; preserve metadata.
- **FR-017e**: Bridge components for external type conversion.
- **FR-018**: Domain logic (Asset filter, booking overlap, `predict_price` adapter) SHOULD be custom components under `app/pipelines/`.
- **FR-018a**: Runnable standalone before Pipeline wire.
- **FR-018b**: Empty candidate/document lists → predictable empty outputs, no unhandled exceptions.
- **FR-019**: Ranking generation MUST use Haystack LLM generation + `PromptBuilder` (or equivalent).
- **FR-019a**: (Target) SuperComponents for recurring subgraphs.
- **FR-019b**: (Target) Tools with short unique name + NL description. **As-built (S7.1):** allowlisted in-process tools `decompose_project_needs`, `retrieve_fleet_assets`, `filter_fleet_candidates`, `check_booking_availability` (+ S6 `predict_asset_price`) via `app/agents/fleet_tools.py` + `tool_factory.py`. Free-form SQL/Cypher rejected. **As-built (S4):** `FLEET_BACKEND=sql` uses `LiveSqlFleetBackend` / `FleetRepository` (allowlisted ORM; `asset_id` = `assets.name`). Default remains `fake`. **As-built (S7.2):** `neo4j_cypher_read` (templates only) + `trigger_neo4j_populate` (non-blocking no-op) via `app/agents/neo4j_tools.py`; empty graph → `[]`; recommend not blocked (K-3 skip). **As-built (S7.3):** tools are invoked from the recommend LangGraph DAG. **As-built (S7.5):** Call 2 HTTP may run that DAG behind `RECOMMEND_VIA_AGENT_GRAPH`.
- **FR-019c**: Pipelines assembled with explicit `.add_component` / `.connect` / `.run`.
- **FR-019d**: (Target) File ingest branch by media type.
- **FR-019e**: (Target) Hybrid retrieval when catalog knowledge exists.
- **FR-019f**: Independent branches structured for concurrent execution; prefer `AsyncPipeline` when beneficial.

#### Scenario: Custom component standalone
- **WHEN** a domain component is unit-tested
- **THEN** it runs standalone (`warm_up` optional) without full graph

#### Scenario: Empty candidates
- **GIVEN** empty candidates (Scenario C)
- **WHEN** filter/rank run
- **THEN** predictable empty outputs without raising

#### Scenario: Allowlisted fleet tools (S7.1 as-built)
- **GIVEN** a recommend tool catalog from `build_recommend_tool_catalog(backend="fake")`
- **WHEN** an unknown tool name is requested
- **THEN** the factory rejects it (no free-form SQL mega-tool)

### Requirement: Recommend agent state partitions (S7.0 as-built)

The multi-agent recommend path SHALL use a shared `RecommendAgentState` (STM) with role-partitioned writes. Fleet Workers write only `fleet_by_need[need_id]`; Pricing Workers write only `prices_by_need[need_id]` for known candidate `asset_id`s; Coordinators write `recommendation` without inventing `asset_id`s outside fleet candidates. `run.indexing_ok == false` MUST block fleet (and pricing) partition writes. Illegal transitions raise a hard error (no partial corrupt write). Runtime: `app/agents/recommend_state.py` (`validate_state_transition`, `apply_partition_write`). LangGraph DAG wiring is **as-built S7.3** (`app/agents/recommend_graph.py`).

**Status:** **as-built (S7.0)**.

#### Scenario: Fleet Worker cannot write recommendation
- **WHEN** a fleet_worker proposes a `recommendation` partition write
- **THEN** validation rejects the transition

#### Scenario: Gate false blocks fleet write
- **GIVEN** `run.indexing_ok` is false
- **WHEN** a fleet_worker writes `fleet_by_need`
- **THEN** validation rejects the transition

#### Scenario: Unknown priced asset rejected
- **GIVEN** fleet candidates that do not include `AST-UNKNOWN`
- **WHEN** a pricing_worker writes a price for `AST-UNKNOWN`
- **THEN** validation rejects the transition

### Requirement: Recommend LangGraph DAG (S7.3 as-built)

The recommend path SHALL run an isolated LangGraph DAG (not the Stage-1 Q&A graph): `check_gate → project_worker [5] → delegator → execute_needs ([6]→[7]×N) → synthesis [8]`. Within a need, fleet MUST complete before pricing. Across needs, fan-out width is `RECOMMEND_FANOUT_CAP` (default 4, min 1): cap 1 serializes each need pipeline; cap ≥ 2 batches fleets then prices. `run.indexing_ok == false` MUST skip project/fleet/price tools and emit a gate warning. Workers MUST NOT spawn sibling needs. Runtime: `app/agents/recommend_graph.py`, `app/agents/recommend_nodes.py`. HTTP Call 2 may invoke this DAG (S7.5).

**Status:** **as-built (S7.3)**.

#### Scenario: Never price before fleet for the same need
- **GIVEN** two fixture needs and recording tools
- **WHEN** `run_recommend_graph` runs with `indexing_ok` true
- **THEN** for each `need_id` the first pricing worker start is after that need's fleet worker start

#### Scenario: Gate refuse blocks fleet and price
- **GIVEN** `run.indexing_ok` is false
- **WHEN** the recommend graph runs
- **THEN** fleet and pricing tools are not called
- **AND** `results_by_need` is empty with a gate warning

### Requirement: Tool-free recommend synthesis (S7.4 as-built)

Coordinator synthesis [8] MUST be tool-free. It SHALL merge `fleet_by_need` + `prices_by_need` into `recommendation.results_by_need` (singular `item` per need). Empty fleet or missing tool-backed prices → `item: null` + warning. MUST NOT invent `asset_id` or write `daily_rate <= 0`. Output shape MUST validate before F-2 apply. Runtime: `app/agents/recommend_synthesis.py` (`synthesize_recommendation`). Stub mode is the CI default; rationale text comes from `app/agents/recommend_prompts.py` (`stub_recommend_rationale`). Optional LLM rationale (S7.7) may rewrite text only via `apply_rationale_only` — never `asset_id` or rates.

**Status:** **as-built (S7.4)**.

#### Scenario: Golden merge copies tool rates only
- **GIVEN** fixture candidates including `AST-SL-001` and a price row `daily_rate` 185
- **WHEN** stub synthesis runs
- **THEN** `results_by_need` contains `AST-SL-001` with `daily_rate` 185
- **AND** no `asset_id` appears that was not in fleet candidates

#### Scenario: Empty fleet yields null item
- **GIVEN** no fleet candidates for a need
- **WHEN** synthesis runs
- **THEN** `item` is null
- **AND** warnings mention no fleet match

### Requirement: Call 2 multi-agent enrich (S7.5 as-built)

`POST /internal/v1/recommendations/project-knowledge/getassetrecommendations` SHALL keep the as-built quote DTO (`quoteRef`, `items[]`). When `RECOMMEND_VIA_AGENT_GRAPH` is **false** (default), Call 2 uses `RecommendationService` MVP. When **true**, `SessionRecommendService` SHALL run `run_recommend_graph` and map `results_by_need` onto the same quote. A registered session implies `indexing_ok=true` unless `session.meta.indexing_ok` is false. Gate refuse MUST return **400** shared error JSON. Missing session remains **404**. MUST NOT invent `equipment.id` or rates. MUST NOT put `tool_traces` or Q&A `answer` on the quote body.

**Status:** **as-built (S7.5)**. Runtime: `app/services/session_recommend.py`. Config: `RECOMMEND_VIA_AGENT_GRAPH`.

#### Scenario: Flag on returns quote shape
- **GIVEN** a Call 1 session and `RECOMMEND_VIA_AGENT_GRAPH=true`
- **WHEN** POST `getassetrecommendations`
- **THEN** response is 200 with `quoteRef` and `items[]`
- **AND** the body has no `answer` and no `tool_traces`

#### Scenario: Flag off uses MVP
- **GIVEN** `RECOMMEND_VIA_AGENT_GRAPH=false`
- **WHEN** Call 2 recommend runs
- **THEN** `run_recommend_graph` is not invoked

#### Scenario: Gate refuse is 400
- **GIVEN** a session with `meta.indexing_ok=false` and the graph flag on
- **WHEN** POST `getassetrecommendations`
- **THEN** response is **400** `{"error","message"}`

### Requirement: Recommend tool_traces (S7.6 as-built)

Recommend-graph `tool_traces` SHALL record `role` (`coordinator` \| `delegator` \| `worker`), `node`, and `status`. Fan-out fleet/pricing events MUST include `need_id`. Terminal statuses (`ok`, `completed`, `error`, `refused`) MUST include `duration_ms >= 0`. Empty fleet still emits a fleet-worker span and a synthesis warning. Traces are STM/audit only — not part of the Call 2 quote DTO.

**Status:** **as-built (S7.6)**. Runtime: `app/agents/recommend_traces.py`.

#### Scenario: Fan-out traces carry need_id and duration
- **GIVEN** two fixture needs and `indexing_ok` true
- **WHEN** `run_recommend_graph` completes
- **THEN** fleet and pricing traces include `need_id`
- **AND** terminal spans include `duration_ms >= 0`

### Requirement: Recommend prompts A–L + tool DI (S7.7 as-built)

Recommend-mode agents SHALL use isolated A–L prompt contracts in `app/agents/recommend_prompts.py` (`RECOMMEND_SYNTHESIS_*`, `DELEGATOR_POLICY_*`, `PROJECT_WORKER_*`, `FLEET_WORKER_*`, `PRICING_WORKER_*`). Stage-1 Q&A prompts in `app/agents/prompts.py` MUST remain uncontaminated (still forbid invent fleet; MUST NOT name fleet/pricing tools). Coordinator synthesis prompt MUST declare **Tools: none**. Tool DI SHALL inject catalogs via `build_recommend_runtime` / `build_recommend_tool_catalog`. Delegator `worker_kind` MUST be allowlisted (`fleet_worker` \| `pricing_worker`); unknown kinds raise `UnknownWorkerKindError` and MUST NOT be scheduled. `PROJECT_AGENT_MODE=stub` MUST stay deterministic (golden `asset_id` / rates / rationale).

**Status:** **as-built (S7.7)**. Runtime: `recommend_prompts.py`, `tool_factory.py` (`ALLOWED_WORKER_KINDS`, `validate_work_plan`). Tests: `tests/test_recommend_prompts.py`, `tests/test_agent_tool_di.py`. OpenSPDD index: `openspec/spdd/prompts/recommend-agents.md`.

#### Scenario: Q&A prompts still forbid invent fleet
- **GIVEN** Stage-1 `SYNTHESIS_AGENT_SYSTEM` / `RESEARCH_AGENT_SYSTEM`
- **WHEN** the prompt contracts are inspected
- **THEN** they still forbid inventing fleet inventory, rates, or bookings
- **AND** they do not mention `retrieve_fleet_assets` or `predict_asset_price`

#### Scenario: Recommend synthesis prompt has no tools
- **GIVEN** `RECOMMEND_SYNTHESIS_SYSTEM`
- **WHEN** the prompt contract is inspected
- **THEN** it declares tools: none
- **AND** it forbids inventing `asset_id` / `daily_rate`

#### Scenario: Delegator rejects unknown worker_kind
- **GIVEN** a work_plan item with `worker_kind="invent_stock"`
- **WHEN** `validate_work_plan` or `execute_needs` runs
- **THEN** `UnknownWorkerKindError` is raised and the item is not scheduled

### Requirement: Live SQL fleet backend (S4 as-built)

When `FLEET_BACKEND=sql`, recommend fleet tools SHALL read Postgres-Haystack via allowlisted SQLAlchemy selects (`app/repositories/fleet_repository.py`). `asset_id` MUST be `assets.name` (UNIQUE) — MUST NOT invent ids. Bookings SHALL join `booking_items` and count only live-hold statuses (`PENDING_DEPOSIT`, `PENDING_CONFIRMED`, `CONFIRMED`, `MOBILISED`). Empty / unknown category / blank name → skip or `[]`. `FLEET_BACKEND=fake` (default) MUST keep seed/injected DTOs so unmarked CI needs no Postgres. Free-form SQL kwargs remain rejected. Config-repo T0–T2 sync is out of this requirement. D0 map: [`../spring-entity-repository/fleet-read-contract.md`](../spring-entity-repository/fleet-read-contract.md).

**Status:** **as-built (S4 app)**. Tests: `tests/test_fleet_repository.py`.

#### Scenario: Asset.name is asset_id
- **GIVEN** a mirror row with `assets.name=AST-SL-001` and category `Scissors Lift`
- **WHEN** `list_assets` runs
- **THEN** the DTO `asset_id` is `AST-SL-001` and `category` is `scissor lift`

#### Scenario: Empty mirror
- **GIVEN** no fleet rows
- **WHEN** retrieve / list_bookings run
- **THEN** results are `[]`

#### Scenario: Default CI stays fake
- **GIVEN** unset / `fake` `FLEET_BACKEND`
- **WHEN** the recommend catalog is built
- **THEN** the backend is the seed fake, not a live session

### Requirement: Neo4j KG-2 tools (S7.2 as-built)

Recommend-mode SHALL expose allowlisted in-process KG-2 tools `neo4j_cypher_read` and `trigger_neo4j_populate` via `app/agents/neo4j_tools.py` + `tool_factory.py`. `neo4j_cypher_read` MUST accept only named templates (`asset_neighbors`, `assets_by_category`, `compatible_attachments`) and MUST reject free-form `cypher` / `query` / `raw_cypher` / `sql`. An empty backend MUST return `[]`. `trigger_neo4j_populate` MUST return a `job_id` immediately with `blocking=false` and MUST NOT run on the recommend hot path. Delegator K-3: when the Neo4j backend is empty/unavailable, fleet `tool_allowlist` MUST omit `neo4j_cypher_read` and record `skip_tools`; required SQL fleet tools MUST still run. Recommend MUST NOT invent `asset_id` from graph neighbors. Live Neo4j populate remains **S8**. Default CI uses `FakeNeo4jBackend` (no `neo4j` package).

**Status:** **as-built (S7.2)**. Runtime: `neo4j_tools.py`. Tests: `tests/test_neo4j_tools.py`.

#### Scenario: Empty graph returns empty list
- **GIVEN** a `FakeNeo4jBackend` with no nodes
- **WHEN** `neo4j_cypher_read` runs `asset_neighbors`
- **THEN** the result is `[]`

#### Scenario: Free-form Cypher is rejected
- **WHEN** `neo4j_cypher_read` is called with `cypher` / `query` / `raw_cypher`
- **THEN** `FreeFormCypherRejected` is raised

#### Scenario: Populate trigger is non-blocking
- **WHEN** `trigger_neo4j_populate` runs
- **THEN** a `job_id` is returned immediately
- **AND** `blocking` is false

#### Scenario: Recommend is not blocked when Neo4j is empty
- **GIVEN** the default fake catalog (empty graph)
- **WHEN** `run_recommend_graph` runs with `indexing_ok` true
- **THEN** fleet SQL tools still run
- **AND** `neo4j_cypher_read` is skipped
- **AND** `results_by_need` is still produced

### Requirement: Pricing integration (FR-020–FR-024)

- **FR-020**: Obtain prices by calling **`predict_price()`**—not a hand-written local stub once experimental exists. **As-built:** production path is `pricing_client.predict_price_for_asset` → `app.services.pricing.model.predict_price`.
- **FR-021**: Prototype: import from `ml_experiments/`. **Superseded (Phase 2b):** experimental loader removed; `ml-experiments/` remains offline scratch only.
- **FR-022**: Production swap: single import site (`pricing_client`). **As-built.** Agent tool **`predict_asset_price`** (S6 / US-5) MUST use the same entrypoint — no second prediction path.
- **FR-023**: Pricing payload SHOULD expose rates/currency/explanation (and model identity when available).
- **FR-024**: Deposit guidance default **30%** unless policy overrides.

#### Scenario: Production pricing single source of truth
- **WHEN** the service recommend path and the agent tool `predict_asset_price` price the same asset/window
- **THEN** both go through `pricing_client` / production `predict_price` and agree on rate and `model_version`

### Requirement: ML training tool (FR-030–FR-035) — TARGET

- **FR-030**: Tool e.g. `trigger_pricing_model_training` MAY enqueue training and return `job_id` immediately.
- **FR-031**: Training: load dataset → feature engineering → fit (default **XGBoost**) → persist artifact + metadata → atomic current-model pointer.
- **FR-032**: Training asynchronous relative to triggering HTTP request.
- **FR-033**: `GET /api/v1/ml/jobs/{job_id}` → `queued` \| `running` \| `succeeded` \| `failed`.
- **FR-034**: `POST /api/v1/ml/train` for operator trigger without agent.
- **FR-035**: Agent MUST NOT retrain on every recommendation by default (`options.allow_retrain` default `false`, or operator-only).

#### Scenario: Train returns job_id
- **WHEN** `POST /api/v1/ml/train` is accepted
- **THEN** response is **202** + `job_id` without blocking recommend path

### Requirement: API & errors (FR-040–FR-043)

- **FR-040**: Public project-spec endpoint is `POST /internal/v1/recommendations/submitprojectspecification` (JSON and/or multipart).
  - **Target / product intent:** recommend envelope (`recommendation_id`, `results_by_need`, singular `item`) per this SPEC and child intake.
  - **As-built override (2026-08-07):** the route currently runs the **indexing** pipeline and returns `IngestFromProjectSpecResponse`. Normative live contract: [`../indexing/spec.md`](../indexing/spec.md). Recommend response remains **target / reattach**; FR-010 service path: [`../recommendation-pipeline/spec.md`](../recommendation-pipeline/spec.md).
- **FR-041**: Optional pricing-only endpoint remains allowed if pricing team does not expose an equivalent.
- **FR-042**: Errors use shared shape `{"error": "<code>", "message": "<human-readable>"}`.
- **FR-043**: Validation → `400`; missing → `404`; training conflict (target) → `409`; unhandled → `500`.

#### Scenario: Live path is ingest
- **WHEN** live `POST .../submitprojectspecification` succeeds
- **THEN** response is ingest-shaped (indexing), not deferred recommend envelope

### Requirement: Observability & config (FR-050–FR-053)

- **FR-050**: Log `request_id`, pricing model identity when known, latency; training `job_id` when applicable.
- **FR-051**: Bedrock / LLM credentials, model paths, feature flags via environment only; `.env.example` when implemented.
- **FR-052**: Heavy components SHOULD `warm_up()` before serving traffic in long-lived process.
- **FR-053**: Pipeline graphs SHOULD be inspectable via `.draw()` in development.

---

## Non-functional requirements

| ID | Requirement |
|----|-------------|
| **NFR-001** | Recommendation path (without training) SHOULD complete within reasonable interactive bounds; document Bedrock/LLM latency risk; consider streaming later. |
| **NFR-002** | (Target) Training MUST NOT block Uvicorn workers indefinitely. |
| **NFR-003** | No secrets in code; provider keys via env or secrets manager only. |
| **NFR-004** | Layering: routers → services → pipelines/components/repositories; no graph/SQL in routers. |
| **NFR-005** | Snake_case JSON for request/response bodies. |
| **NFR-006** | Day 1 exit: Scenario A runs end-to-end with honest rationale before Day 2 SPEC lock. |
| **NFR-007** | Prefer **pipeline-first** validation: deterministic components testable without an agent loop. |
| **NFR-008** | Production serve path SHOULD use async-capable ASGI so LLM I/O does not block workers. **As-built:** async routes offload sync service via `run_in_threadpool`. Full async decomposer / shared lifespan-warmed client remains a follow-up before high-volume `NEED_DECOMPOSER=llm`. |
| **NFR-009** | Containerized deploys SHOULD be configurable solely via environment/settings; no secrets in image layers. |

---

## API contract (normative sketch)

Exact path and field names finalized on Day 2 with intake scaffold; working contract:

### Recommend from project specification (MVP target)

`POST /internal/v1/recommendations/submitprojectspecification`  
JSON (`project_text`) or multipart (`file` ± `project_text`). Full field tables: [`../recommendation-intake/spec.md`](../recommendation-intake/spec.md).

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

**Example response 200** (quantity 2 → two unit-needs; **exactly one `item` per unit-need**)

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

Public structured `POST .../from-needs` with client-posted `needs[]` is **not** the MVP contract.

### Trigger training (target)

`POST /api/v1/ml/train` → `202` + `job_id`  
`GET /api/v1/ml/jobs/{job_id}` → status + metrics

---

## Domain constraints (product alignment)

- Approved types: **Boom Lift, Scissors Lift, Fork Lift, Excavator**.
- Shared rental window when dates supplied.
- Deposit guidance default **30%**; currency default **SGD**.
- Availability truth from fleet bookings data; this service recommends and filters, does not own bookings.
- Rationale MUST acknowledge **schema gaps** (e.g. terrain, operator-required) with team-agreed phrasing before Day 4 prompt lock.
- **Quantity** exists only on **internal** decomposed needs; expand to unit-needs. **`RecommendationItem` has no quantity.**
- **Exactly one** ranked recommendation per unit-need (`item`), not a list of alternatives.

---

## Demo scenarios (normative for acceptance)

| Scenario | Intent | Build notes |
|----------|--------|-------------|
| **A** | Happy path — matches with honest rationale | Day 1 exit condition; primary live demo |
| **B** | Second clean path (alternate need / partial inference) | Full-day Day 1 + Day 5; live demo with A |
| **C** | No match / empty availability | Requires seeded overlapping bookings; Q&A back pocket |

Day 6 rehearsal: run **A + B** live; keep **C** for questions.

---

## Data, models, and Haystack data types

| Concern | Guidance |
|---------|----------|
| Assets | Real `Asset` schema for SQL filter (Day 3); Day 1 may use small seed |
| Bookings | `Booking` / `BookingItem` overlap for availability |
| Pricing model | Owned by pricing team; recommendation only **calls** `predict_price()` |
| Training artifacts | Pricing workstream; training tool section is target integration |
| Algorithm default (training) | XGBoost (+ joblib) already in stack |
| Haystack **Document** / **ByteStream** | Use when indexing catalog text or ingesting uploaded project files (target) |
| DocumentStore | Choose per environment (in-memory for prototype; production-grade when retrieval added) |
| **Knowledge graph** | Ragas `KnowledgeGraph` (nodes/edges); offline from catalog + historical project text; optional JSON snapshot |

### Knowledge graph (target + as-built pointer)

**As-built (HR-76 + Stage 1 multi-agent):** **Mandatory** user-scoped KG-1 after project-spec **indexing** (`final_doc_joiner` chunks); JSON artifact + in-memory session; LangGraph Q&A over project DocumentStore + KG-1. Normative child: [`../knowledge-graph/spec.md`](../knowledge-graph/spec.md). Live ingest HTTP: [`../indexing/spec.md`](../indexing/spec.md) (`user_id` required). Map: [`../../AGENTS.md`](../../AGENTS.md).

**Target:** broader offline catalog/historical-project **KG-2**, multi-hop for ranking/eval, equipment tools — not a substitute for Asset SQL / availability / `predict_price` on the recommend path.

The KG does **not** replace Asset SQL, Booking availability, or `predict_price()`. Online recommendation remains: needs → candidates → availability → price → rank.

Architecture, Ragas pattern, deps, and offline pipeline sketch: [`design.md`](./design.md).

---

## Acceptance criteria (GIVEN / WHEN / THEN)

1. **Given** Day 1 prototype setup, **when** Scenario A is run from a script/test against `app/pipelines/`, **then** end-to-end completes with rationale that states assumptions and includes a refinement suggestion where applicable.
2. **Given** free-text that decomposes into multiple unit-needs (or quantity expansion), **when** results are returned, **then** each unit-need has an independent entry with singular **`item`** (no cross-need merge; no multi-rank `items[]`).
2a. **Given** a decomposed need with `quantity = 2`, **when** expansion and ranking run, **then** two unit-need rows are returned and neither `RecommendationItem` carries a `quantity` field.
3. **Given** dates and seeded overlapping bookings, **when** Scenario C is exercised, **then** the no-match path sets `item: null` (with warnings) against real (or seed) availability data.
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
13. **(Target KG)** **Given** KG dependencies are not installed, **when** only MVP recommendation runs, **then** the service still operates (KG optional for recommend import path; as-built indexing path requires KG separately).
14. **(Deployment)** **Given** the FastAPI app is started for serving, **when** the first recommend request uses a warmed generator/embedder path, **then** heavy model load was performed at lifespan/startup (`warm_up`), not re-initialized on every request.
15. **(Deployment / target)** **Given** a container image of the app, **when** run with required env vars, **then** `/health` succeeds and recommend config is read from environment rather than baked-in secrets.

---

## Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Spec timing | Day 2 after Day 1 pipeline proof | Spec written against proven shape, not hope |
| Framework stance | **Pipeline-first Haystack**; LangGraph for stateful agent later | Chapter 3 hybrid architecture |
| Pipeline API | `Pipeline` / `AsyncPipeline` + `add_component` / `connect` / `run` / `draw` | Chapter 4 directed multigraph construction |
| Retrieval (target) | Hybrid BM25 + dense → join → rerank | Better precision than naive dense-only |
| File ingest (target) | Router-based branching by type | Chapter 4 indexing pattern (as-built: indexing capability) |
| Prototype location | `app/pipelines/`, no public route Day 1 | Masterplan / execution plan |
| Pricing call | `ml_experiments.predict_price` → `app.services.pricing.predict_price` | Avoid local stub; non-blocking if production slips |
| Ranking | Haystack `PromptBuilder` + `Generator` (Bedrock); as-built template rank for CI | Inspectable prompts; CI without Bedrock |
| Custom domain steps | Custom `@component` with Ch. 5 life cycle | Extensibility; testable standalone |
| Knowledge graph library | **Ragas** `KnowledgeGraph` + transforms | Book component; multi-hop + synthetic tests |
| KG storage (v1 target) | In-memory build + **JSON** artifact; no Neo4j by default | Simpler ops |
| KG in 6-day demo | **Out of critical path** for recommend | Demo uses SQL + availability + price + rank |
| Primary deploy | **FastAPI app** (Ch. 7 Method 1) | Project stack |
| Hayhooks / MCP | Optional | Not second source of truth for fleet/price |
| Intake UX | Free-text box and/or file; LLM decomposes | Not structured multi-need form |
| Quantity | Expand to unit-needs; no qty on RecommendationItem | Item rows = units requested |
| One item per need | Singular `item` (not top-N `items[]`) | Clear portal binding |
| Multi unit-need | Independent per unit-need loop | Prevents merged answers |
| Haystack Agent vs LangGraph | LangGraph preferred when state grows | Context opacity of Haystack agent loop |
| Training tool | Post–6-day / pricing-owned | Keeps demo focused |
| Catalog | Hard filter to 4 SG types | Portal product |
| Auth | Deferred | Constitution |
| Live HTTP (2026-08-07) | Indexing + mandatory KG | Recommend envelope deferred reattach |

---

## Open questions

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
| 10 | Prefer `AsyncPipeline` in MVP for availability∥pricing, or keep serial until measured latency pain? | Day 3–5; document here |
| 11 | KG LLM/embedder: same Bedrock stack as ranking, or separate OpenAI/Ollama as in Ch.5 samples? | Before first KG batch job |
| 12 | Persist KG only as JSON artifacts, or also promote triples into DocumentStore/hybrid index? | Before online use of graph signals |
| 13 | Is Neo4j (or other graph DB) ever required, or is Ragas in-memory + JSON enough for v1 target? | Default: **no Neo4j** until a dedicated SDD |
| 14 | Dockerize only the FastAPI monolith, or also a Hayhooks sidecar for rank-only MCP tools? | Post-demo; default: monolith first |
| 15 | Auth for recommend routes: API key, interim portal JWT, or network policy only until shared auth SDD? | When leaving open-dev posture |

---

## Change control

| Version | Date | Notes |
|---------|------|--------|
| 0.1.0 | 2026-08-04 | Initial draft: agentic recommendation, pricing recommender, tool-triggered ML training |
| 0.2.0 | 2026-08-05 | 6-day schedule, predict_price path, Scenarios A/B/C, Jira branches |
| 0.3.0–0.5.0 | 2026-08-05 | Haystack Ch. 3–5 incorporation |
| 0.6.0–0.6.1 | 2026-08-05 | Knowledge Graph target (Ragas) |
| 0.7.0 | 2026-08-05 | Chapter 7 deployment |
| 0.8.0 | 2026-08-05 | Intake correction: free-text/file + singular item |
| 0.9.0 | 2026-08-06 | Pricing `daily_rate` + `total_price`; threadpool offload notes |
| 0.9.1 | 2026-08-07 | As-built override FR-040: public path is indexing ingest |
| 0.9.2 | 2026-08-07 | KG as-built pointer; sequential map |
| 1.0.0 | 2026-08-10 | Migrated to OpenSpec under `openspec/specs/equipment-recommendation/`; architecture/day plan/deployment → design.md |
| 1.1.0 | 2026-08-12 | **S7.0 + S7.1 as-built:** `RecommendAgentState` + F-2 partition validation; allowlisted fleet/needs tools + DI factory (FR-019b note). Graph (S7.3+) still TARGET. Archives `changes/archive/2026-08-12-s7-0-recommend-agent-state/`, `.../s7-1-fleet-tool-catalog/`. |
| 1.6.0 | 2026-08-13 | **S4 as-built (app):** live SQL fleet backend (`FLEET_BACKEND=sql`); D0 `fleet-read-contract.md`. Config T0–T2 remain config-repo. Archive `changes/archive/2026-08-13-s4-live-sql-fleet-backend/`. |
| 1.5.0 | 2026-08-13 | **S7.2 as-built:** `neo4j_cypher_read` (templates only) + `trigger_neo4j_populate` (non-blocking no-op); K-3 skip when graph empty. Live populate remains S8. Archive `changes/archive/2026-08-13-s7-2-neo4j-tools/`. |
| 1.4.0 | 2026-08-13 | **S7.7 as-built:** isolated A–L recommend prompts + tool DI runtime + Delegator `worker_kind` allowlist. Archive `changes/archive/2026-08-13-s7-7-prompts-a-l-tool-di/`. |
| 1.3.0 | 2026-08-12 | **S7.5 + S7.6 as-built:** Call 2 graph enrich behind `RECOMMEND_VIA_AGENT_GRAPH` (same quote DTO; gate 400); G-1 `tool_traces` duration contract. Archive `changes/archive/2026-08-12-s7-5-s7-6-call2-enrich-traces/`. |
| 1.2.0 | 2026-08-12 | **S7.3 + S7.4 as-built:** recommend LangGraph DAG (gate → [5] → Delegator → ([6]→[7])×N) + tool-free stub synthesis [8]. HTTP Call 2 still service MVP (S7.5). Archive `changes/archive/2026-08-12-s7-3-s7-4-recommend-graph-synthesis/`. |

When behaviour, API paths, tool names, or schedule gates change, bump this table and align OpenAPI / tests / execution plan in the same change set.

**Reading order:** [`../../AGENTS.md`](../../AGENTS.md) · [`design.md`](./design.md) · children: [indexing](../indexing/spec.md) · [KG](../knowledge-graph/spec.md) · [intake](../recommendation-intake/spec.md) · [pipeline](../recommendation-pipeline/spec.md) · [pricing](../dynamic-pricing/spec.md)
