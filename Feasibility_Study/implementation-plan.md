# Implementation Plan: Feasibility Study Rollout

| Field | Value |
|-------|--------|
| **Document type** | Implementation plan (derived from feasibility studies) |
| **Status** | Plan only — **not** runtime source of truth |
| **Date** | 2026-08-12 |
| **Version** | 3.8.0 |
| **Source studies** | All documents in this folder (feasibility studies + this plan; all GO with phased constraints) |
| **Repo** | `haystack-fast-api` (app) + related config/Spring repos where noted |
| **Revision notes** | **3.8.0** Phase 7 / **S7.5 + S7.6 as-built** (Call 2 graph enrich behind flag + `tool_traces` duration contract); **3.7.0** S7.3 + S7.4 as-built; **3.6.0** S7.0 + S7.1; **3.5.6** S6; **3.5.5** S5-I1; **3.5.4** S5-I0; **3.5.3** pytest isolation; **3.5.2** S3; **3.5.1** Call 2/3 renumber; **3.5.0** Call 2 recommend HTTP MVP; **3.4.x** portal dual-hop; **3.0.0** stage catalog |

Related studies: [`README.md`](./README.md) · normative product behaviour: [`../openspec/`](../openspec/)

---

## 1. Assessment summary

### 1.1 What the studies decide (combined)

| Study | Verdict | Priority for shipping value |
|-------|---------|------------------------------|
| **Call 1 project-spec summary** | GO lean body + full FR-IX-023 needs/dates/budget **as-built** (S1a–S1e / Phase 1.7) | **High** — client-facing, small surface |
| **Spring ↔ FastAPI resilience** | REST default; SSE not for upload; C1 then C2 jobs | **High** for production multi-call |
| **Postgres–Haystack–Neo4j dual plane** | Viable dual-track; poll ETL first; Neo4j projection async | **High** for production recommend accuracy |
| **Indexing → SuperComponent** | GO, optional packaging; no KG inside SC; packaging for **Coordinator gate [4]** | **Low** — refactor, not product path |
| **ML pricing multi-agent** | GO in-process `predict_asset_price`; not public HTTP; **Worker [7] fan-out per need** | **Medium** — after fleet candidates exist |
| **Multi-agent synthesis → assets + prices** | GO as tool-free **Coordinator** merge node; Stage-1 Q&A stays separate | **Medium–High** — enrich **Call 2 recommend** (C/W/D) |
| **C/W/D role vocabulary** | GO as alias layer over Orchestrator; **§10 A–L templates** (incl. seq/par processing) | **Medium** — Phase 7 full agent contract |

**Hard architectural rules (do not violate):**

- Tools are **in-process** only (no FastMCP/MCP server).
- Indexing **[4]** is a **forced non-agent Coordinator gate** (not an LLM Worker); must succeed before recommend tools; files never go into LLM context as raw bytes.
- **Delegator** is an **explicit allowlisted router** / workflow optimizer — not free ReAct.
- Fleet / pricing recommend steps **fan-out Workers per need** ([6]×N / [7]×N): **must-seq** fleet→price within need; **may-par** across needs (capped).
- Synthesis **must not** invent `asset_id` or rates — only merge tool outputs (**Coordinator [8]**).
- Fleet LTM for agents: **`postgres_haystack` / `heavy_rental` synced from `postgres-primary`** (read mirror only).
- Logs / `tool_traces` SHOULD emit C/W/D **`role`** (+ **`need_id`**, duration on fan-out).
- Agent **Worker** ≠ ops **job worker** (202 jobs, Neo4j populate, Uvicorn).
- KG-1 (project) and KG-2 (fleet Neo4j) stay separate planes.
- Spring remains HTTP REST client; resilience lives mostly on Spring + job patterns.
- Phase 7 agent prompts follow C/W/D **A–L** contracts ([`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) §10).

### 1.2 As-built baseline (today)

API routes under **`/internal/v1/recommendations`** (Spring-facing internal API).

```text
Call 1: POST /internal/v1/recommendations/submitprojectspecification
  → default: IndexingIngestService → InMemoryDocumentStore + mandatory KG-1 + session
  → optional S3 (INDEXING_VIA_AGENT_GATE=true):
       START → index_gate → END (forced non-LLM Coordinator [4])
         → tool run_indexing_from_request → same IndexingIngestService
  → lean public body (shipping contract; same on both paths):
       ingest_id, user_id, user_requirement_summary, warnings[]
  → technical indexing/KG fields NOT on public body (still run internally)
  → FR-IX-023 Call 1 summary **as-built** (S1a–S1e)
  → FR-IX-026 optional agent gate **as-built S3** (default flag off; S3.3 SuperComponent deferred)

Call 2: POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
  → requires user_id + ingest_id from Call 1 (+ optional query)
  → **RECOMMEND / quote** via SessionRecommendService → RecommendationService MVP
  → optional S7.5: RECOMMEND_VIA_AGENT_GRAPH=true → run_recommend_graph (same DTO)
  → quoteRef, items[].equipment, rates (no invent)
  → portal dual-hop primary body for React

Call 3: POST /internal/v1/recommendations/project-knowledge/query
  → chatbot Q&A: LangGraph research → graph → synthesis
  → tools: project_vector_search, project_kg_query
  → optional follow-ups after submit (not required for portal project-spec UX)

Full multi-agent C/W/D recommend graph remains future enrichment behind Call 2 DTO

DocumentStore: InMemory per-ingest session (default)
  S5-I0 as-built: INDEXING_DOCUMENT_STORE + build_document_store()
  S5-I1 as-built: create_session_document_store wire + tenant filters + TTL
    (memory default | pgvector flag; I2 production default TARGET)
Fleet: seed in app; D1 merge-sync in devcontainer config
  (postgres_haystack_sync, ~60s poll on develop)
Neo4j: compose service may exist; no populate-from-db job; no agent Neo4j tools
Pricing: pricing_client → app.services.pricing.model.predict_price (production)
  Phase 1e (repository util/lead-time + adapter wiring) — **as-built**
  Phase 2a (app/services/pricing/ + per-asset clamp) — **as-built**
  Phase 2b pipeline wire + Phase 2c internal quote API — **as-built**
  predict_asset_price agent tool (S6) — **as-built** (same entrypoint; Phase 7 Workers [7]×N as-built S7.3)
  RecommendAgentState + F-2 partition validation (S7.0) — **as-built**
  Fleet/needs tool catalog + DI factory (S7.1) — **as-built** (fake default; SQL DTO backend)
  Phase 7 graph + stub synthesis (S7.3–S7.4) — **as-built**
  HTTP Call 2 multi-agent enrich (S7.5) — **as-built** (`RECOMMEND_VIA_AGENT_GRAPH`, default off)
  tool_traces duration contract (S7.6) — **as-built**
  Neo4j tools / prompts A–L (S7.2, S7.7) — **not wired**
Error JSON: {"error","message"} handlers already as-built
Idempotency-Key / ingest correlation headers — **as-built S2a** (process-local store + middleware)
Agent indexing tool + Coordinator gate [4] — **as-built S3** (flag default off)

Default pytest (as-built):
  uv run pytest / uv run pytest tests/ -q
  → no optional markers / skip-if-service patterns in the suite
  → tests/conftest.py autouse forces:
       INDEXING_EMBEDDER=mock, INDEXING_EMBEDDING_DIM=384,
       INDEXING_DOCUMENT_STORE=memory, RECOMMEND_VIA_AGENT_GRAPH=false,
       PROJECT_AGENT_MODE=stub, KG_ARTIFACT_DIR=tmp
  → host .env (e.g. dim 768 for OpenAI) MUST NOT break CI
  → project_vector_search: query embedder mode/dim MUST match session store
  → planned @pytest.mark.pgvector|neo4j|integration remain TARGET (not registered)
```

**Call 1 → Call 2 handoff (minimum):** Spring stores `user_id` + `ingest_id` from Call 1; Call 2 recommend sends those (+ optional `query`). See **§1.2.1**.

### 1.2.0 Portal project-spec submit saga (Spring + React)

When the user **submits a project specification** from the React web portal, Spring runs **Call 1 then Call 2 recommend**, then returns **Call 2 quote** to the portal.

```text
React  POST /api/recommendations/project-spec
  → Spring
       → Call 1  POST /internal/v1/recommendations/submitprojectspecification
       → persist user_id + ingest_id
       → Call 2  POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
                 (user_id + ingest_id + optional query) → quote / items[]
  → React  primary response body = Call 2 recommend quote
  → optional Call 3 chatbot Q&A later: POST .../project-knowledge/query
```

| Rule | Detail |
|------|--------|
| Call 1 first | Required for index + KG + `ingest_id` |
| Call 2 second | **Recommend / quote** (required for portal submit UX) |
| Call 3 | **Chatbot Q&A** — optional follow-ups |
| Idempotency | `Idempotency-Key` on Call 1 only (S2a) |
| Call 2 fail | Do **not** re-run Call 1 (S2b saga) |
| No invent | Call 2 items/rates from catalog + pricing only |

Spring pack: [`../Feasibility_Study_Spring/portal-to-haystack-mapping.md`](../Feasibility_Study_Spring/portal-to-haystack-mapping.md).  
Contract: [`../openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md`](../openspec/specs/recommendation-pipeline/contracts/get-asset-recommendations.md).

### 1.2.1 Call 2 request contract — `getassetrecommendations` (**recommend**)

**Route:** `POST /internal/v1/recommendations/project-knowledge/getassetrecommendations`  
**Behaviour (as-built MVP):** Session-backed **equipment recommend / quote** via `RecommendationService` (seed fleet + pricing). Response: `quoteRef`, `items[].equipment`, rates, `estimatedTotal`, etc.  
**Not chatbot Q&A** — that is Call 3 `.../project-knowledge/query`.

#### As-built request body

| Field | Required | Notes |
|-------|----------|--------|
| `user_id` | **yes** | Same as Call 1 |
| `ingest_id` | **yes** | From Call 1 lean response — session key |
| `query` | no | Optional focus / predefined prompt |
| `top_k` | no | Cap on returned items |

```json
{
  "user_id": "user_demo",
  "ingest_id": "ing_a1b2c3d4e5f6",
  "query": "What excavator capacity and soil conditions are specified?"
}
```

#### Is `query` necessary on Call 2?

| Answer | When |
|--------|------|
| **Optional (as-built recommend)** | Call 2 recommend uses session text/needs; `query` is optional focus |
| **Required on Call 3** | Chatbot Q&A needs a question string |

Call 1 `user_requirement_summary` may inform Call 2 grounding via session meta and optional Call 3 prompts.

### 1.3 Target multi-call journey

```text
React portal project-spec submit:
  POST /api/recommendations/project-spec
    → Spring saga (as-built hops):
         Call 1  ingest [1–4]     → lean FR-IX-023 body
         Call 2  recommend        → getassetrecommendations quote / items[]
                                    → primary body to React
    → optional Call 3 chatbot Q&A → project-knowledge/query
    → future: richer C/W/D Workers behind same Call 2 DTO
```

### 1.4 Where work lives

| Concern | Repository / owner |
|---------|-------------------|
| Pipelines, agents, schemas, tools, Pgvector wiring | **haystack-fast-api** (this repo) |
| Compose, postgres_haystack_sync interval, neo4j-populate container, pgvector image | **heavy-rental-devcontainer-configuration** |
| Primary OLTP, outbox, Spring WebClient saga | **Spring / REST API** stack |
| Schema contract Asset/Booking enums | Shared contract (Spring + D0 doc) |

---

## 2. Independent testability principles

These rules apply to **every** phase so work can merge and stay green without waiting for the full stack.

| Principle | Practice |
|-----------|----------|
| **P1. Stub the next hop** | Any dependency on a later phase is replaced by a fake, seed, or in-memory substitute in that phase’s test suite. |
| **P2. Feature-flag production paths** | New paths default off or degrade gracefully so CI stays on as-built defaults. |
| **P3. Dual-mode CI** | Default job: no external Neo4j/Kafka/real primary; **as-built** suite is one unmarked job (`uv run pytest`) with conftest isolation (mock embedder + dim 384). Optional/nightly jobs (**TARGET**): Postgres+pgvector (and later Neo4j) via Testcontainers or compose — **markers not registered yet**. |
| **P4. Contract at boundaries** | Each phase publishes a stable interface (schema, tool signature, DTO, env flag). Later phases depend on the contract, not on private internals. |
| **P5. Golden fixtures** | Prefer fixed JSON fixtures (needs, tool hits, prices) over live LLM/model nondeterminism. |
| **P6. Phase exit = automated gate** | A phase is “done” only when its **Independent test pack** is green without requiring unfinished later phases. |
| **P7. Regression isolation** | Existing suites (indexing, KG, Stage-1 Q&A, health) must remain green after every phase merge. |
| **P8. Per-stage test implementation** | Every **stage ID** (S0–S9 / S7.0–S7.7) that ships code **must** list concrete test cases, suggested modules, fixtures/stubs, and CI job. No stage merges without its pack. |
| **P9. TDD for units** | New production behavior lands only after a **failing automated test** (red → green → refactor). Prefer fast, deterministic tests (stubs, golden fixtures)—not live LLM as the merge gate. |
| **P10. BDD for behaviors** | Stage acceptance is specified in **domain language** as **Given / When / Then** (from OpenSpec FRs, Call 1–3 journey, C/W/D hard rules) before or with implementation. |

**What “independently testable” means here:**  
You can open a PR for that phase alone, run its tests in CI (or the phase’s documented harness), and prove the exit criteria **without** implementing later phases. Runtime *product* value may still need later phases (e.g. recommend without real fleet is less accurate), but **verification** does not.

---

### 2.1 Test-Driven Development (TDD)

TDD is the **default implementation process** for every code-bearing stage (S1–S9, S7.0–S7.7). Exception: pure docs (S0) may use checklists only.

#### Cycle (per unit of work)

```text
1. RED     Write a failing automated test that expresses one behavior
2. GREEN   Write the minimum production code to pass
3. REFACTOR  Clean design; keep the suite green
4. Repeat  Next behavior / next stage test case
```

#### Rules

| Rule | Practice |
|------|----------|
| **Test first** | Do not merge production logic without a test that failed before the fix (or would fail if the logic were removed). |
| **One behavior per test** | Align with a single exit-criterion bullet or BDD scenario. |
| **Deterministic gates** | Default CI uses stubs, fixed fixtures, `PROJECT_AGENT_MODE=stub`—not flaky live LLM/network. |
| **Fast feedback** | Unit/contract tests in **default** job; heavy containers only on marked jobs. |
| **Regression stays green** | Refactor never breaks earlier stage packs (P7). |

#### Where TDD is mandatory

| Layer | Examples |
|-------|----------|
| **Unit** | Schema fields, pricing clamp, state partition validation (S7.0), tool allowlists |
| **Contract** | Tool I/O shapes, DTO golden files, HTTP status/body |
| **Graph order** | Must-seq fleet→price; gate refuse (S7.3)—drive with recording fakes |

#### Anti-patterns

- Implementing first, then writing tests only to match current code (“greenwash”).  
- Using live LLM/primary/Neo4j as the only proof of correctness in default CI.  
- One mega-test that asserts the entire product journey for a small PR.

---

### 2.2 Behavior-Driven Development (BDD)

BDD specifies **what the system should do** in language shared by product and eng, then binds those scenarios to automated tests (pytest, optional Gherkin later).

#### Scenario form

```text
Feature: <stage or product capability>
  Scenario: <exit criterion in plain language>
    Given <preconditions / fixtures / flags>
    When  <action: API call, graph run, tool invoke>
    Then  <observable outcome: status, DTO fields, traces, errors>
    And   <extra assertions / non-goals>
```

#### Sources of behavior (authoritative)

| Source | Use for scenarios |
|--------|-------------------|
| OpenSpec FRs / contracts | Call 1 summary, recommend DTO, pricing rules |
| Multi-call journey | Call 1 → 2 → 3 saga expectations |
| C/W/D hard rules | No invent assets/rates; gate [4]; fan-out; tool-free synthesis |
| Stage **Exit criteria** + **Test implementation** lists | Each numbered case → one scenario |

#### Mapping to this plan

| Plan artifact | BDD role |
|---------------|----------|
| Stage **Test implementation** bullets | Scenario outlines (expand to full G/W/T when coding) |
| Golden JSON under `tests/fixtures/` | `Then` expected payloads |
| Feature flags / stub mode | `Given` preconditions |
| Optional `tests/features/*.feature` | Gherkin if team adopts pytest-bdd; **not required** if G/W/T lives in test names/docstrings |

#### Where BDD is mandatory

| Layer | Examples |
|-------|----------|
| **API / HTTP** | S1 Call 1 summary; S7.5 Call 2 multi-agent enrich |
| **User-visible agent outcomes** | S7.4 empty fleet → `item: null` + warning; S7.3 gate fail → no fleet tools |
| **Resilience** | S2 double ingest same key → one `ingest_id` |
| **Isolation** | S5-I1 two users cannot read each other’s chunks |

Unit-heavy stages (S6 clamp math, S7.0 validation) still use TDD; phrase top-level acceptance as BDD when the behavior is product-facing.

#### Example scenarios (templates for implementers)

**S1 — Call 1 summary**

```text
Scenario: Lean Call 1 body after successful ingest
  Given a project-spec fixture with project_text describing a scissors lift need
  When  the client POSTs /internal/v1/recommendations/submitprojectspecification
  Then  the response includes ingest_id starting with ing_
  And   user_id echoes the request
  And   user_requirement_summary is non-empty and reflects the project_text
  And   the body does not expose documents[] or kg_* technical fields
```

**S7.4 — Recommend synthesis**

```text
Scenario: Synthesis merges tool-backed fleet and prices only
  Given fixture candidates for need_access including asset AST-SL-001
  And   fixture prices with daily_rate 185 for AST-SL-001
  When  the Coordinator synthesis node runs in stub mode
  Then  results_by_need contains AST-SL-001 with daily_rate 185
  And   no asset_id appears that was not in the fleet fixture
```

```text
Scenario: Empty fleet yields null item and warning
  Given no fleet candidates for need_earthwork
  When  synthesis runs
  Then  item is null for that need
  And   warnings mention no fleet match
```

---

### 2.3 Stage PR workflow (TDD + BDD combined)

For **every code-bearing stage PR**:

```text
1. BDD   Write Given/When/Then scenarios from stage exit criteria
         (docstring, feature file, or plan bullet expanded)
2. TDD   Encode scenarios as failing automated tests (red)
3. IMPL  Implement production code until green
4. REFACTOR  Clean up; suite stays green
5. REGRESSION  Full default CI for earlier stages still green
6. MERGE only when stage Test implementation pack is complete
```

```text
        BDD scenarios
             │
             ▼
        TDD tests (RED)
             │
             ▼
     implementation (GREEN)
             │
             ▼
         refactor
             │
             ▼
      stage pack + regression CI
```

---

## 3. Tracks and dependency graph

Reuse study track IDs so this plan stays aligned with the dual-plane study.

```text
Wave 0 — Foundation (this repo + light Spring)
  Call1 summary (S1–S5) ── parallel ── Resilience C1 (Spring)
  SuperComponent (optional, anytime after indexing stable)

Wave 1 — Data platform (config + Spring + this repo read models)
  D0 schema contract → D1 poll mirror (mostly done) → D2 near-RT → D3 Neo4j
  D4 pgvector platform ──► I0/I1 Indexing DocumentStore cutover

Wave 2 — Agent / recommend
  R1 agent wraps indexing ──► R2 Q&A (mostly as-built)
  R4 tool catalog (fleet, Neo4j, pricing)
  R5 recommend graph [5–8] + synthesis DTO  ≈ Call 2 (HTTP recommend)

Wave 3 — Production hardness
  Resilience C2 (202 jobs / SSE progress)
  Pricing Phase 1e + 2a
  I2 production default Pgvector + TTL
```

**Suggested first-ship order (practical):**

1. **Call 1 summary** (fast client win, this repo only)  
2. **R1** agent indexing tool behind flag (still InMemory OK)  
3. **D0–D1 / T0–T1** schema + near-real-time sync  
4. **I0–I1** Pgvector cutover  
5. **Pricing 1e/2a** + **R4 tools**  
6. **R5 / Call 2** recommend synthesis (HTTP; enrich MVP)  
7. **D3/T3 Neo4j** + Neo4j tools (can lag slightly behind SQL fleet tools)  
8. **C2** async jobs when latency/timeouts force it  

---

## 3.1 Stage catalog (implementable units)

Use **stage IDs** in PRs and test names. Every stage below that ships code has a **Test implementation** block in §4.

| Stage ID | Name | Phase | Repo | Depends on | Default CI? |
|----------|------|-------|------|------------|-------------|
| **S0** | Spec freeze & D0 schema contract | 0 | shared | — | checklist |
| **S1** | Call 1 lean body + FR-IX-023 increments (**S1a–S1e**) | 1 | app | — | **yes** |
| **S2a** | Resilience C1 — FastAPI (idempotency, errors, correlation) | 2 | app | — | **yes** |
| **S2b** | Resilience C1 — Spring client (timeouts, CB, saga) | 2 | Spring | WireMock | Spring CI |
| **S3** | Agent indexing tool R1 + Coordinator gate **[4]** | 3 | app | — | **yes** (**as-built**) |
| **S3.3** | Indexing SuperComponent (optional) | 3 | app | S3 | **yes** (deferred) |
| **S4** | Fleet sync T0–T2 (`postgres_haystack` ← primary) | 4 | config | S0/D0 | config CI |
| **S5-I0** | DocumentStore factory (memory default) | 5 | app | — | **yes** |
| **S5-I1** | Pgvector cutover + isolation | 5 | app+config | S5-I0 | optional job |
| **S6** | Pricing 2a + `predict_asset_price` tool (1e largely as-built) | 6 | app | fixtures OK | **yes** |
| **S7.0** | `RecommendAgentState` + partition validation | 7 | app | — | **yes** (**as-built**) |
| **S7.1** | Fleet/project tool catalog (in-process) | 7 | app | S7.0 interfaces | **yes** (**as-built**) |
| **S7.2** | Neo4j tools (no-op until S8) | 7 | app | S7.1 | **yes** (fake) |
| **S7.3** | Recommend LangGraph DAG (seq/par C/W/D) | 7 | app | S7.0–S7.1 | **yes** (**as-built**) |
| **S7.4** | Tool-free synthesis + F-2 validation | 7 | app | S7.3 | **yes** (**as-built**) |
| **S7.5** | HTTP Call 2 multi-agent enrich (same quote DTO) | 7 | app | S7.4 | **yes** (**as-built**) |
| **S7.6** | `tool_traces` / metrics (role, need_id, duration) | 7 | app | S7.3 | **yes** (**as-built**) |
| **S7.7** | Prompts A–L + tool DI factory | 7 | app | S7.3–7.4 | **yes** |
| **S8** | Neo4j populate + real graph tools | 8 | config+app | seed SQL | optional |
| **S9.1** | C2 202 jobs / SSE | 9 | app (+ Spring) | HTTP surface | **yes** (fake worker) |
| **S9.2–S9.5** | Object storage / I2 default / D2 / C3 | 9 | split | metrics-driven | per sub-item |

**Rule:** A stage is implementable when its **Test implementation** section lists cases, modules, stubs, and CI job.

---

## 4. Step-by-step implementation plan (with independent tests)

Each step is sized as a reviewable PR (or small PR stack). Every phase/stage has a **Test implementation** pack.

---

### Phase 0 — Spec freeze & parity (1–2 days)

| Step | Work | Owner | Exit criteria |
|------|------|-------|---------------|
| **0.1** | Confirm OpenSpec TARGET docs match feasibility (FR-IX-023, ingest contract, AGENTS.md flow) | App | Specs already updated; no code |
| **0.2** | Inventory Spring Asset/Booking/Category columns needed for recommend + pricing + graph (**D0**) | Shared | Short schema contract doc (tables, PKs, enums, lag-sensitive fields) |
| **0.3** | Decide open product knobs that block design: project chunk TTL, every-call-through-agent vs flag, Neo4j populate trigger mode | Product + eng | Written answers (can live in OpenSpec design) |

#### Test implementation — Stage S0

| Attribute | Detail |
|-----------|--------|
| **Independently testable?** | **Yes** (document review + optional static checks) |
| **Does not need** | App code, Postgres, Neo4j, Spring runtime |
| **Test implementation** | (1) Checklist: FR-IX-023 fields present in OpenSpec; (2) D0 table list includes Asset/Booking/Category (+ payments/rental_plan if used); (3) open questions ticketed or answered; (4) optional `lychee`/markdown link check on Feasibility_Study README |
| **Suggested artifacts** | `docs/` or shared `schema-contract.md`; PR checklist in PR template |
| **CI job** | optional docs CI |
| **Stubs for later phases** | Schema contract is what S4/S6/S7.1 implement against |

---

### Phase 1 — Call 1: lean public body + FR-IX-023 increments (this repo)

Maps to [`call1-ingest-response-project-summary.md`](./call1-ingest-response-project-summary.md) and OpenSpec **FR-IX-023**.

| Step | Work | Files (expected) | Exit criteria | Status |
|------|------|------------------|---------------|--------|
| **1.0** | Routes under `/internal/v1/recommendations` (`submitprojectspecification`, `getassetrecommendations`) | `app/api/…`, tests, Postman | OpenAPI shows internal paths | **Done** |
| **1.1 S1a** | Lean `IngestFromProjectSpecResponse`: `ingest_id`, `user_id`, `user_requirement_summary`, `warnings[]` | `app/schemas/indexing.py`, `IndexingIngestService` | 200 body is lean; index+KG still run for Call 2 | **Done** |
| **1.2 S1a** | Build `user_requirement_summary` from `project_text` or extracted multipart content (deterministic; truncate + warning) | service helper + unit tests | Keywords from fixture appear in summary | **Done** |
| **1.3 S1b** | Echo request `start_date`/`end_date` as `tentative_start_date` / `tentative_end_date` when present | service + API | Dates in response when supplied; null when omitted | **Done** |
| **1.4 S1c** | `needs_summary[]` via decomposer **after** successful index+KG only | service + stub decomposer | CI stub; LLM optional | **Done** |
| **1.5 S1d** | `expected_budget` extract: currency phrases only; **never invent** | extractor + tests | No hallucinated budgets | **Done** |
| **1.6 S1e** | **FR-IX-023 free-text date extract:** when request omits dates, extract rental window from project text / extracted file content when confident; **request dates still preferred**; else null + warning; **never invent** | extractor + API fixtures | Text/file with clear dates fills `tentative_*` without request dates; request overrides extract | **Done** |
| **1.7** | Converge FR-IX-023: full tests + Postman; **mark FR-IX-023 as-built** in OpenSpec when **S1c + S1d + S1e** are green | tests, postman, openspec | Full Call 1 project-spec summary as-built | **Done** |

**FR-IX-023 completion order (normative for implementers):**

```text
S1a lean + summary string     (done)
S1b request date echo         (done)
    │
    ▼
S1c needs_summary[]           (1.4)
    │
    ▼
S1d expected_budget           (1.5)
    │
    ▼
S1e free-text date extract    (1.6)  ← **Done**
    │
    ▼
1.7 mark FR-IX-023 as-built   (OpenSpec + Postman + regression)  ← **Done**
```

- **FR-IX-023 is complete** after S1c + S1d + S1e (**Phase 1.7 as-built**).  
- **S1b** stays request-echo only; **S1e** adds document/text extract when the request omits dates.

**Non-goals in this phase:** ranked assets on Call 1; public `documents[]` / `kg_*` (Call 2 recommend is separate stage).

**Runtime dependency:** none beyond ingest (InMemory + KG).

#### Test implementation — Stage S1

| Attribute | Detail |
|-----------|--------|
| **Independently testable?** | **Yes — fully in this repo’s default CI** |
| **Does not need** | Pgvector, Neo4j, fleet mirror, Spring, multi-agent recommend, pricing |
| **Test implementation (S1a lean — done)** | (1) Lean fields; (2) summary from project_text/file; (3) no `documents`/`kg_built`; (4) Call 2 with `ingest_id` |
| **Test implementation (S1b — done)** | Request dates echoed; omitted → null; invalid window → 400 |
| **Test implementation (S1c–d)** | Stub needs shape; budget present / absent / never invent |
| **Test implementation (S1e free-text dates)** | (1) Request omits dates + text has clear window → `tentative_*` set; (2) no dates in text → null + warning; (3) request dates override extracted dates; (4) end ≥ start when both resolved |
| **Test implementation (1.7)** | Checklist: OpenSpec FR-IX-023 status as-built; Postman example full summary body; full S1 regression green |
| **Suggested modules** | `tests/test_recommendations_intake.py`, `tests/test_project_knowledge_api.py`, unit for summary / date / budget extractors |
| **Fixtures / stubs** | Project text fixtures with/without dates and budget; Postman optional |
| **CI job** | **default** |
| **How later phases don’t block** | Lean S1a/S1b is enough for Spring saga; S7 uses `ingest_id` only |

---

### Phase 2 — Spring ↔ FastAPI resilience C1 (mostly Spring)

Maps to `spring-boot-fastapi-integration-resilience.md` Phase C1.

**Stage-scoped implementation plans (implementers):**

| Stage | Perspective | Plan |
|-------|-------------|------|
| **S2a** | haystack-fast-api | [`phase2-s2a-haystack-implementation-plan.md`](./phase2-s2a-haystack-implementation-plan.md) |
| **S2b** | Spring Boot REST API | [`phase2-s2b-spring-implementation-plan.md`](./phase2-s2b-spring-implementation-plan.md) |

| Step | Work | Owner | Exit criteria |
|------|------|-------|---------------|
| **2.1** | WebClient (or RestClient) with **per-operation timeouts** (ingest ≫ Q&A ≫ health) | Spring | Config documented |
| **2.2** | Circuit breaker + bulkhead (Resilience4j) on recommender client | Spring | CB opens on forced 5xx; recovers |
| **2.3** | `Idempotency-Key` on ingest POST; FastAPI stores key → same `ingest_id` on retry | Spring + **App** | Double POST same key → one logical ingest — **app as-built (S2a)** |
| **2.4** | Correlation: `X-Correlation-Id` / `traceparent` on every call; log both sides | Both | Trace id visible end-to-end — **app as-built (S2a)**; Spring half → S2b |
| **2.5** | Spring **saga** orchestrator: ingest → persist ingest_id → Q&A (0..N) → (later) recommend | Spring | No re-ingest on Q&A failure |
| **2.6** | Document max file size, expected p95; **error contract already as-built** (`{"error","message"}`) — document in ops runbook | Both | Runbook + regression tests — **app docs as-built (S2a)** |

**As-built (app / S2a):** shared error JSON via `app/core/errors.py`; `run_in_threadpool` on ingest/Q&A; process-local `Idempotency-Key` store (`app/services/ingest_idempotency.py`); correlation middleware (`app/middleware/correlation.py`); OpenSpec FR-IX-024/025 + Postman headers.  
**App remaining (out of S2a):** multi-replica shared idempotency store; Spring client half → **S2b**.

**Defer C2 (202 + poll/SSE)** until measured gateway timeouts force it (Phase 9).

#### Test implementation — Stages S2a / S2b

| Attribute | Detail |
|-----------|--------|
| **Independently testable?** | **Yes — split by repo** |
| **S2a App test implementation** | (1) Same `Idempotency-Key` → same `ingest_id`; (2) different keys → two ingests; (3) missing key → current behavior; (4) correlation header logged; (5) **regression:** error body `{"error","message"}` still holds |
| **S2a modules** | `tests/test_ingest_idempotency.py`, middleware logging tests; error-shape regression (existing or thin) |
| **S2b Spring test implementation** | (1) Timeout on delayed stub; (2) CB opens after N 500s; (3) bulkhead rejects excess concurrency; (4) saga: ingest OK then Q&A 500 → no second ingest; (5) idempotency key on retry |
| **S2b harness** | WireMock / MockWebServer |
| **CI job** | app **default**; Spring repo CI |
| **Stubs** | In-memory idempotency map; HTTP stubs |

---

### Phase 3 — Agent-fronted indexing (R1) + optional SuperComponent

Maps to dual-plane R1 + `indexing-pipeline-supercomponent.md`.

| Step | Work | Exit criteria | Status |
|------|------|---------------|--------|
| **3.1** | In-process tool `run_indexing_from_request` wrapping `IndexingIngestService` (meta stamp, KG hard-fail, session registry) | Tool parity with direct HTTP ingest tests | **Done** |
| **3.2** | LangGraph path: `START → index_tool → …` behind feature flag; **index_tool = Coordinator gate** (non-LLM forced edge, not a Worker agent); keep direct service path default | Flag off = as-built; flag on = same DTO | **Done** (`INDEXING_VIA_AGENT_GATE`, default false) |
| **3.3** | (Optional) `IndexingPipelineSuperComponent` around `build_indexing_pipeline` only; **no KG inside**; explicit I/O maps for chunks + `documents_written` | Service can call SC; unit smoke test | **Deferred** |
| **3.4** | Failure parity: unsupported MIME / KG hard-fail still 4xx | Regression tests green | **Done** |

**As-built (app / S3):** `app/agents/tools.py` (`run_indexing_from_request`); `app/agents/indexing_gate.py` (`START→index_gate→END`); API wire in `app/api/recommendations.py`; tests `tests/test_indexing_tool.py`.

**Runtime dependency:** Phase 1 optional (tool can return technical body only). No Pgvector/Neo4j.

#### Test implementation — Stages S3 / S3.3

| Attribute | Detail |
|-----------|--------|
| **Independently testable?** | **Yes — fully in default CI with InMemory** |
| **Does not need** | Pgvector, Neo4j, fleet, Spring, pricing, Call 2 multi-agent enrich |
| **S3 test implementation** | (1) Tool vs `IndexingIngestService` parity on fixture; (2) flag on: `START→index_tool→END` forced non-LLM gate; (3) flag off: HTTP unchanged; (4) MIME/KG hard-fail parity; (5) gate failure sets `indexing_ok=false` semantics for later S7 |
| **S3.3 test implementation** | SC smoke `run(sources=…)`; KG still outside SC; intermediate chunk outputs available |
| **Suggested modules** | `tests/test_indexing_tool.py`, `tests/test_indexing_supercomponent.py` |
| **CI job** | **default** |
| **Stubs** | Stub agent mode; InMemory; no LLM |

---

### Phase 4 — Data platform: near-real-time fleet mirror (D1→D2 / T0–T2)

Maps to dual-plane §10 Track D + §11 T-phases. **Primary work in config repo.**

| Step | Work | Where | Exit criteria |
|------|------|-------|---------------|
| **4.1 T0** | Confirm `postgres-primary` on `heavy-rental-network`; runbook for merge success/halt | Config | One successful merge when primary up |
| **4.2 T1** | Near-RT poll (**~60s** on config-repo `develop`); `postgres_haystack_sync` `restart: unless-stopped`; lag logging/metrics if missing | Config | Row change visible on `postgres_haystack` within SLA |
| **4.3 T2** | Table allowlist (Asset, Booking, Category, …); metrics | Config | Deterministic table set |
| **4.4 D0** | Freeze schema contract from Phase 0.2 into versioned doc | Shared | Contract tests or snapshot |

**App work later:** SQLAlchemy read models against Postgres-Haystack (`postgres_haystack`), not primary.

#### Test implementation — Stage S4

| Attribute | Detail |
|-----------|--------|
| **Independently testable?** | **Yes — config/devcontainer harness** |
| **Does not need** | App recommend, Neo4j populate, multi-agent |
| **Test implementation** | (1) `postgres_haystack` healthy; (2) seed primary → after sync cycle row on haystack; (3) primary down → no wipe of haystack; (4) lag logged; (5) allowlist tables only (Asset, Booking, …) |
| **Harness** | Two Postgres containers + `postgres_haystack_sync` script |
| **CI job** | **config-sync** (config repo) |
| **Stubs** | Fixture primary schema from S0/D0 |
| **Note** | Proves fleet LTM mirror path: **primary → sync → haystack** |

---

### Phase 5 — Indexing DocumentStore cutover (I0–I1 / T5)

Maps to dual-plane §4.5. **Critical for multi-replica and Call 1→2 without sticky sessions.**

| Step | Work | Exit criteria | Status |
|------|------|---------------|--------|
| **5.1 T5/D4** | Postgres-Haystack: `pgvector` image or `CREATE EXTENSION vector`; dim matches `INDEXING_EMBEDDING_DIM` | Extension present | Config / infra (not app) |
| **5.2 I0** | Config `INDEXING_DOCUMENT_STORE=memory\|pgvector` (default **memory**); `build_document_store()` factory | CI stays memory | **As-built** (FR-IX-027) |
| **5.3 I1** | Wire factory into indexing pipeline + session registry; writer → store from flag | Ingest with flag writes durable chunks | **As-built** (FR-IX-028) |
| **5.4** | All retrieval tools **must** filter `user_id` (+ `ingest_id`); isolation test two users | Cross-tenant retrieval fails | **As-built** (FR-IX-028) |
| **5.5** | Optional TTL/delete job for temporary project chunks | Delete one ingest without affecting another | **As-built** (FR-IX-028) |
| **5.6** | Integration suite (optional live pgvector); full memory suite still green | Dual-mode CI | **As-built** (marker + skip) |

**Does not require Neo4j or Kafka.** I2 production default `pgvector` remains TARGET.

#### Test implementation — Stages S5-I0 / S5-I1

| Attribute | Detail |
|-----------|--------|
| **Independently testable?** | **Yes — I0 + I1 default packs; live pgvector optional** |
| **S5-I0 test implementation** | (1) factory `memory` default; (2) invalid flag errors; (3) full suite green without Postgres — **as-built** in `tests/test_document_store_factory.py` |
| **S5-I1 test implementation** | (1) two users isolation on shared InMemory — **as-built** `tests/test_tenant_vector_isolation.py`; (2) TTL/delete isolation — **as-built** `tests/test_project_chunk_cleanup.py`; (3) optional live pgvector isolation + reconnect — `tests/test_pgvector_isolation.py` |
| **Suggested modules** | `tests/test_document_store_factory.py`, `tests/test_tenant_vector_isolation.py`, `tests/test_project_chunk_cleanup.py`, `tests/test_pgvector_isolation.py` (**all as-built**) |
| **Markers** | `@pytest.mark.pgvector` registered; skipped unless `RUN_PGVECTOR_TESTS=1` |
| **CI job** | Default suite = memory path (as-built); live **pgvector** optional/nightly |
| **Stubs** | Fake embedder fixed dim (must match `INDEXING_EMBEDDING_DIM` for query + store); optional live Postgres for marker pack |
| **As-built note** | Default suite uses InMemory + mock embedder; conftest forces dim **384**. Call 1 uses `create_session_document_store()`. Retrieval always filters session `user_id` + `ingest_id`. Archive: `openspec/changes/archive/2026-08-12-s5-i1-document-store-pipeline-wire/`. |

---

### Phase 6 — Pricing production path (ML Phase 1e → 2a → agent tool) — **as-built S6**

Maps to `ml-pricing-multi-agent.md` + `docs/dynamic-pricing-execution-plan.md`.  
Archive: `openspec/changes/archive/2026-08-12-s6-predict-asset-price-tool/`.

| Step | Work | Exit criteria | Status |
|------|------|---------------|--------|
| **6.1 Phase 1e** | `pricing` repository (`period_utilization`, `lead_time_days`) + `pricing_client` / adapter wiring | Live util when `db`+dates present; defaults when not; suite green | **As-built** |
| **6.2 Phase 2a** | `app/services/pricing/` package; per-asset min/max clamp; in-process `predict_price` (no public price HTTP) | Model + clamp; never silent zeros | **As-built** (also 2b pipeline wire + 2c quote API) |
| **6.3** | In-process agent tool `predict_asset_price` → `pricing_client`; returns `daily_rate`, clamp metadata, `model_version` | Tool unit tests + stub/mock mode for CI | **As-built** (`app/agents/tools.py`) |
| **6.4** | Service recommend path (`RecommendationService` / adapter) on same pricing entrypoint | Service + agent share pricing | **As-built** |

**Product accuracy** benefits from Phase 4 mirror; **tests do not require it**.  
**Not in S6:** Phase 7 Pricing Workers [7]×N graph fan-out; Phase 2d model recalibration.

#### Test implementation — Stage S6 (as-built)

| Attribute | Detail |
|-----------|--------|
| **Independently testable?** | **Yes — without Phase 7 recommend graph** |
| **Does not need** | Multi-agent synthesis, Neo4j, SuperComponent |
| **Test implementation** | **Regression (1e/2a):** repository util/lead-time; client/adapter `db`+dates; model clamp. **Tool (S6):** (1) golden shape; (2) SoT parity with `predict_price_for_asset`; (3) `was_clamped` pass-through; (4) silent zero → `ValueError`; (5) tool name contract; (6) optional `asset_id` echo |
| **Modules** | `tests/test_pricing_repository.py`, `tests/test_pricing_client_phase1e.py`, `tests/test_pricing_phase1e_wiring.py`, `tests/test_pricing_model.py`, `tests/test_pricing_phase2b_wiring.py`; **S6** `tests/test_predict_asset_price_tool.py` |
| **CI job** | **default** |
| **Stubs** | Fixture ORM rows; mock `predict_price_for_asset` for zero/clamp edge cases |
| **Optional integration** | Real `postgres_haystack` when S4 available |

---

### Phase 7 — Multi-agent recommend graph (R4–R5 / Call 2 enrich) — C/W/D A–L

Maps to dual-plane §4.1 [5]–[8], [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md), [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) §10 **A–L**.

**Safeguards:** no recommend if [4] failed; no invent inventory; no silent zeros; no free-form SQL/Cypher; must-seq within need; may-par across needs (capped).

**Independence:** default CI uses **fixture tools** (no live primary/Neo4j). Inject tools via DI/factory.

#### Role vocabulary (implement in stages below)

| Piece | Role | Stage | Status |
|-------|------|-------|--------|
| `RecommendAgentState` + partition validation | STM / F-2 | **S7.0** | **As-built** |
| Fleet/project tools | Worker backends | **S7.1** | **As-built** |
| Neo4j tools (fake then real) | optional | **S7.2** / S8 | Todo |
| LangGraph DAG seq/par | Coordinator + Delegator + Workers | **S7.3** | **As-built** |
| Tool-free synthesis | Coordinator [8] | **S7.4** | **As-built** |
| HTTP Call 2 multi-agent enrich | API | **S7.5** | **As-built** |
| tool_traces metrics | G-1 | **S7.6** | **As-built** |
| Prompts A–L + DI | all agents | **S7.7** | Todo |

---

#### Stage S7.0 — RecommendAgentState + partition validation — **as-built**

| Field | Content |
|-------|---------|
| **Status** | **As-built (2026-08-12)** |
| **Work** | TypedDict/state module for recommend mode; `validate_state_transition(role, current, proposed)`; partition write helpers |
| **Exit criteria** | Illegal writes rejected; legal Worker writes accepted — **met** |
| **Test implementation** | (1) Fleet Worker cannot write `recommendation`; (2) price for unknown `asset_id` rejected; (3) legal `fleet_by_need[need_id]` write OK; (4) gate false blocks fleet write |
| **Modules** | `app/agents/recommend_state.py`; `tests/test_recommend_agent_state.py` |
| **Fixtures** | `tests/fixtures/recommend/state_minimal.json`, `state_gate_false.json` |
| **CI job** | **default** |
| **C/W/D** | D, F-2, H-1 |
| **OpenSpec** | archive `openspec/changes/archive/2026-08-12-s7-0-recommend-agent-state/` · equipment-recommendation FR notes |

---

#### Stage S7.1 — In-process tool catalog — **as-built**

| Field | Content |
|-------|---------|
| **Status** | **As-built (2026-08-12)** |
| **Work** | `decompose_project_needs`, `retrieve_fleet_assets`, `filter_fleet_candidates`, `check_booking_availability` (read-only allowlist); factory for fake vs SQL backends |
| **Exit criteria** | Stub + optional DB tests green; free-form SQL rejected — **met** (fake default CI) |
| **Test implementation** | (1) Fake fleet list filter by category; (2) availability drops overlapping bookings; (3) empty fleet → []; (4) decomposer stub returns fixed needs; (5) allowlist rejects unknown tool name |
| **Modules** | `app/agents/fleet_tools.py`, `app/agents/tool_factory.py`; `tests/test_fleet_tools.py`, `tests/test_tool_factory.py` |
| **Fixtures** | `tests/fixtures/recommend/fleet_seed.json` |
| **CI job** | **default** (fake); optional haystack SQL when S4 |
| **C/W/D** | E, H-2 (fleet LTM via tools), J-1 |
| **OpenSpec** | archive `openspec/changes/archive/2026-08-12-s7-1-fleet-tool-catalog/` · equipment-recommendation FR notes |
| **Not in S7.1** | LangGraph DAG (S7.3); Neo4j tools (S7.2); HTTP Call 2 multi-agent enrich (S7.5) |

---

#### Stage S7.2 — Neo4j tools (no-op until S8)

| Field | Content |
|-------|---------|
| **Work** | `neo4j_cypher_read` (templates only), `trigger_neo4j_populate` (returns job_id / no-op) |
| **Exit criteria** | Empty graph OK; free-form Cypher rejected; recommend not blocked |
| **Test implementation** | (1) empty backend → []; (2) free-form Cypher → error; (3) template query with fixture graph (optional); (4) populate trigger non-blocking |
| **Suggested modules** | `tests/test_neo4j_tools.py` |
| **CI job** | **default** fake; **neo4j** optional |
| **C/W/D** | E, K-3 skip path |

---

#### Stage S7.3 — Recommend LangGraph DAG (seq / par) — **as-built**

| Field | Content |
|-------|---------|
| **Status** | **As-built (2026-08-12)** |
| **Work** | Graph: gate→[5]→Delegator→([6]→[7])×N→[8]; modes `qa` vs `recommend`; fan-out cap config; Workers do not spawn siblings |
| **Exit criteria** | Within-need order; across-need batch invocations; gate refuse — **met** |
| **Test implementation** | (1) Recording traces: never price before fleet for same need; (2) multi-need → fleet worker once per `need_id`; (3) [4] fail → no fleet/price calls; (4) fan-out cap=1 serializes needs; (5) Stage-1 Q&A graph still green (mode isolation) |
| **Modules** | `app/agents/recommend_graph.py`, `app/agents/recommend_nodes.py`; `tests/test_recommend_graph_order.py`, `tests/test_recommend_fanout.py` |
| **Config** | `RECOMMEND_FANOUT_CAP` (default 4, min 1) |
| **CI job** | **default** |
| **C/W/D** | K, L (must-seq / may-par), F-1 |
| **OpenSpec** | archive `openspec/changes/archive/2026-08-12-s7-3-s7-4-recommend-graph-synthesis/` |
| **Not in S7.3** | HTTP Call 2 enrich (S7.5); Neo4j tools (S7.2); prompts A–L (S7.7) |

---

#### Stage S7.4 — Tool-free synthesis + validation — **as-built**

| Field | Content |
|-------|---------|
| **Status** | **As-built (2026-08-12)** |
| **Work** | Coordinator [8] merge to `results_by_need`; stub merge for CI; F-2 on output |
| **Exit criteria** | Golden assets/rates; empty fleet → null item + warning; no invent — **met** |
| **Test implementation** | (1) Fixture candidates+prices → golden DTO exact `asset_id`/rates; (2) empty fleet → `item: null` + warning; (3) pricing failure → fallback/warning, no zeros; (4) LLM stub cannot inject unknown asset; (5) schema validation fails on bad shape |
| **Modules** | `app/agents/recommend_synthesis.py`; `tests/test_recommend_synthesis.py` |
| **Fixtures** | `tests/fixtures/recommend/golden_results_by_need.json` |
| **CI job** | **default** |
| **C/W/D** | Coordinator J-3, F-2, G-2 |
| **OpenSpec** | archive `openspec/changes/archive/2026-08-12-s7-3-s7-4-recommend-graph-synthesis/` |

---

#### Stage S7.5 — HTTP Call 2 multi-agent enrich — **as-built**

| Field | Content |
|-------|---------|
| **Status** | **As-built (2026-08-12)** |
| **Work** | Enrich **Call 2** `getassetrecommendations` with full C/W/D orchestrator; map to quote DTO / `results_by_need`; feature flag for graph vs MVP |
| **Exit criteria** | Contract tests vs OpenAPI / schema — **met** |
| **As-built note** | Flag `RECOMMEND_VIA_AGENT_GRAPH` (default **false**) keeps MVP `RecommendationService`. Flag on: `SessionRecommendService` → `run_recommend_graph` → same `AssetRecommendResponse`. Gate refuse → 400. Call 3 is chatbot `.../query`. |
| **Test implementation** | (1) POST recommend with fixtures → 200 shape; (2) flag off → MVP Call 2 path; (3) gate fail → 4xx/structured error; (4) multi-need body matches golden |
| **Modules** | `app/services/session_recommend.py`; `tests/test_recommend_http_call2.py` |
| **Config** | `RECOMMEND_VIA_AGENT_GRAPH` (default false) |
| **CI job** | **default** |
| **C/W/D** | Coordinator handoff; I session |
| **OpenSpec** | archive `openspec/changes/archive/2026-08-12-s7-5-s7-6-call2-enrich-traces/` |
| **Not in S7.5** | Neo4j tools (S7.2); prompts A–L (S7.7); production default flip |

---

#### Stage S7.6 — tool_traces and metrics — **as-built**

| Field | Content |
|-------|---------|
| **Status** | **As-built (2026-08-12)** |
| **Work** | Append traces with `role`, `node`, `need_id`, `tool`, `duration_ms`; warnings on empty fleet |
| **Exit criteria** | Contract asserts on trace fields — **met** |
| **Test implementation** | (1) After graph run, traces include worker roles; (2) fan-out traces have `need_id`; (3) duration ≥ 0; (4) empty fleet warning present |
| **Modules** | `app/agents/recommend_traces.py`; `tests/test_tool_traces.py` |
| **CI job** | **default** |
| **C/W/D** | G-1 |
| **OpenSpec** | same archive as S7.5 |

---

#### Stage S7.7 — Prompts A–L + tool DI

| Field | Content |
|-------|---------|
| **Work** | Separate `RECOMMEND_*` prompts from Stage-1; factory injects tools; Delegator allowlist only; stub LLM |
| **Exit criteria** | No prompt contamination; DI swaps fakes in tests |
| **Test implementation** | (1) Q&A prompts still forbid invent fleet; (2) recommend synthesis prompt has no tools; (3) DI injects fake fleet; (4) Delegator rejects unknown worker_kind; (5) `PROJECT_AGENT_MODE=stub` path deterministic |
| **Suggested modules** | `tests/test_recommend_prompts.py`, `tests/test_agent_tool_di.py` |
| **CI job** | **default** |
| **C/W/D** | A–L full contracts |

---

#### Phase 7 aggregate regression (run after any S7.x merge)

| # | Case |
|---|------|
| R1 | Full fixture multi-need graph → golden `results_by_need` |
| R2 | Stage-1 Q&A suite still green |
| R3 | Optional: real haystack seed when S4 available (not default CI) |

---

### Phase 8 — Neo4j fleet projection (D3 / T3–T4)

Can partially overlap Phase 7 (SQL fleet tools first; Neo4j tools after populate).

| Step | Work | Where | Exit criteria |
|------|------|-------|---------------|
| **8.1 T3** | Job/script `populate-neo4j-from-haystack` — SQL → Cypher MERGE; label namespace vs DocumentStore | Config (+ optional app client) | Browser / query shows fleet after load |
| **8.2 T4** | Trigger on successful merge or admin HTTP; never drop DocumentStore labels | Config | Incremental or scoped delete |
| **8.3** | Wire real `neo4j_cypher_read` + populate trigger into tool module | App | Agents get graph context when available |

#### Test implementation — Stage S8

| Attribute | Detail |
|-----------|--------|
| **Independently testable?** | **Yes — Neo4j harness; not full recommend E2E** |
| **Does not need** | Spring saga, C2, production Pgvector |
| **Test implementation (job)** | (1) Seed SQL → populate → Cypher count; (2) second run MERGE idempotent; (3) DocumentStore labels survive; (4) scoped delete fleet labels only |
| **Test implementation (app tool)** | (1) Template query returns neighbors; (2) empty DB → []; (3) free-form Cypher rejected; (4) populate returns `job_id` non-blocking |
| **Suggested modules** | config job tests; `tests/test_neo4j_tools_integration.py` |
| **CI job** | **neo4j** optional/nightly; default keeps S7.2 fake |
| **Stubs** | Seed `postgres_haystack` directly; fixture Cypher |

---

### Phase 9 — Production hardness (C2, I2, D2+)

| Step | Work | When |
|------|------|------|
| **9.1 C2** | `202 Accepted` + job status poll and/or SSE/NDJSON progress for long ingest/recommend | When proxy timeouts or multi-minute agent work hurt |
| **9.2** | Optional object storage for multi-MB project files | When portal files routinely large |
| **9.3 I2** | Production default `INDEXING_DOCUMENT_STORE=pgvector`; memory for CI/local only | After I1 stable in staging |
| **9.4 D2** | Outbox/CDC if poll lag SLA insufficient | Metrics-driven |
| **9.5 C3** | Queue / gRPC only if measured need | Avoid early |

#### Test implementation — Stages S9.1–S9.5

| Stage | Test implementation | CI |
|-------|---------------------|-----|
| **S9.1** | (1) POST → 202 + `job_id`; (2) poll until succeeded; (3) SSE ordered events; (4) cancel/fail; inject **sleep worker** (no real LLM). Spring: WireMock poll client | **default** app + Spring |
| **S9.2** | (1) `file_url` fetch mocked HTTP; (2) reject bad hosts | unit default |
| **S9.3** | (1) staging smoke pgvector; (2) CI conftest forces memory | dual-mode |
| **S9.4** | (1) outbox fixture events; (2) lag metrics unit | optional |
| **S9.5** | Spike/benchmark only if pursued | not a gate |

**Does not need for S9.1 gate:** Neo4j, fleet accuracy, full multi-agent Call 2 accuracy.

---

## 5. Phase independence matrix (quick reference)

| Phase / stages | Default CI without later phases? | Primary harness | Stub / substitute | Blocks later if untested? |
|----------------|----------------------------------|-----------------|-------------------|---------------------------|
| **0 / S0** | Yes | Doc checklist | N/A | Soft for fleet accuracy |
| **1 / S1** | Yes | App pytest + API | Stub decomposer | No |
| **2 / S2a–b** | Yes (split) | pytest / WireMock | In-mem idempotency | No |
| **3 / S3** | Yes | InMemory | Stub graph/LLM | No |
| **4 / S4** | Yes (config) | Two PG + sync | Fixture primary | No (app seed) |
| **5 / S5-I0–I1** | I0+I1 yes (**as-built**); live pgvector optional | Factory + wire + isolation | Memory default | No |
| **6 / S6** | Yes | Unit + fixture ORM | Mock model | No |
| **7 / S7.0–7.7** | Yes **per stage** | Fixture tools + golden | Fake fleet/price/Neo4j | Soft E2E needs 4/6/8 |
| **8 / S8** | Yes (optional CI) | Neo4j + seed SQL | Direct seed haystack | No (7 uses fake) |
| **9 / S9.x** | Yes per sub-item | Fake worker / config | Sleep worker | No |

### Parallelism that stays test-safe

```text
Phase 1 ──┐
Phase 2 ──┼── can land in any order; each has own suite
Phase 3 ──┤
Phase 4 ──┘

Phase 5 (I0) anytime after indexing stable
Phase 5 (I1) needs only pgvector infra (not Phase 7/8)

Phase 6 anytime after schema seed exists (fixtures OK)

Phase 7 stages S7.0–S7.7 each mergeable alone with fakes;
         needs contracts from 1/3/6 as *interfaces*

Phase 8 anytime after seed SQL tables exist (not full Spring)

Phase 9.1 anytime after HTTP surface exists (fake worker)
```

### “Done” definition per stage (test gate)

A **stage** (or phase) may merge when:

1. **BDD scenarios** for product-facing exit criteria exist as **Given / When / Then** (test names, docstrings, or optional Gherkin)—see **§2.2**.  
2. **TDD**: production behavior was driven by **failing tests first** (red → green → refactor)—see **§2.1 / §2.3**.  
3. Its **Test implementation** pack is green in the stage’s harness.  
4. **Regression suite** for earlier shipped stages is still green.  
5. New public contracts have at least one golden fixture test.  
6. Feature flags default so unfinished later stages are not required at runtime in CI.  
7. Suggested test modules exist (or equivalent) covering the listed cases.

---

## 6. Concrete “next PRs” (recommended start)

Every PR below follows the **§2.3** workflow: BDD scenarios → TDD red tests → implement → refactor → regression.  
Every code-bearing PR **must** use the **PR description template** below (bare minimum: **What & Why** + **Key Changes**).

| PR | Stage | Title | Test implementation (must ship with PR) |
|----|-------|-------|----------------------------------------|
| **PR-A** | S1 | Call 1 lean body (`ingest_id`, `user_id`, `user_requirement_summary`) | Schema + API: summary from project_text/file; no technical fields; Call 2 still works; **BDD** G/W/T lean body |
| **PR-B** | S2a | Ingest idempotency key | Double POST same key; different keys; **BDD** “same key → one ingest_id” |
| **PR-C** | S5-I0 | DocumentStore factory | Factory unit; suite memory-green (**TDD** unit-first) |
| **PR-D** | S3 | Agent indexing tool R1 + gate [4] | Tool vs service parity; flag-off unchanged; gate fail semantics; **BDD** gate refuse |
| **PR-E** | S7.0 | RecommendAgentState + validation | **Shipped** — illegal partition writes rejected (**TDD** unit-first) |
| **PR-F** | S7.1 | Fleet tool catalog + DI factory | **Shipped** — fake fleet filter/availability; allowlist (**TDD** + contract) |
| **PR-G** | S7.3–7.4 | Recommend graph + synthesis | **Shipped** — order, fan-out, golden results_by_need; **BDD** no invent / empty fleet |
| **PR-H** | S7.5–7.6 | Call 2 multi-agent enrich + traces | **Shipped** — same quote DTO behind flag; role/`need_id`/`duration_ms` traces; **BDD** Call 2 quote happy path |
| **PR-I** | S7.7 | Prompts A–L + tool DI | Recommend prompts isolated from Stage-1; Delegator allowlist; **TDD** stub LLM |

### PR description template (required bare minimum)

Copy this structure into the GitHub PR body. **Required** sections must not be empty for stage PRs (PR-A…PR-H and later).

```markdown
## What & Why
<!-- 1-2 sentences: What problem does this solve, or what feature does it add? -->


## Key Changes
<!-- Bullet points highlighting the 2-3 most important files/logic shifts -->
- 
- 

---

### Optional (Good to have)

<details>
<summary><b>Out of Scope / Follow-up Work</b></summary>

<!-- List items intentionally LEFT OUT of this PR that will be handled in future branches/tickets -->
- [ ] 
</details>

<details>
<summary><b>Testing & Verification</b></summary>

- [ ] Unit / Integration tests added or updated
- [ ] Tested manually (Postman / local FastAPI / local DB)
</details>

<details>
<summary><b>Visuals / Screenshots (For UI changes)</b></summary>

<!-- Drag and drop screenshots or screen recordings here; usually N/A for API-only PRs -->

</details>

<details>
<summary><b>Dependent PRs / API Contracts</b></summary>

<!-- Link related backend/frontend PRs or contract/DTO changes (Spring, config repo, OpenSpec) -->
- Depends on / Pairs with: #
</details>
```

**How to fill it for this plan**

- **What & Why** — name the **stage ID** (e.g. S1, S7.4) and the exit criterion or problem solved.  
- **Key Changes** — 2–3 bullets on the main modules/files or logic shifts.  
- **Out of Scope** — later stage IDs or intentionally deferred work (keeps PRs reviewable).  
- **Testing & Verification** — align with **§2.1 TDD**, **§2.2 BDD**, and the **PR checklist** below (red-first tests; G/W/T for product-facing behavior).  
- **Dependent PRs / API Contracts** — Spring saga, config sync, DTO/OpenSpec pairs when relevant.

### PR checklist (TDD + BDD)

Before merge, author confirms:

- [ ] **BDD**: Stage exit criteria expressed as Given/When/Then (or equivalent scenario titles).  
- [ ] **TDD**: At least one new/changed behavior had a **failing test before** production code (or would fail if logic removed).  
- [ ] Stage **Test implementation** pack cases covered and green in default (or marked) CI job.  
- [ ] Regression (earlier stages) green.  
- [ ] No live LLM / primary / Neo4j required for default CI gate (P5/P9).  
- [ ] Feature flags default-safe (P2).

Parallel outside this repo (each with own tests):

- Spring S2b vs WireMock  
- Config S4 sync script vs two Postgres  
- S0 D0 schema contract review  

---

## 7. Cross-cutting testing strategy

Process: **§2.1 TDD** + **§2.2 BDD** + **§2.3 stage PR workflow**. Layer tactics below implement those principles.

### 7.0 As-built default suite (today)

Normative OpenSpec companions: [`../openspec/specs/project-setup/`](../openspec/specs/project-setup/) · indexing FR-IX-015 · knowledge-graph FR-KG-014 · `docs/testing/`.

| Item | As-built |
|------|----------|
| **Command** | `uv run pytest` or `uv run pytest tests/ -q` from app root |
| **Markers / skips** | `@pytest.mark.pgvector` registered; live tests skip unless `RUN_PGVECTOR_TESTS=1` |
| **External prereqs** | **None** for default green (no live LLM, Neo4j, Pgvector required) |
| **`tests/conftest.py` autouse** | Forces `INDEXING_EMBEDDER=mock`, `INDEXING_EMBEDDING_DIM=384`, `INDEXING_DOCUMENT_STORE=memory`, `RECOMMEND_VIA_AGENT_GRAPH=false`, `PROJECT_AGENT_MODE=stub`, temp `KG_ARTIFACT_DIR`; clears settings cache; resets session + idempotency stores |
| **Embed dim rule** | Query embedder for `project_vector_search` **must** use same mode/dim as documents in the session store (mismatch → Haystack embedding-size error) |
| **Tenant filters** | Vector tools filter session `user_id` + `ingest_id` (FR-IX-028) |
| **Health tests** | Do not skip if Postgres is down — accept `database=up\|down` |
| **Host `.env`** | May set dim 768 / OpenAI for **manual** API work; **must not** break pytest (conftest overrides) |

| Layer | Approach |
|-------|----------|
| **Process** | **TDD** red→green→refactor for units/contracts; **BDD** G/W/T for API, agent outcomes, resilience |
| **Unit** | Schema, decomposer stub, pricing clamp, state validation, synthesis merge from fixtures |
| **Pipeline** | Indexing MIME/branch; SC smoke if added |
| **API** | Call 1 summary; Call 2 recommend quote; Call 3 Q&A—prefer scenario-named tests |
| **Isolation** | Two `user_id`s shared-store isolation + TTL delete — **as-built** (InMemory); live Pgvector optional |
| **Agent** | `PROJECT_AGENT_MODE=stub`; forced [4] edge; fixture tools; no invent |
| **Integration (optional CI)** | Live pgvector pack as-built; Neo4j seed — **TARGET** |
| **Manual** | Postman; Spring WebClient spike |
| **Markers** | `@pytest.mark.pgvector` **as-built**; `@pytest.mark.neo4j` / `integration` / `recommend_graph` — **TARGET** |
| **Fixtures dir** | Prefer `tests/fixtures/recommend/` for golden needs/fleet/prices/results (`Then` payloads) |
| **Naming** | Prefer `tests/test_<stage_topic>_*.py` aligned with stage IDs; scenario titles mirror BDD |
| **Optional Gherkin** | `tests/features/*.feature` + pytest-bdd only if team adopts; not required |

### Recommended CI jobs

| Job | When | Covers stages | Status |
|-----|------|---------------|--------|
| **default** | Every PR | Full `tests/` (S1, S2a, S3, S5-I0/I1 memory packs, KG/vector tools, pricing unit, recommend MVP, …); mock embedder dim 384 via conftest; no Neo4j | **As-built** |
| **pgvector** | Main / nightly / labeled | S5-I1 live (`RUN_PGVECTOR_TESTS=1`) | **Optional pack as-built** |
| **neo4j** | Nightly / labeled | S8 | **TARGET** |
| **config-sync** | Config repo PR | S4 | **TARGET** |
| **spring-client** | Spring repo PR | S2b | **TARGET** (Spring repo) |

---

## 8. Risks & mitigations (plan-level)

| Risk | Mitigation |
|------|------------|
| Boiling the ocean day one | Wave order; ship Call 1 + C1 first |
| Double ingest on Spring retry | PR-B idempotency before aggressive retries |
| Cross-tenant vector leak | Hard filters + isolation tests in I1 |
| LLM invents assets/prices | Structured stub merge; schema validation |
| Phase 7 blocked waiting on Neo4j | Fake Neo4j tool; Phase 8 optional for recommend correctness |
| Phase 6 blocked waiting on live mirror | Seed/fixture ORM rows for repository tests |
| Sticky sessions still required | Prioritize I1 for multi-replica |
| Neo4j populate wipes DocumentStore | Label isolation + automated test in Phase 8 |
| Integration tests flaky in default CI | Markers + optional jobs only (**TARGET**); default suite stays unmarked + conftest-isolated |
| Host `.env` embed dim ≠ mock store dim | conftest forces `INDEXING_EMBEDDING_DIM=384`; vector tests pass matching `Settings` |

---

## 9. Explicit non-goals (this rollout)

- FastMCP / separate tool server  
- SSE as file upload channel  
- Public HTTP pricing API  
- Dual-write Spring → Neo4j  
- Mega SuperComponent (index+KG+session)  
- Replacing Spring as fleet SoT  
- Requiring full dual-plane stack to merge early product PRs  

---

## 10. Success metrics

| Milestone | Done when |
|-----------|-----------|
| **M1 Call 1** | Portal/Spring can show needs + dates + budget from ingest 200; `ingest_id` works for Call 2 |
| **M2 Multi-user durable** | Two users, two replicas, Q&A hits correct chunks after restart |
| **M3 Fleet-aware recommend** | Call 2 returns real Asset ids from mirror + non-zero clamped prices |
| **M4 Resilient saga** | Timeout + CB + idempotent ingest under failure drills |
| **M5 Graph context** | Neo4j fleet projection refreshes without blocking recommend |
| **M6 Multi-agent Call 2** | Fixture recommend graph green on Call 2: C/W/D DAG, fan-out, golden quote/`results_by_need`, no invent; traces with `role`/`need_id` |

Each milestone maps to **end-to-end product proof**; stage merge gates use the **Test implementation** packs in §3.1–§5, not full milestones.

---

## 11. Open questions (need product/ops input before some phases)

1. Project chunk **TTL** (24h / 7d / until discard)?  
2. Must **every** Spring call go through Multi-Agent, or feature-flag subset?  
3. Neo4j populate: per upload / schedule / admin-only?  
4. Expected **p95 ingest** and max **file size** (drives C2 timing)?  
5. Auth Spring→FastAPI (mTLS / API key / mesh)?  
6. Sync table **allowlist** and lag SLA for availability/pricing?  

---

## 12. Mapping: study phases → this plan

| Feasibility phase IDs | This plan |
|----------------------|-----------|
| Call1 S1–S5 | Phase 1 |
| Resilience C1 / C2 / C3 | Phase 2 / 9.1 / 9.5 |
| Dual-plane D0–D4 | Phases 0, 4, 5, 8, 9 |
| Dual-plane I0–I2 | Phases 5, 9.3 |
| Dual-plane R1–R5 | Phases 3, 7 |
| Dual-plane T0–T5 | Phases 4, 5, 8 |
| SuperComponent S1–S5 | Phase 3.3 (optional) |
| ML pricing P1–P5 / 1e–2a | Phase 6 |
| Synthesis R5/M6 | S7.4–S7.5 |
| C/W/D A–L vocabulary | S7.0–S7.7 + [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) §10 |

---

## 13. Implementation readiness

| Item | Status |
|------|--------|
| Feasibility decisions | Complete (GO) |
| OpenSpec FR-IX-023 full Call 1 | **As-built** (S1a–S1e complete; Phase 1.7) |
| Call 1 lean public body | Shipping: `ingest_id`, `user_id`, `user_requirement_summary`, `tentative_*` echo, `warnings` |
| Internal recommendation routes | `/internal/v1/recommendations/...` |
| As-built ingest + Stage-1 Q&A | Live (internal paths) |
| Error JSON `{"error","message"}` | As-built |
| Pricing Phase 1e / 2a / 2b / 2c | **As-built** (`app/services/pricing/` + `pricing_client` + quote API) |
| Phase 6 / S6 `predict_asset_price` | **As-built** — tool → `pricing_client` (single SoT); Phase 7 Workers not wired |
| Phase 7 / S7.0 `RecommendAgentState` | **As-built** — F-2 partition validation; illegal writes rejected |
| Phase 7 / S7.1 fleet tool catalog | **As-built** — allowlisted in-process tools + fake/SQL DI factory |
| Phase 7 / S7.3 recommend LangGraph DAG | **As-built** — gate → [5] → Delegator → ([6]→[7])×N; `RECOMMEND_FANOUT_CAP` |
| Phase 7 / S7.4 tool-free synthesis | **As-built** — stub Coordinator [8]; empty fleet → `item: null`; no invent |
| FR-010 service recommend (seed) | **As-built Call 2 MVP** via SessionRecommendService; S7.5 wires graph behind same DTO (`RECOMMEND_VIA_AGENT_GRAPH`) |
| Full recommend multi-agent path | S7.0–S7.1 + S7.3–S7.6 **as-built**; S7.2 / S7.7 remain (Neo4j, prompts A–L) |
| Pgvector / Neo4j populate | Not in app path |
| Idempotency-Key on ingest | **As-built S2a** (process-local; multi-replica later) |
| Stage catalog | **Specified** (§3.1) |
| Per-stage test implementation | **Specified** (§4 each stage + §5–§7) |
| Default pytest isolation | **As-built** — §7.0; conftest mock embedder dim 384; optional `@pytest.mark.pgvector` only |
| Query/store embedding dim match | **As-built** — FR-IX-015 / FR-KG-014; OpenSpec project-setup 2.1.0 |
| TDD process (P9) | **Specified** (§2.1 red→green→refactor; mandatory for code stages) |
| BDD process (P10) | **Specified** (§2.2 Given/When/Then; stage PR workflow §2.3) |
| PR description template | **Specified** (§6 — What & Why + Key Changes required; optional details) |
| Accuracy validation | **3.2.1** cross-checked against app + OpenSpec |
| Ready to implement | **Yes — start S1 (Call 1) + parallel S2a idempotency / S2b Spring C1 / S4 config sync**, each with **BDD scenarios + TDD-first** test pack and the §6 PR body template; multi-agent via S7.0→S7.7 increments |
