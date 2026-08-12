# Feasibility Study: Multi-Agent Coordinator / Worker / Delegator Vocabulary

| Field | Value |
|------

> **Call numbering (as-built 2026-08-12):** HTTP **Call 1** = ingest · HTTP **Call 2** = **recommend / quote** (`getassetrecommendations`) · HTTP **Call 3** = **chatbot Q&A** (`project-knowledge/query`).  
> In this C/W/D study, multi-agent **recommend synthesis [5–8]** is the **HTTP Call 2** product path (richer graph behind the same route). Chatbot/project-only Q&A is **HTTP Call 3**.

-|--------|
| **Document type** | Architecture vocabulary / agent role mapping (study only) |
| **Status** | Complete (docs only — no runtime rename required) |
| **Date** | 2026-08-11 |
| **Version** | 2.1.2 |
| **Application** | `haystack-fast-api` Multi-Agent Orchestrator (LangGraph) |
| **Question** | How do **Coordinator**, **Worker**, and **Delegator** map onto the existing Orchestrator + domain agents + in-process tools design? |
| **Authority** | **Authoritative for role vocabulary.** Dual-plane study remains authoritative for data planes, tool catalog, and sync. Implementation plan Phase 7 is authoritative for rollout steps. |
| **Related** | [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) §4.1 · [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) · [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) · [`implementation-plan.md`](./implementation-plan.md) Phase 7 |

---

## 1. Executive summary

### Question

Prior feasibility studies describe a **Multi-Agent Orchestrator** (LangGraph), **domain agents**, and **in-process tools**, but never name a **Coordinator / Worker / Delegator** model. Can that three-role vocabulary be mapped cleanly without redesigning the architecture?

### Verdicts

| Question | Result |
|----------|--------|
| Is C/W/D already specified in Feasibility_Study? | **No** (until this document) |
| Mapping onto existing Orchestrator design without redesign? | **GO** |
| Rename runtime LangGraph nodes immediately? | **No** — docs first; optional later for logs |
| **[4] indexing** as LLM Worker agent? | **No** — **forced non-agent tool edge** under Coordinator |
| **Delegator** shape | **Explicit router node** (not edges-only) |
| Fleet / pricing parallelism | **Fan-out Workers per need** |
| C/W/D labels in logs/metrics? | **Yes** |

**Overall:** **GO as a naming / observability layer** over the existing design. Primary architecture terms remain **Orchestrator**, **tools**, and **synthesis**. Coordinator / Worker / Delegator are **aliases** for policy, domain nodes, and routing — they must not weaken hard rules (in-process tools only, tool-free synthesis, **[4]** gate).

---

## 2. Definitions

| Role | Responsibility | Must not |
|------|----------------|----------|
| **Coordinator** | Owns graph policy, mode (`qa` vs `recommend`), **[4]** success gate, shared state, final synthesis **[8]** / response shape | Embed fleet SQL, free Cypher, pricing math; invent `asset_id` or rates; put raw file bytes into LLM context |
| **Worker** | Domain agent node for one concern; may call **allowlisted** in-process tools for that concern | Own global ranking policy; call tools outside allowlist; skip the **[4]** gate; invent inventory or prices |
| **Delegator** | **Explicit router node**: chooses which Worker (or Worker fan-out) runs next and with what sub-task (e.g. which `need_id`) | Execute backends itself; become a mega-agent that does research + fleet + pricing in one node; bypass **[4]** |

### 2.1 Not agent roles (disambiguation)

| Term | What it is | Relation to C/W/D |
|------|------------|-------------------|
| **In-process tool** | Allowlisted Python callable (SQL, KG, pricing, indexing pipeline) | **Execution** layer — invoked by Workers or by Coordinator gate **[4]**; not Coordinator/Worker/Delegator |
| **Job worker** | Background process: 202 jobs, Neo4j populate, Uvicorn workers | **Ops** — never an agent Worker |

```text
Agent Worker  ≠  Job worker  ≠  In-process tool
```

---

## 3. Map onto documented layers

| C/W/D role | Existing Feasibility_Study term | Concrete as-built / target |
|------------|----------------------------------|----------------------------|
| **Coordinator** | Multi-Agent Orchestrator (LangGraph) + synthesis **[8]** | `StateGraph` / `run_project_knowledge_agents`; target recommend graph; tool-free synthesis |
| **Worker** | Domain agents: research / fleet / pricing / rank | Stage-1: `research_agent`, `graph_agent`. Target: project **[5]**, fleet **[6]**, pricing **[7]** (fan-out per need) |
| **Delegator** | Sequencing policy (now elevated to **explicit router node**) | After **[4]** (and after needs exist): route to Workers; skip optional paths (e.g. empty Neo4j) without free ReAct |
| **Tools** | In-process tool module | `app/agents/tools.py` + shared catalog — dual-plane §4.6 |
| **[4] index gate** | Forced indexing tool | **Non-agent** LangGraph node / edge under Coordinator — **not** a Worker |

---

## 4. Pipeline [4]–[8] in C/W/D terms

### 4.1 Target recommend graph

```text
┌─────────────────────────────────────────────────────────────────┐
│ COORDINATOR (LangGraph Orchestrator)                            │
│  mode · shared state · [4] gate · synthesis [8] · response DTO  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
              [4] FORCED NON-AGENT TOOL EDGE
              run_indexing_from_request / IndexingIngestService
              (no LLM · no Worker label · files never in LLM context)
                             │
                    success only
                             ▼
              DELEGATOR (explicit router node)
              · after needs known: fan-out plan per need_id
              · optional skip (e.g. Neo4j empty → no graph tool)
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   WORKER [5]         WORKER [6]×N       WORKER [7]×N
   project / needs    fleet / Neo4j      pricing
   (once / shared)    per need_id        per need_id
          │                  │                  │
          ▼                  ▼                  ▼
   project_* tools    retrieve_* /       predict_asset_price
                      neo4j_* / avail.
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
              COORDINATOR synthesis [8]  (tool-free merge)
              results_by_need[] — no invent asset_id / rates
```

### 4.2 Step table

| Step | C/W/D label | Notes |
|------|-------------|--------|
| **[4]** indexing | `coordinator.gate` | **Forced non-agent tool edge** under Coordinator. Not a Worker. Gate: no recommend Workers until success. **As-built (S3 / FR-IX-026):** `app/agents/indexing_gate.py` (`START→index_gate→END`) + `run_indexing_from_request`; env `INDEXING_VIA_AGENT_GATE` default **off** (direct service). |
| **[5]** project / needs | `worker` | Shared / once per run; tools: `project_vector_search`, `project_kg_query`, `decompose_project_needs` |
| **Delegator** | `delegator` | Explicit router; builds per-`need_id` work plan; may skip optional backends |
| **[6]** fleet + graph | `worker` | **Fan-out per need**; tools: `retrieve_fleet_*`, `check_booking_availability`, `neo4j_cypher_read` |
| **[7]** pricing | `worker` | **Fan-out per need** (per candidate set for that need); tool: `predict_asset_price` only for rates |
| **[8]** synthesis | `coordinator.synthesis` | Tool-free; merge tool hits into `results_by_need` / recommend DTO |

### 4.3 Product decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **[4] placement** | **Forced non-agent tool edge** under Coordinator | Indexing is deterministic pipeline work; must not depend on LLM tool-calling whim; aligns with dual-plane “forced tool **[4]**” and Phase 3.2 `START → index_tool → …` |
| **Delegator** | **Explicit router node** | Supports skip/branch (e.g. Neo4j unavailable) and **per-need fan-out** without free-form ReAct mega-agent |
| **Parallelism** | **Fan-out Workers per need** | Multi unit-need loop; isolates failures/warnings per need; matches recommend DTO `results_by_need` |
| **Observability** | **C/W/D labels in logs/metrics** | `role=coordinator|worker|delegator` (+ `need_id` on fan-out Workers) |

---

## 5. Stage-1 as-built (today)

**Indexing gate [4] (S3 as-built, separate from Q&A graph):** optional `run_indexing_gate` / `INDEXING_VIA_AGENT_GATE`; default Call 1 still hits `IndexingIngestService` directly. Q&A graph below remains post-ingest Call 3.

```text
COORDINATOR: build_project_knowledge_graph / run_project_knowledge_agents
DELEGATOR:   (implicit) fixed edges only — no explicit router node yet
WORKER:      research_agent  → project_vector_search
WORKER:      graph_agent     → project_kg_query
COORDINATOR: synthesis_agent → markdown Q&A (no assets / prices)
```

As-built has **no [4] inside the Q&A graph** (ingest already happened on Call 1) and **no fan-out**. Target recommend graph adds forced **[4]** when ingest is agent-fronted, explicit Delegator, and per-need Workers.

---

## 6. Responsibility matrix

| Concern | Coordinator | Delegator | Worker | Tool |
|---------|-------------|-----------|--------|------|
| Mode `qa` / `recommend` | Own | — | — | — |
| Force **[4]** before recommend | Own (gate node) | Refuse route if gate failed | Must not run fleet/price if gate failed | Execute index pipeline |
| Choose next Worker / need slice | Policy | **Own (router)** | — | — |
| Project vector / KG read | — | Route to [5] | Invoke | Execute |
| Fleet SQL / Neo4j read | — | Route [6]×N | Invoke | Execute |
| Price prediction | When / which candidates (policy) | Route [7]×N | Invoke | Model + clamp |
| Rank + final JSON | **Own [8]** | — | May draft per-need rationale only if policy allows | No |
| Invent `asset_id` / `daily_rate` | **Forbidden** | **Forbidden** | **Forbidden** | N/A (tools return real hits or empty) |

---

## 7. Delegator: explicit router (not free ReAct)

| Mode | Allowed? | Notes |
|------|----------|--------|
| **Explicit router node** with allowlisted branches | **Yes (target)** | e.g. after needs: for each `need_id` → fleet Worker → pricing Worker; skip Neo4j tool if graph empty |
| Fixed sequential edges only | Acceptable interim | Stage-1 today; Phase 7 may start sequential then add router |
| Free LLM “plan anything” Delegator | **No** | Violates forced order, allowlists, and auditability |

Router inputs (illustrative): `indexing_ok`, `needs[]`, `neo4j_available`, `mode`.  
Router outputs: ordered work items `{ worker_kind, need_id?, tool_allowlist }`.

---

## 8. Fan-out Workers per need

```text
needs = [need_A, need_B, need_C]   # from [5] / decomposer

Delegator expands:
  for need in needs:
    enqueue fleet_worker(need)
    enqueue pricing_worker(need)   # after that need’s fleet candidates exist

Coordinator synthesis [8]:
  merge per-need tool hits → results_by_need[]
  partial failure → item null + warning for that need (not whole envelope unless hard policy)
```

| Rule | Detail |
|------|--------|
| Isolation | One need’s empty fleet or pricing failure does not invent substitutes |
| Ordering within need | Fleet **[6]** before pricing **[7]** for that `need_id` |
| Across needs | Fan-out may be parallel **if** tool backends and rate limits allow; sequential fan-out is OK for CI simplicity |
| Traces | Each Worker invocation logs `role=worker`, `worker_kind`, `need_id` |

---

## 9. Logs and metrics (C/W/D labels)

**Target structured fields** (names illustrative):

| Field | Example |
|-------|---------|
| `role` | `coordinator` \| `delegator` \| `worker` |
| `node` | `index_gate` \| `router` \| `fleet_worker` \| `synthesis` |
| `need_id` | present on fan-out Workers |
| `tool` | tool name when a tool is invoked |
| `gate` | `indexing_ok=true/false` |

Metrics suggestions: count by `role`+`node`; latency histograms per Worker kind; fan-out width (`needs` count); gate failure rate for **[4]**.

Runtime node **names** in code may stay `research_agent` / `graph_agent` until a later rename; **logs should still emit C/W/D `role`** when the recommend graph is built.

---

## 10. Agent instruction templates

Every **agent role** in this multi-agent design MUST be specified with **A + B + C + D + E + F + G + H + I + J + K + L**:

| Part | Name | Purpose |
|------|------|---------|
| **A** | Defining objectives | Outcome, core functions, constraints, behavior |
| **B** | Task specifications | Steps, expected outputs, potential challenges |
| **C** | Contextual awareness | Multi-layer environment/user/situation awareness + adaptation |
| **D** | State space representation | How the agent encodes, reads, updates, and constrains run state |
| **E** | Environment modeling | External systems, static rules, dynamic conditions the agent may interact with |
| **F** | Integration and interaction patterns | **F-1** event-driven updates + **F-2** state validation and consistency |
| **G** | Monitoring and adaptation | **G-1** metrics/traces + **G-2** bounded adaptation under load/failure |
| **H** | Agent memory architecture | **H-1** short-term · **H-2** long-term · **H-3** episodic — stores, lifetime, R/W/clear |
| **I** | Context management | **I-1** context hierarchy · **I-2** context switching (preserve / restore / merge) |
| **J** | Integration with decision-making | **J-1** information retrieval · **J-2** pattern recognition · **J-3** decision optimization |
| **K** | Workflow optimization | **K-1** task class/priority · **K-2** resources · **K-3** dynamic seq/parallel adjustment |
| **L** | Sequential and parallel processing | **L-1** sequential · **L-2** parallel · **L-3** hybrid / mode participation |

These templates are **target prompt contracts** (Phase 7.7). As-built Stage-1 lives in `app/agents/prompts.py` / `app/agents/state.py` and is mapped in §10.8.

**Domain:** heavy-equipment rental recommend / project-spec Q&A — not generic travel-agent copy.

**Contextual awareness (definition):** the agent’s duty to **read, respect, and adapt to** multi-layered circumstances (platform, tenant, project-spec, commercial request, cross-agent state, and — via tools — Postgres-Haystack fleet tables) without inventing missing facts. It is more than “call a tool once”; it is understanding *which* context applies and *how* partial or changing context changes the next action.

**State space representation (definition):** how an agent **perceives, maintains, and updates** a structured snapshot of the situation—known facts, legal actions, and allowed outcomes—without unnecessary complexity or invented fields. **C** names *which world layers matter*; **D** names *how they are encoded and mutated* in LangGraph run state.

**Environment modeling (definition):** creating a clear representation of the **world outside** local state—systems/services the agent may use, **rules** governing those interactions, and **changing conditions** it must monitor. Every agent’s **E** answers: (1) What can I interact with? (2) What rules constrain me? (3) What dynamics must I watch? **E** is partitioned by role so no single agent holds every integration point.

**Integration and interaction patterns (definition):** how agents **signal** each other and the environment (**F-1 event-driven updates**) and how they **guard** state changes (**F-2 validation and consistency**) so the system stays accurate without busy-polling or illegal transitions. **D** defines *what* may be written; **F** defines *when* writes fire and *whether* they are allowed.

**Monitoring and adaptation (definition):** **G-1** tracks health and effectiveness (latency, quality, resources, errors, outcome proxies) via metrics and traces; **G-2** adjusts behavior under those signals **within hard rules** (no invent fleet/rates, gate intact, tool-free synthesis). Completes the loop: state + environment + integration stay reliable as load and data change.

**Agent memory architecture (definition):** how each agent uses **three memory kinds**—**H-1 short-term (working)**, **H-2 long-term (knowledge base)**, **H-3 episodic (interaction history)**—including lifetime, who may read/write/clear, and retrieval rules. **D** is the *schema* of working memory; **H** assigns that schema (and durable stores) to memory *systems*. Fleet long-term data lives in **`postgres_haystack`**, which is a **read mirror synced from `postgres-primary`** (Spring OLTP SoT)—agents never treat the mirror as write SoT.

**Context management (definition):** how the agent keeps **appropriate awareness of the current situation and relevant history** while moving through multi-step recommend/Q&A work. **I-1 Context hierarchy** separates global / session / task scopes; **I-2 Context switching** covers preserve, restore, and merge when the graph moves between steps or needs (fan-out). **C** says *what* to be aware of; **I** says *how context is scoped and transitioned* without losing critical facts or inventing missing ones.

**Integration with decision-making (definition):** how **memory (H)** and **context (I)** feed each agent’s decisions via **J-1 information retrieval**, **J-2 pattern recognition**, and **J-3 decision optimization**. Decisions stay within role authority and **tool-backed** options—optimization never invents `asset_id` or rates.

**Workflow optimization (definition):** how the multi-agent graph chooses **sequential vs parallel** execution, **task order**, and **resource use** under dependencies and load (**K-1/K-2/K-3**). **J** decides *what* option to pick; **K** decides *how work is scheduled*. Never “optimize” by inventing stock, skipping the gate, or skipping availability when dates are set.

**Sequential and parallel processing (definition):** the two primary **execution modes** in agentic workflows. **L-1 Sequential** runs dependent steps in order; **L-2 Parallel** runs independent work concurrently under caps; **L-3 Hybrid** is how each role participates in mixed DAGs. **K** sets the overall schedule and resources; **L** states, per agent, what *must* be sequential vs what *may* be parallel (travel flight-before-hotel → fleet-before-price within need).

### 10.0 Shared context layers (L1–L7)

All agents reference these layers by id. Agents **consume** only the layers they are allowed; they do not own foreign systems of record.

| Layer | Name | Typical contents |
|-------|------|------------------|
| **L1** | Platform / environment | `mode` (`qa`\|`recommend`), feature flags, tool allowlists, `neo4j_available`, model deploy / stub vs live, CI |
| **L2** | Tenant / user | `user_id`, auth boundary, multi-tenant filters (`user_id` / `ingest_id` on project chunks) |
| **L3** | Project-spec session | `ingest_id`, `indexing_ok` **[4]**, DocumentStore + **KG-1** session; project facts **only via project tools** (never raw file bytes in LLM) |
| **L4** | Request / commercial situation | Query or Call 2 recommend options; rental `start_date` / `end_date`; budget **if present**; `include_pricing`; correlation / idempotency on the wire |
| **L5** | Cross-agent graph state | `needs[]`, `work_plan[]`, `candidates_by_need`, `prices_by_need`, `research_notes` / `graph_notes`, `tool_traces`, `warnings` |
| **L6** | Fleet / market (Postgres-Haystack `heavy_rental`) | Read-only mirror tables (below) + optional Neo4j KG-2 projection freshness |
| **L7** | Pricing situation | `model_version`, clamp bounds (`minDailyRate`/`maxDailyRate` from **assets**), fallback category table, `period_utilization` / `lead_time_days` from **bookings** |

#### 10.0.1 Postgres-Haystack `heavy_rental` tables (L6 / recommend persistence)

Host: **`postgres_haystack`** · DB: **`heavy_rental`** (app `POSTGRES_DB`). **Long-term fleet memory for agents is this mirror**, continuously **synced from `postgres-primary`** (Spring OLTP write SoT) by service **`postgres_haystack_sync`** (eventual consistency — mirror lag is part of context). Agents **read** via tools only; they **never write** primary or treat haystack as SoT.

| Table | Contextual role for agents | Typical consumers |
|-------|----------------------------|-------------------|
| **`assets`** | Fleet inventory: category, condition, capacity, platform height, rate guardrails (`baseDailyRate` / `minDailyRate` / `maxDailyRate`), asset identity | Worker [6] retrieve/filter; Worker [7] feature rows + clamp |
| **`bookings`** | Rental windows + status; availability overlap; live util / lead-time inputs | Worker [6] availability; Worker [7] `period_utilization` / `lead_time_days` |
| **`payments`** | Commercial payment state linked to bookings (read-only context if product allows) — **not** a price oracle for inventing rates | Coordinator warnings / audit only if exposed via allowlisted tool; never invent payment success |
| **`rental_plan`** | Plan / package terms that may constrain duration tiers or commercial options | Worker [6]/[7] when tool exposes plan constraints; Coordinator rationale only from tool hits |
| **`recommendation_items`** | Persist ranked line items / `mlPredictedPrice` after recommend — **output sink**, not invent source mid-run | Coordinator handoff / Spring persistence path (service layer) |
| **`ai_recommendations`** | Parent AI recommendation envelope (ids, timestamps, user/project linkage) — **output / audit**, not fleet SoT | Coordinator / HTTP layer after [8] |

**Hard rules for DB context:**

- Access only through **allowlisted in-process tools** (read-only SQL on the mirror) — no free-form SQL in agent nodes.  
- Mirror is **not** primary OLTP write SoT; do not treat lag as “asset does not exist forever.”  
- **`assets` + `bookings`** are the primary live fleet context for Workers [6]/[7].  
- **`recommendation_items` / `ai_recommendations`** are primarily **write/read-after-write** for the recommend product path — agents must not invent rows that were never produced by tools/synthesis.  
- **`payments` / `rental_plan`**: use only if an allowlisted tool returns them; absence → do not invent commercial terms.  
- Column casing may be camelCase or snake_case in real schema — tools normalize; agents consume tool DTOs.

**Domain analogues to “travel contextual awareness”:**

| Travel example | Heavy-rental analogue |
|----------------|----------------------|
| Destination intelligence | Project-spec site/constraints (L3 tools) + **`assets`** category/capacity/height fit |
| Dynamic adaptation (cancelled flight) | **`bookings`** overlap → unavailable asset; re-filter alternatives from **`assets`** tool hits only |
| Cultural competence | Site rules in project-spec (indoor, noise, soil) + fleet **condition** / rental_plan constraints |

### 10.0.2 State space vs environment

| Concept | Meaning in this design |
|---------|------------------------|
| **State** | LangGraph shared dict / TypedDict for **one run** (qa or recommend). Moment-in-time knowledge the graph nodes pass forward. |
| **Environment** | Tools, allowlists, policies, Postgres-Haystack **`heavy_rental`** mirror, Neo4j, ML model artifacts, Spring HTTP — *outside* the agent “mind,” observed only via tools/flags |
| **Rule** | DB tables are **not** LangGraph state. Tools project rows into **normalized DTO fields** in state (`fleet_by_need`, etc.). |

### 10.0.3 Shared state schemas

#### As-built qa state (`ProjectKnowledgeAgentState`)

From `app/agents/state.py`:

| Field | Role |
|-------|------|
| `user_id`, `ingest_id` | Tenant + project session |
| `query`, `top_k` | Request |
| `research_notes`, `research_hits` | Vector Worker output |
| `graph_notes`, `graph_hits` | KG Worker output |
| `final_answer`, `sources_used` | Coordinator (qa) output |
| `tool_traces` | Audit |

#### Target recommend state partitions (travel → rental)

| Travel state example | Heavy-rental partition | Main keys |
|----------------------|------------------------|-----------|
| Customer profile | **Run / tenant / request** | `run.user_id`, dates, budget?, `include_pricing` |
| Travel context | **Project + fleet context** | `project.needs`, `fleet_by_need` (from **`assets`/`bookings`** tools) |
| Booking state | **Recommendation run** | `prices_by_need`, `recommendation.results_by_need`, `warnings`, `persistence.*` |

#### Target `RecommendAgentState` (S7.0 **as-built** module; graph not wired yet)

Runtime: `app/agents/recommend_state.py` — `RecommendAgentState`, `validate_state_transition`, `apply_partition_write`, `write_fleet_slice`, `write_price_rows`.

```json
{
  "run": {
    "mode": "recommend",
    "user_id": "u-42",
    "ingest_id": "ing-9f3a",
    "indexing_ok": true,
    "start_date": "2026-09-01",
    "end_date": "2026-09-14",
    "include_pricing": true
  },
  "project": {
    "research_notes": "...",
    "graph_notes": "...",
    "needs": [
      {
        "need_id": "need_access",
        "equipment_type_hint": "scissor_lift",
        "constraints": { "platform_height_m": 8 }
      }
    ]
  },
  "work_plan": [
    {
      "worker_kind": "fleet",
      "need_id": "need_access",
      "tool_allowlist": [
        "retrieve_fleet_assets",
        "filter_fleet_candidates",
        "check_booking_availability"
      ]
    },
    {
      "worker_kind": "pricing",
      "need_id": "need_access",
      "tool_allowlist": ["predict_asset_price"]
    }
  ],
  "fleet_by_need": {
    "need_access": {
      "candidates": [
        {
          "asset_id": "AST-SL-001",
          "category": "scissor lift",
          "platform_height": 10.0,
          "condition": "GOOD",
          "min_daily_rate": 120,
          "max_daily_rate": 280
        }
      ],
      "unavailable": [],
      "source_tables": ["assets", "bookings"]
    }
  },
  "prices_by_need": {
    "need_access": [
      {
        "asset_id": "AST-SL-001",
        "daily_rate": 185,
        "currency": "SGD",
        "was_clamped": false,
        "model_version": "…"
      }
    ]
  },
  "recommendation": {
    "results_by_need": [],
    "warnings": []
  },
  "tool_traces": [],
  "persistence": {
    "ai_recommendation_id": null,
    "recommendation_item_ids": []
  }
}
```

| State path | Context layers | Environment sources |
|------------|----------------|---------------------|
| `run.*` | L1, L2, L3 gate, L4 | HTTP request, **[4]** gate |
| `project.*` | L3, L5 | Project tools / KG-1 |
| `work_plan` | L1, L5 | Delegator only |
| `fleet_by_need` | L5, L6 | Tools → **`assets`**, **`bookings`** (+ optional **`rental_plan`**) |
| `prices_by_need` | L5, L7 | `predict_asset_price` (+ util from **`bookings`**) |
| `recommendation.*` | L5 | Coordinator merge only |
| `persistence.*` | — | Service write to **`ai_recommendations`**, **`recommendation_items`** after [8] |

**Global state invariants:**

1. No `asset_id` in `recommendation` unless present in `fleet_by_need` tool-backed candidates.  
2. No `daily_rate` unless present in `prices_by_need` (or documented fallback recorded in traces).  
3. Fleet/pricing Workers run only if `run.indexing_ok == true`.  
4. Each Worker writes **only its partition** (no cross-slice invent).  
5. State holds DTOs, not raw SQL rows.

### 10.0.4 Shared environment model (static + dynamic)

The multi-agent **environment** is everything outside a single run’s LangGraph state. Agents do not embed ad-hoc connections; they use **allowlisted in-process tools** and flags. Full dual-plane / resilience detail lives in sibling studies; this section is the agent-facing map.

#### Static environment elements

| Category | Content in this product |
|----------|-------------------------|
| **Business rules / constraints** | **[4]** gate before recommend fleet/pricing tools; synthesis **tool-free**; no invent `asset_id`/rates; KG-1 ≠ fleet SoT; multi-tenant `user_id`/`ingest_id` filters; Spring = HTTP client only; primary OLTP ≠ Haystack mirror for writes; never silent-zero prices; allowlisted tools only; **no FastMCP** tool server |
| **System interfaces** | In-process tool module; Postgres-Haystack **`heavy_rental`** (read-only SQL tools); InMemory/Pgvector project store; KG-1 session; Neo4j KG-2 constrained reads; `predict_asset_price` / `pricing_client`; indexing pipeline / optional SuperComponent; Spring REST Call 1–3; correlation / idempotency headers on the wire |
| **Error / quota protocols** | Tool failure → warning + documented fallback; KG hard-fail on ingest; long work → 202 jobs / SSE (resilience study); `PROJECT_AGENT_MODE=stub` for CI |

#### Dynamic environment elements

| Category | Content in this product |
|----------|-------------------------|
| **Resource availability** | **`assets`** inventory/condition; **`bookings`** overlaps; `postgres_haystack_sync` lag; Neo4j projection freshness; ML model artifact presence; project session TTL |
| **Commercial / market signals** | Live utilization / lead-time; per-asset clamp bounds; optional **`rental_plan`** / **`payments`** if tool-exposed |
| **System performance / health** | Tool/DB latency; empty result vs hard error; LLM live vs stub; Neo4j populate / index job queues |

#### Travel environment → heavy-rental mapping

| Travel example | This design |
|----------------|-------------|
| Airline / hotel booking APIs | In-process tools → **`assets`**, **`bookings`**, project vector/KG tools |
| Payment processors | **`payments`** only if allowlisted tool returns data; Spring owns payment SoT for bookings |
| Booking policies / SLAs | OpenSpec + product rules; availability filters; synthesis no invent |
| Price / inventory fluctuations | Re-invoke tools each run; mirror lag; clamp + category fallback |
| Weather / local events | Project-spec constraints via **project tools** (not a weather API) |

#### Complexity mitigation (purpose-built agents)

Too many integration points in one agent creates a brittle mega-agent. This architecture **partitions the environment by role**:

| Role | Environment surface (narrow) |
|------|------------------------------|
| Coordinator [8] | State + response DTO (+ optional persist service) — **no** fleet SQL |
| Delegator | Capability flags + allowlists only |
| Worker [5] | Project store + KG-1 tools |
| Worker [6] | **`assets`/`bookings`** (+ optional Neo4j / rental_plan) |
| Worker [7] | Pricing model tool only |
| Fan-out | Parallel/sequential per-need Workers coordinate via shared state, not one agent with all edges |

### 10.0.5 Integration and interaction patterns (shared)

Success of state space (**D**) and environment modeling (**E**) depends on how components **interact**. Two patterns are mandatory for every agent.

#### F-1 Event-driven updates

Prefer **discrete events** (tool results, gate outcomes, node completion, job/SSE signals) over agents **busy-polling** Postgres or Neo4j inside LLM loops.

**As-built:** LangGraph **sequential edges** act as implicit completion events (`research_agent` → `graph_agent` → `synthesis_agent`).  
**Target recommend:** same pattern—node completion + tool return values are the primary in-request “event bus.” External **C2 jobs / SSE** may re-enter the system later; Phase 7 does **not** require Kafka.

| Event type (illustrative) | Source | Typical consumer | State / action effect |
|---------------------------|--------|------------------|------------------------|
| `INDEXING_SUCCEEDED` / `INDEXING_FAILED` | [4] gate | Coordinator, Delegator | `run.indexing_ok`, `ingest_id` |
| `PROJECT_RESEARCH_DONE` | Research Worker | Graph Worker / [5] | `project.research_*` |
| `PROJECT_KG_DONE` | Graph Worker | Decomposer / Coordinator | `project.graph_*` |
| `NEEDS_DECOMPOSED` | Worker [5] | Delegator | `project.needs[]` |
| `WORK_PLAN_READY` | Delegator | Workers [6][7] | `work_plan[]` |
| `FLEET_CANDIDATES_READY` / `FLEET_EMPTY` | Worker [6] | Pricing / Coordinator | `fleet_by_need[need_id]` |
| `BOOKING_OVERLAP_DETECTED` | availability tool via [6] | Worker [6] | candidate → `unavailable[]` |
| `PRICE_READY` / `PRICE_FALLBACK` / `PRICE_FAILED` | Worker [7] | Coordinator | `prices_by_need[need_id]` |
| `SYNTHESIS_DONE` | Coordinator | HTTP / persist | `recommendation.*` |
| `NEO4J_UNAVAILABLE` / `MIRROR_LAG_WARNING` | env / tools | Delegator, Workers | strip tools / warn |
| `JOB_PROGRESS` / `JOB_SUCCEEDED` | C2 index/Neo4j jobs | Spring poll/SSE | out-of-band; optional re-entry |

**Travel → rental event mapping:**

| Travel example | This product |
|----------------|--------------|
| `FLIGHT_CHANGE` → check deps, notify | `BOOKING_OVERLAP_DETECTED` / fleet tool refresh → re-filter **`assets`**, warn Coordinator |
| `WEATHER_ALERT` → alternatives | Project constraint change or empty fleet → re-decompose or `item: null` + warning (via tools/state, not weather API) |

Illustrative handler shape (docs only—not runtime code):

```text
on_event(event, state, role):
  if event.type == "INDEXING_FAILED":
    state.run.indexing_ok = false
    refuse_recommend(state)
  elif event.type == "BOOKING_OVERLAP_DETECTED":
    move_candidate_to_unavailable(state, event.need_id, event.asset_id)
  elif event.type == "PRICE_FALLBACK":
    append_warning(state, event.need_id, "pricing_fallback")
  ...
  append tool_traces / role labels
```

#### F-2 State validation and consistency

Before applying a proposed state write:

```text
validate_state_transition(current, proposed, role):
  1. is_valid_transition(role, current → proposed)  # partition ownership (D)
  2. check_state_dependencies(proposed)             # e.g. prices need candidates
  3. validate_business_rules(proposed)            # gate, no invent, multi-tenant
  else: reject → warning or hard error (no partial corrupt write)
```

| Check | Heavy-rental examples |
|-------|------------------------|
| **Transition validity** | Fleet Worker writes only `fleet_by_need[need_id]`; cannot set `recommendation` |
| **Dependencies** | Pricing requires candidates for that need; synthesis rates ⊆ `prices_by_need`; within-need fleet before price (Delegator order) |
| **Business rules** | `indexing_ok` before fleet; no `asset_id` outside candidates; never silent-zero rates; project retrieve filtered by `user_id` |

**Travel validation → rental:**

| Travel | This product |
|--------|----------------|
| Payment received before confirm | Price tool success / fallback recorded before attaching rate |
| Seats still available | **`bookings`** availability tool |
| Hotel after flight arrival | Rental window on `run` + need; fleet then price order |
| Passport / policy ack | `user_id`/`ingest_id` present; DTO schema validation; gap warnings |

### 10.0.6 Monitoring and adaptation (shared)

Robust state (**D**), environment (**E**), and integration (**F**) require continuous **monitoring** and **bounded adaptation**. Complements §9 (C/W/D log labels).

#### G-1 Metric classes

| Class | Examples (this product) |
|-------|-------------------------|
| **Latency** | Node duration; tool latency; Call 2/3 p95 (recommend / Q&A); time from gate success to synthesis |
| **Quality / accuracy** | Empty-fleet rate; pricing clamp rate; fallback rate; schema validation fails; stub vs live mode mix |
| **Resource utilization** | Fan-out width (`needs_count`); DB pool; threadpool; LLM tokens/cost |
| **Errors / recovery** | Tool error rate; gate fail rate; F-2 reject rate; time-to-fallback after model miss |
| **Outcome / satisfaction proxies** | Per-need fill rate (`item` non-null); warning counts; Spring saga success; later operator feedback on recommendations (**not** invented scores) |

**Shared emission points:** `tool_traces` (`role`, `node`, `need_id`, `tool`, optional event type, duration_ms); `warnings[]`; pricing `was_clamped` / `model_version`; C2 job status / SSE.

#### G-2 Adaptation strategies (bounded)

| Strategy | Allowed | Forbidden |
|----------|---------|-----------|
| Graceful degrade | `item: null` + warning; skip Neo4j; pricing category fallback | Invent `asset_id` / rates to raise fill rate |
| Dynamic resources | Cap concurrent need Workers; 202 jobs for long index/Neo4j | Block recommend on full graph rebuild |
| Model lifecycle | Pin `model_version`; scheduled retrain (pricing Phase 3) | Silent zero prices |
| Route adjust | Delegator strips tools on unavailability flags | Free ReAct mega-agent |
| Feedback | Portal/operator feedback → prompt/policy versioning (later) | Agent auto-writes primary OLTP |

Travel “seasonal patterns / preference shifts” → rental: **`bookings`** utilization seasonality; project-spec re-index + tools for new constraints—not a weather API.

### 10.0.7 Agent memory architecture (shared)

Memory keeps interactions coherent. Three kinds (travel Working / Customer+KB / Episodic → rental backends):

| Kind | Purpose | Heavy-rental backends |
|------|---------|------------------------|
| **H-1 Short-term (working memory)** | Immediate workspace for **this graph run** | LangGraph state: as-built `ProjectKnowledgeAgentState`; target `RecommendAgentState` (`run`, `project`, `work_plan`, `fleet_by_need`, `prices_by_need`, `recommendation`, `tool_traces`) |
| **H-2 Long-term (knowledge base)** | Persistent knowledge across runs | **Project:** session registry + InMemory store (as-built) / **Pgvector** (I1) + **KG-1**. **Fleet:** Postgres-Haystack DB **`heavy_rental`** on host **`postgres_haystack`**, **synced from `postgres-primary`** via `postgres_haystack_sync` (eventual consistency / lag). Tables: **`assets`**, **`bookings`**, **`payments`**, **`rental_plan`**, etc. **Pricing:** model artifacts + clamp policy. |
| **H-3 Episodic (interaction history)** | Discrete past outcomes | Current-run `tool_traces` / `warnings`; after Call 2 recommend persist: **`ai_recommendations`**, **`recommendation_items`**; logs/metrics retention. Full multi-turn chat history **not** required for Phase 7 unless product adds a chat store. |

#### Lifetimes and clear rules

| Store | Lifetime | Clear / update |
|-------|----------|----------------|
| Working memory | Single LangGraph run (Call 2 recommend or Call 3 Q&A) | Discarded at run end |
| Project session LTM | Until discard/TTL; key `(user_id, ingest_id)` | Explicit discard; **does not** delete fleet mirror |
| Fleet LTM (`postgres_haystack`) | Durable **mirror** of primary | Updated by **`postgres_haystack_sync`** from **`postgres-primary`**; agents **read-only** via tools |
| Primary OLTP (`postgres-primary`) | Durable SoT for fleet/bookings writes | Spring / domain services only — **not** agent write path |
| Pricing model LTM | Deploy/version | Retrain job / artifact pin |
| Episodic recommend rows | Durable after persist | App/Spring lifecycle |
| Traces / logs | Run + retention policy | Log policy |

#### Memory hard rules

1. Read fleet/project LTM **only via allowlisted tools** (no free SQL in agent nodes).  
2. Mid-run writes go to **working memory partitions** only (D ownership).  
3. **`postgres_haystack` is not write SoT** — it is synced from **`postgres-primary`**; mirror lag is expected (G/F/E).  
4. Episodic **`ai_recommendations` / `recommendation_items`** are **outputs**, not invent sources for new fleet.  
5. Multi-tenant isolation on project LTM (`user_id` / `ingest_id`).  
6. Clearing a project session ≠ truncating fleet tables.

#### Travel → rental memory mapping

| Travel example | This product |
|----------------|--------------|
| WorkingMemory: search criteria, booking in progress | Working: `run.*`, `project.needs`, fan-out slices, in-flight traces |
| CustomerMemory / TravelKnowledge | Project LTM (spec store + KG-1); fleet LTM (`assets`/`bookings` on **haystack mirror**); pricing model |
| EpisodicMemory: past trips, layover issues | Past recommends + tool_traces patterns; empty-fleet episodes |

#### Context flow (brief)

```text
LTM (primary → sync → postgres_haystack | project store/KG-1 | model)
        │  allowlisted tools
        ▼
Working memory (LangGraph state)  ←── Workers / Delegator / Coordinator partitions
        │
        ▼
Episodic: tool_traces (run) → optional persist ai_recommendations / recommendation_items
```

### 10.0.8 Context management (shared)

Effective context management keeps multi-step project-spec → recommend journeys coherent (travel multi-city trip analogue → multi-**need** equipment recommend with dates, budget, and fleet constraints).

#### I-1 Context hierarchy

| Level | Travel example | Heavy-rental content |
|-------|----------------|----------------------|
| **Global context** | System settings, travel alerts | Mode (`qa`\|`recommend`), feature flags, tool allowlists, `neo4j_available`, model deploy/stub, gate policy, multi-tenant rules, **mirror lag** awareness |
| **Session context** | Active customer interaction, searches | `user_id`, `ingest_id`, project session (DocumentStore + KG-1), Call 3 query thread, rental window / budget **if present**, correlation ids |
| **Task context** | Current booking step, related bookings | Current graph node; `need_id` under fan-out; step in [4]→[5]→Delegator→[6]→[7]→[8]; dependencies (fleet before price within need); active tool allowlist for this Worker |

Maps onto L1–L7 (§10.0): global ≈ L1; session ≈ L2–L4 + project LTM; task ≈ L5 slices + current Worker kind.

**Scenario (travel multi-city → multi-need rental):** Customer/project needs elevated indoor work **and** earthmoving in one window, budget optional, dates set. Global: recommend mode + pricing on. Session: same `ingest_id` project-spec. Task: Delegator fans out `need_access` then `need_earthwork`; each fleet/pricing Worker holds only its `need_id` task context while session/global remain stable.

#### I-2 Context switching

| Operation | Meaning in this design |
|-----------|------------------------|
| **Preserve** | Before leaving a node/need, required fields already committed to working memory (D partitions) + `tool_traces`; do not drop `indexing_ok`, `user_id`, dates |
| **Restore** | Next node reads shared state (not re-upload of project file); fan-out Worker restores only its `need_id` slice + shared `run`/`project.needs` |
| **Merge** | Coordinator [8] merges per-need fleet/price contexts into `results_by_need`; resolve conflicts by **tool precedence** (fleet/price tools win over LLM narrative); state Vector vs Graph conflicts explicitly in Q&A |

**Switch points:** [4]→[5]; [5]→Delegator; Delegator→[6]×N / [7]×N; Worker→Worker within need; all→Coordinator; Call 1 session later used by Call 2 recommend / Call 3 Q&A (restore project session by `ingest_id`).

**Hard rules for context management:**

1. Never invent context to “fill gaps” (budget, assets, rates).  
2. Task switch must not lose session tenancy keys.  
3. Merge must not override tool-backed numbers with free text.  
4. Context from **`postgres_haystack`** is mirror-scoped (lag possible)—do not assume primary instantaneous consistency.  
5. Clearing task context (end of Worker) ≠ clearing session project LTM.

### 10.0.9 Integration with decision-making (shared)

Memory and context exist to support **decisions**. Three mechanisms (travel A1–A3 → rental):

#### J-1 Information retrieval

| Sub | Travel | This product |
|-----|--------|--------------|
| History / preferences | Customer profile | Project-spec via vector/KG tools; optional past **`ai_recommendations`** as **soft prior only** (never fleet SoT) |
| Similar past cases | Past trips | Prior recommends / `tool_traces` patterns; empty-fleet episodes |
| Current + historical | Session + profile | STM + LTM tools (**`postgres_haystack`←`postgres-primary`**) + optional episodic |
| Filter / prioritize | Relevance | Allowlists; `need_id` scope; top-k; tool hit order—not invent |

#### J-2 Pattern recognition

| Pattern class | This product |
|---------------|--------------|
| Interaction patterns | Q&A tool sequences; recommend fan-out width |
| Successful match patterns | Need type → category that later booked (if episodic available) |
| Issue patterns | **`bookings`** overlap clusters; repeated empty fleet; high clamp/fallback |
| Seasonal / demand | `period_utilization` / booking density—not weather API |

#### J-3 Decision optimization

| Factor | This product |
|--------|--------------|
| Weighted options | Rank **only among STM candidates** (fit, availability, price) |
| Constraints | Project site/height + dates + budget if present + clamp bounds + gate |
| Balance | Project needs vs mirror stock—**never invent** to please |
| Risk mitigation | `item: null` + warning; price fallback; refuse if gate fail |

**Hard rule:** Optimization **never creates** `asset_id` or `daily_rate` absent from tool-backed STM.

#### Decision authority by role

| Role | May decide | Must not decide |
|------|------------|-----------------|
| **Coordinator** | Final rank/merge among priced candidates; refuse path; Q&A answer | Free SQL; invent stock |
| **Delegator** | Work plan, allowlists, skips, fan-out | Execute backends; invent needs |
| **Worker [5]** | Need set grounded in project tools | Fleet selection / prices |
| **Worker [6]** | Candidate set + availability filter | Prices; cross-need rank |
| **Worker [7]** | Rate via model/fallback only | Invent candidates; global rank |

### 10.0.10 Workflow optimization (shared)

Combine sequential and parallel patterns under dependencies, SLAs, and resources (travel multi-component booking → multi-**need** recommend).

#### Default recommend DAG

```text
[4] gate ──seq──► [5] project ──seq──► Delegator
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼  (parallel across needs, CAP)
              [6] fleet(n1)           [6] fleet(n2)           [6] fleet(nN)
                    │                       │                       │
                    ▼ seq                   ▼ seq                   ▼ seq
              [7] price(n1)           [7] price(n2)           [7] price(nN)
                    └───────────────────────┼───────────────────────┘
                                            ▼ barrier
                                      [8] Coordinator synthesis
```

**As-built Q&A:** `research → graph → synthesis` (fully sequential).

#### K-1 Task classification and prioritization

| Task | Depends on | Class | Priority |
|------|------------|-------|----------|
| [4] Index gate | Request + files | Critical path, sequential | P0 |
| [5] Project | Gate (recommend) | Critical path, once | P0 |
| Delegator plan | Needs | Critical path | P0 |
| [6] Fleet × need | Plan + need | Parallelizable across N | P1 |
| [7] Price × need | Fleet slice same need | Sequential after [6] within need | P1 |
| [8] Synthesis | Worker outputs (partial OK) | Barrier / final | P0 |

**Dependency analysis:** critical path must not skip gate or within-need fleet→price order. **Data flow:** tools → STM partitions → merge. **Temporal:** rental window on session; long index → async job (C2), not silent skip.

#### K-2 Resource management

| Resource | Management |
|----------|------------|
| App CPU/memory | `run_in_threadpool`; bound fan-out concurrency |
| Postgres haystack | Read-only pool; avoid unbounded N×queries; batch where tools allow |
| LLM | Stub in CI; bound rationale generation |
| Long work | 202 jobs + poll/SSE for index/Neo4j populate |
| External | In-process tools only (no FastMCP); no public price HTTP |

#### K-3 Dynamic workflow adjustment

| Signal (G metrics) | Adjustment |
|--------------------|------------|
| Wide fan-out / high load | Cap parallel needs; queue rest |
| Neo4j unavailable/slow | Delegator strips graph tool |
| Index long | Prefer C2 job path |
| Model down | Pricing fallback; continue |
| Empty fleet for need | Skip [7] for that need |

**Forbidden under pressure:** invent assets; skip availability when dates set; skip [4]; free ReAct mega-agent.

#### Role in workflow optimization

| Role | Workflow duty |
|------|----------------|
| **Coordinator** | Owns mode path; final barrier [8]; refuse path |
| **Delegator** | **Primary workflow optimizer** (order, allowlists, caps, skips) |
| **Workers** | Single task type; complete for barrier |
| Gate / tools / jobs | Critical path + resource backends |

### 10.0.11 Sequential and parallel processing (shared)

Efficiency depends on using **sequential** processing for dependent work and **parallel** processing for independent work—then combining them (see DAG §10.0.10).

#### L-1 Sequential processing (MUST)

Ordered steps where each depends on prior completion:

| Sequential chain | Why (dependency) | Travel analogue |
|------------------|------------------|-----------------|
| **[4] gate → recommend tools** | No fleet/price without index | Visa/session before finalize |
| **[5] → Delegator** | Plan needs needs | Gather prefs before multi-leg plan |
| **[6](need) → [7](need)** | Prices need candidates | Flight confirm before hotel (stock before rate) |
| **research → graph → synthesis** | Stage-1 Q&A evidence order | Ordered itinerary steps |
| **Worker slices → [8]** | Merge needs completed (or partial) | Finalize after components ready |
| **Price tool → attach rate in synthesis** | No invent rates | Payment/price before confirm docs |

#### L-2 Parallel processing (MAY, capped)

Independent concurrent work:

| Parallel set | Isolation | Travel analogue |
|--------------|-----------|-----------------|
| **[6] across need_ids** | Separate `fleet_by_need[need_id]` partitions | Multi-airline / multi-hotel search |
| **[7] across need_ids** | Only after that need’s [6]; separate `prices_by_need` | Concurrent rate quotes per leg |
| **Independent tools in one Worker** | Only if no data dependency | Weather + hotel APIs (here: SQL + optional Neo4j if plan allows) |
| **Background jobs** | Outside request graph | Profile updates, advisories — here: **`postgres_haystack_sync`**, Neo4j populate, retrain |

**Not agent parallel:** free ReAct spawning unbounded tools; polling primary while Workers run.

#### L-3 Hybrid / mode selection

| Rule | Owner |
|------|--------|
| Choose parallel width for needs | **Delegator** (+ Coordinator policy / config cap) |
| Encode within-need sequential edges | **Delegator** plan |
| Join parallel completions | **Coordinator** barrier [8] |
| Workers do **not** spawn sibling needs | Workers only execute assigned work item |
| Under load, shrink parallel (K-3/G) | Delegator / runtime |

```text
Sequential backbone:  [4] → [5] → plan → … → [8]
Parallel ribs:        need pipelines || need pipelines (capped)
Sequential within rib: fleet → price
```

### 10.1 Master template (blank)

Use this skeleton for any new agent. Fill every block including Sequential and parallel processing (L).

```text
# Agent: <ROLE_NAME>   role=<coordinator|delegator|worker>

## A. Defining objectives

Objective:
- <one sentence: role + outcome>

Core functions:
- ...
- ...

Constraints:
- ...
- ...

Behavior:
- ...
- ...

## B. Task specifications

### Task: <task_name>
Steps:
1. ...
2. ...
Expected outputs:
- ...
Potential challenges:
- ...

## C. Contextual awareness

Context layers (from §10.0):
- L...

Must read (inputs):
- ...

Must not assume / invent:
- ...

Dynamic adaptation:
- ...

Personalization / grounding:
- ...

Handoff context (leave in state for next role):
- ...

## D. State space representation

State partitions (view / own):
- ...

Must read (state fields):
- ...

May write / update:
- ...

Must not write:
- ...

Available actions (legal in this state):
- ...

Terminal / success conditions:
- ...

Invariants:
- ...

Example state fragment (JSON):
{ ... }

## E. Environment modeling

Systems / services in scope:
- ...

Out of scope (must not call):
- ...

Static rules governing interactions:
- ...

Dynamic conditions to monitor:
- ...

Response to environment change:
- ...

Compliance / safety:
- ...

## F. Integration and interaction patterns

### F-1 Event-driven updates
Emits:
- ...
Handles:
- ...
State updates on events:
- ...
Does not poll:
- ...

### F-2 State validation and consistency
Transitions this role may propose:
- ...
Dependency checks:
- ...
Business rules:
- ...
On validation failure:
- ...

## G. Monitoring and adaptation

### G-1 Monitoring
Metrics emitted:
- ...
Signals observed:
- ...
Trace fields required:
- ...

### G-2 Adaptation
Triggers → allowed adaptations:
- ...
Escalation:
- ...
Must never change under adaptation (hard rules):
- ...

## H. Agent memory architecture

### H-1 Short-term (working memory)
Reads:
- ...
Writes:
- ...
Clear / end of run:
- ...

### H-2 Long-term (knowledge base)
Accesses (via tools / stores):
- ...
Never writes / never invents:
- ...

### H-3 Episodic (interaction history)
Records:
- ...
May retrieve:
- ...
Scope limits:
- ...

## I. Context management

### I-1 Context hierarchy
Global context used:
- ...
Session context used:
- ...
Task context used:
- ...

### I-2 Context switching
Preserve (before leave):
- ...
Restore (on enter):
- ...
Merge / conflict rules:
- ...
Must not lose / must not invent:
- ...

## J. Integration with decision-making

### J-1 Information retrieval
Sources:
- ...
Filter / prioritize:
- ...

### J-2 Pattern recognition
Patterns used:
- ...
Forbidden (hallucinated) patterns:
- ...

### J-3 Decision optimization
Options considered:
- ...
Constraints / weights:
- ...
Risk mitigation:
- ...
Decision artifact (state / output):
- ...

## K. Workflow optimization

### K-1 Task classification & prioritization
Critical path vs parallel:
- ...
Upstream / downstream dependencies:
- ...
Priority rules:
- ...

### K-2 Resource management
Resources consumed:
- ...
Throttles / caps / retries:
- ...

### K-3 Dynamic workflow adjustment
Signals → workflow change:
- ...
Must not skip under pressure:
- ...

## L. Sequential and parallel processing

### L-1 Sequential processing
Ordered steps (must wait):
- ...
Dependency reason:
- ...

### L-2 Parallel processing
May run concurrent with:
- ...
Isolation / caps:
- ...

### L-3 Hybrid participation
Barrier / join role:
- ...
Forbidden parallel shortcuts:
- ...
```

**Folder-wide rules for every filled template:**

- Tools are **in-process** and **allowlisted** only (no FastMCP server).  
- Never invent `asset_id`, fleet stock, bookings, payments, or rates without tool hits.  
- Respect **[4]** gate: no recommend fleet/pricing work if indexing failed.  
- Emit observability fields when implemented: `role`, `node`, `need_id` (fan-out), `tool`, duration where useful.  
- Agent **Worker** ≠ ops **job worker**.  
- Every agent has **A + B + C + D + E + F + G + H + I + J + K + L**.  
- State holds **tool-normalized DTOs**, not raw **`heavy_rental`** rows.  
- Environment access is **role-partitioned** (§10.0.4) — no mega-agent with all backends.  
- Prefer **event/edge-driven** updates (§10.0.5 F-1); **validate** every transition (§10.0.5 F-2).  
- **Adapt only within hard rules** (§10.0.6 G-2) — never invent stock/rates to improve metrics.  
- **Memory:** STM = run state; fleet LTM = **`postgres_haystack` mirror of `postgres-primary`** via tools; episodic recommend rows are outputs (§10.0.7).  
- **Context:** maintain global/session/task hierarchy; preserve–restore–merge on switches without inventing gaps (§10.0.8).  
- **Decisions:** retrieve + patterns + optimize only over **tool-backed** options (§10.0.9)—never invent to “optimize.”  
- **Workflow:** respect critical path and within-need order; cap parallel fan-out; never skip gate/availability under load (§10.0.10).  
- **Seq/par:** mandatory sequential chains vs capped parallel sets (§10.0.11)—Workers do not spawn siblings.

| Role | Has A–L? |
|------|----------|
| Coordinator | **Yes** §10.2 |
| Delegator | **Yes** §10.3 — chooses parallel width |
| Worker [5] Project / needs | **Yes** §10.4 |
| Worker [6] Fleet / Neo4j | **Yes** §10.5 |
| Worker [7] Pricing | **Yes** §10.6 |
| Stage-1 Research / Graph Workers | **Yes** §10.7 (as-built specializations) |
| **[4] indexing gate** | **No** full agent L — sequential blocker (§10.9) |
| Tools / job workers / sync | **No** — background parallel to requests |

---

### 10.2 Coordinator

`role=coordinator` · steps: graph policy, **[4]** gate ownership, synthesis **[8]**

#### A. Defining objectives

**Objective:** Act as the Multi-Agent Orchestrator policy owner for project-spec Q&A and equipment recommend: enforce gates and modes, then produce a **grounded** final answer or structured recommendation without inventing fleet inventory or prices.

**Core functions:**

- Select and enforce mode (`qa` vs `recommend`) and graph policy  
- Own **[4]** indexing gate outcome (non-agent tool edge); refuse recommend path if gate failed  
- Hold shared state (`tool_traces`, needs, candidates, prices, warnings)  
- **Tool-free synthesis [8]:** merge Worker/tool outputs into Q&A markdown or `results_by_need` / recommend DTO  
- Surface gaps and warnings transparently (empty fleet, pricing fallback, missing project facts)  
- Align final HTTP/DTO shape for Spring (Call 2 recommend quote / Call 3 Q&A); persistence into **`ai_recommendations` / `recommendation_items`** is service-layer after merge  

**Constraints:**

- **Tools: none** at synthesis; do not call SQL, Cypher, or `predict_asset_price` from synthesis  
- Do not invent `asset_id`, daily rates, availability, payments, or KG nodes  
- Do not put raw file bytes into LLM context  
- Do not bypass **[4]** or free-form ReAct over the whole stack  
- Do not embed fleet SQL / pricing math in node code  
- KG-1 (project) vs KG-2 (fleet) stay separate; do not treat project KG as inventory SoT  
- Do not treat **`recommendation_items`** history as proof of current **`assets`** availability  

**Behavior:**

- Prefer structured recommend fields first; optional narrative second  
- Cite evidence type (Vector / Graph / Fleet tool / Pricing tool)  
- If sources conflict, state the conflict  
- If evidence is insufficient, say what is missing — do not pad with guesses  
- Professional, concise, operator-safe language  
- Record synthesis inputs from `tool_traces` for debug  

#### B. Task specifications

##### Task: Mode and graph policy

**Steps:**

1. Read request mode / feature flags (`qa` vs `recommend`).  
2. Ensure required prior steps for that mode (Q&A needs project session; recommend needs **[4]** success + needs).  
3. Refuse or degrade with explicit error/warning if prerequisites missing.  

**Expected outputs:**

- `mode` fixed for the run  
- Policy flags (e.g. `include_pricing`, Neo4j optional)  

**Potential challenges:**

- Client requests recommend without ingest  
- Mixed flags (pricing on, fleet empty)  

##### Task: Own [4] gate outcome

**Steps:**

1. Observe forced non-agent index edge result (`indexing_ok`, `ingest_id`, errors).  
2. If failed: stop recommend Workers; return ingest/error path only.  
3. If succeeded: allow Delegator / Workers.  

**Expected outputs:**

- `gate.indexing_ok` boolean  
- `ingest_id` when success  

**Potential challenges:**

- Partial index (docs written, KG hard-fail) — treat per product hard-fail rules  
- Timeout on long index — prefer 202 job path (resilience study), not fake success  

##### Task: Synthesis [8] — recommend merge

**Steps:**

1. Collect per-`need_id` fleet candidates and prices from Worker outputs / tool_traces.  
2. For each need: choose rank among **already priced** candidates only (or leave `item: null` + warning).  
3. Copy `asset_id` and rates **verbatim** from tool hits; compute totals only as rate × days when days known.  
4. Write optional rationale tied to project constraints from [5].  
5. Emit structured `results_by_need` (+ optional markdown narrative).  

**Expected outputs:**

- `recommendation.results_by_need[]` with `RecommendationItem` + `PricingPayload` when available  
- Warnings for empty fleet / pricing fallback / conflicts  
- No new asset ids or rates not present in tool hits  

**Potential challenges:**

- Partial fan-out failure on one need — isolate warning, do not fail whole envelope unless hard policy  
- LLM temptation to “helpful” invent stock — schema validation must reject  
- Stage-1 Q&A prompts still forbid fleet — use separate `RECOMMEND_SYNTHESIS_*` prompts  

##### Sample walkthrough: multi-need recommend merge

```text
Inputs:
  needs: [need_earthwork, need_access]
  fleet[need_earthwork]: [{asset_id: A1, ...}]
  prices[need_earthwork]: [{asset_id: A1, daily_rate: 420, ...}]
  fleet[need_access]: []   # empty

Steps:
  1. Merge earthwork → item A1 + pricing from tool
  2. Merge access → item null + warning "no fleet match"
  3. Do not invent access equipment

Outputs:
  results_by_need: two rows; only earthwork has asset_id/rate
```

#### C. Contextual awareness

| Block | Content |
|-------|---------|
| **Layers** | **L1–L5** required; **L6/L7** only as already resolved in Worker outputs (do not re-query DB at synthesis) |
| **Must read** | `mode`; `indexing_ok`; `needs[]`; `candidates_by_need`; `prices_by_need`; `tool_traces`; `warnings`; request dates/budget if present (L4); `user_id` / `ingest_id` for tenancy |
| **Must not assume / invent** | Assets not in fleet tool hits; rates not in pricing tool hits; payment status; rental_plan terms not in state; that mirror lag means permanent absence; project KG-1 as fleet inventory |
| **Dynamic adaptation** | Gate fail → no recommend merge; one need empty → `item: null` + warning, continue others; pricing fallback flagged in traces → surface in explanation; Vector vs Graph conflict → state conflict in Q&A mode |
| **Personalization / grounding** | Rank rationale tied to **this** project-spec constraints (height, soil, indoor) from [5]; budget only if L4 provided; multi-tenant isolation via L2 |
| **Handoff** | Structured recommend DTO / Q&A answer for Spring; service may persist **`ai_recommendations`** + **`recommendation_items`** (output tables — not invent mid-synthesis) |

**Sample (situational):** Earthwork candidates priced from tools; access need has zero **`assets`** matches after **`bookings`** filter — Coordinator does not invent a scissor lift; warns and returns partial `results_by_need`.

#### D. State space representation

| Block | Content |
|-------|---------|
| **Partitions** | Views **entire** run state; owns `recommendation.*`, top-level policy outcomes, `final_answer` (qa) |
| **Must read** | `run.*`, `project.needs`, `fleet_by_need`, `prices_by_need`, `tool_traces`, `work_plan` (audit), warnings |
| **May write** | `recommendation.results_by_need`, `recommendation.warnings`, `final_answer` / `sources_used` (qa); refuse/error flags |
| **Must not write** | Invent entries in `fleet_by_need` or `prices_by_need`; invent `persistence` ids without service write |
| **Available actions** | Enforce gate; merge; emit DTO; do **not** call fleet/pricing tools at [8] |
| **Terminal success** | Valid structured recommend or grounded Q&A with explicit gaps |
| **Invariants** | `indexing_ok` required for recommend merge; every output `asset_id`/`daily_rate` ⊆ tool-backed state; no invent |

**Example fragment (after merge):**

```json
{
  "recommendation": {
    "results_by_need": [
      {
        "need_id": "need_access",
        "item": {
          "asset_id": "AST-SL-001",
          "rank": 1,
          "pricing": { "daily_rate": 185, "currency": "SGD" }
        }
      }
    ],
    "warnings": []
  }
}
```

#### E. Environment modeling

| Question | Answer |
|----------|--------|
| **Systems in scope** | LangGraph shared state; HTTP response assembly for Spring; optional **service-layer** persist to **`ai_recommendations` / `recommendation_items`** after merge |
| **Out of scope** | Direct SQL on **`assets`/`bookings`**; `predict_asset_price`; free Cypher; re-indexing inside synthesis |
| **Static rules** | Tool-free [8]; no invent rates/assets; recommend only if gate ok; multi-tenant ids on response path; DTO contract (`results_by_need`) |
| **Dynamic conditions** | Partial need failures; empty fleet slices; pricing fallback flags in `tool_traces`; stub vs live LLM for rationale |
| **Response to change** | Isolate per-need warnings; refuse recommend if `indexing_ok` false; never backfill invent |
| **Compliance / safety** | Audit via `tool_traces`; do not expose raw DB credentials; Spring remains client |

#### F. Integration and interaction patterns

##### F-1 Event-driven updates

| | |
|--|--|
| **Emits** | `SYNTHESIS_DONE`; recommend refuse signals on gate failure |
| **Handles** | Implicit completion of Workers (state slices present); `INDEXING_FAILED`; `FLEET_EMPTY` / `PRICE_FALLBACK` via warnings in state |
| **State updates** | Writes `recommendation.*` / `final_answer` only after inputs observed |
| **Does not poll** | Does not re-query **`assets`/`bookings`** in a loop at synthesis |

##### F-2 State validation and consistency

| | |
|--|--|
| **Transitions** | `recommendation.results_by_need`, warnings, qa `final_answer` |
| **Dependencies** | Rates only if `prices_by_need` has rows; assets only if in `fleet_by_need` candidates |
| **Business rules** | Refuse recommend if not `indexing_ok`; schema-validate DTO; no invent |
| **On failure** | Hard refuse or per-need `item: null` + warning — never corrupt partial invent |

**Example:** like travel “confirm only if payment+seats valid” — attach `daily_rate` only if `PRICE_READY`/`PRICE_FALLBACK` data exists for that `asset_id`.

#### G. Monitoring and adaptation

##### G-1 Monitoring

| | |
|--|--|
| **Emits** | Synthesis latency; schema validation fail count; partial fill rate; warning volume; gate-refuse count |
| **Observes** | Worker warnings; empty fleet/price slices; stub vs live mode |
| **Traces** | `role=coordinator`, `node=synthesis`, duration_ms; link to `tool_traces` |

##### G-2 Adaptation

| Trigger | Allowed adaptation |
|---------|-------------------|
| Gate fail | Refuse recommend; return error/ingest path |
| Partial needs empty | Per-need `item: null` + warning; continue others |
| High schema fail rate | Prefer stub merge path in CI; fix prompts—**not** invent fields |
| Load / long run | Rely on C2 jobs for index—not invent faster answers |

**Hard rules under adaptation:** never invent assets/rates; tool-free synthesis remains.

#### H. Agent memory architecture

| Kind | This agent |
|------|------------|
| **H-1 STM** | **Reads** full working state; **writes** `recommendation.*` / `final_answer` only; cleared at run end |
| **H-2 LTM** | **No direct** fleet/project tool calls at [8]; consumes Worker projections already in STM (those came from project store/KG-1 and **`postgres_haystack`** mirror of **`postgres-primary`**) |
| **H-3 Episodic** | Appends synthesis-related traces; service may **persist** episode to **`ai_recommendations` / `recommendation_items`** — not invent fleet from old episodes |

#### I. Context management

##### I-1 Context hierarchy

| Level | Content for Coordinator |
|-------|-------------------------|
| **Global** | Mode, gate policy, DTO contract, no-invent rules |
| **Session** | `user_id`, `ingest_id`, dates/budget if present, full run after Workers |
| **Task** | Synthesis step [8]: merge all needs into one response |

##### I-2 Context switching

| | |
|--|--|
| **Preserve** | All Worker slices + traces already in STM before merge |
| **Restore** | Re-read full state at [8]; no re-query fleet LTM |
| **Merge** | Per-need contexts → `results_by_need`; tool prices/assets win; gaps → warning |
| **Must not** | Lose tenancy keys; invent rates to “complete” multi-need trip analogue |

**Scenario:** Multi-need recommend (access + earthwork) like multi-city trip—Coordinator holds session project + dates globally while merging each need’s task context.

#### J. Integration with decision-making

##### J-1 Information retrieval

| | |
|--|--|
| **Sources** | Full STM (`fleet_by_need`, `prices_by_need`, `project.needs`, warnings); optional episodic soft prior |
| **Filter / prioritize** | Only tool-backed assets/rates; multi-tenant session keys |

##### J-2 Pattern recognition

| | |
|--|--|
| **Uses** | Empty-need patterns; Vector vs Graph conflicts (Q&A); high warning density |
| **Forbidden** | “I know we usually have excavators” without STM candidates |

##### J-3 Decision optimization

| | |
|--|--|
| **Options** | Rank among **priced** candidates per need |
| **Constraints** | Project constraints + availability already applied + prices + budget if present |
| **Risk** | Partial fill + warnings; refuse if gate fail |
| **Artifact** | `recommendation.results_by_need` / `final_answer` |

#### K. Workflow optimization

##### K-1 Task classification & prioritization

| | |
|--|--|
| **Path** | Final **barrier** after all need pipelines; sequential merge |
| **Depends on** | Worker STM slices (partial OK with warnings) |
| **Priority** | P0 final deliverable |

##### K-2 Resource management

| | |
|--|--|
| **Consumes** | LLM for rationale (optional); CPU for merge/validation |
| **Caps** | Bound rationale length; prefer stub merge in CI |

##### K-3 Dynamic workflow adjustment

| Signal | Adjustment |
|--------|------------|
| Incomplete needs | Partial results—do not wait forever inventing |
| Gate fail | Refuse path—do not parallel-fake recommend |
| Load | Keep synthesis sequential; do not spawn extra invent Workers |

**Must not skip under pressure:** F-2 validation; tool-backed-only ranks.

#### L. Sequential and parallel processing

##### L-1 Sequential

| | |
|--|--|
| **Must wait** | Worker need-pipelines complete (or partial policy); then synthesis |
| **Why** | Merge needs priced candidates—flight/hotel finalize analogue |

##### L-2 Parallel

| | |
|--|--|
| **Concurrent with** | Receives completions from parallel need Workers; does **not** run parallel invent |
| **Caps** | N/A (single barrier node) |

##### L-3 Hybrid

| | |
|--|--|
| **Join** | Logical **barrier** over need ribs of the DAG |
| **Forbidden** | Parallel free-text “guess all needs” without STM |

---

### 10.3 Delegator

`role=delegator` · explicit router after needs known

#### A. Defining objectives

**Objective:** Act as the allowlisted router that turns project **needs** into an ordered **work plan** of Worker invocations (including **fan-out per need**), without executing fleet SQL, graph queries, or pricing itself.

**Core functions:**

- Read `indexing_ok`, `needs[]`, and optional capability flags (`neo4j_available`, etc.)  
- Expand work items: for each `need_id`, schedule fleet Worker **[6]** then pricing Worker **[7]**  
- Skip optional branches when backends empty/unavailable (e.g. Neo4j tool)  
- Enforce within-need order: fleet before pricing  
- Emit a machine-readable plan for the graph (and traces)

**Constraints:**

- **No backend execution** — do not call SQL, Cypher, or pricing model  
- **No inventing needs** — only route what [5] / decomposer produced  
- **No bypass of [4]** — if `indexing_ok` is false, emit empty/refuse plan  
- **Allowlisted branches only** — not free-form “plan any tools” ReAct  
- Do not become a mega-agent that also researches and prices  

**Behavior:**

- Deterministic and auditable preferred (code-first router OK; short policy prompt optional)  
- Prefer explicit skip reasons in traces (`skip_neo4j=empty_graph`)  
- Keep fan-out width visible (`needs_count`)  
- Fail closed: unknown worker_kind → do not schedule  

#### B. Task specifications

##### Task: Build per-need work plan

**Steps:**

1. Assert `indexing_ok` (recommend path).  
2. Load `needs[]` (`need_id`, equipment hints, constraints).  
3. For each need: append `{worker_kind: fleet, need_id}` then `{worker_kind: pricing, need_id}`.  
4. Attach tool allowlists per worker_kind from catalog.  
5. Publish plan to graph state.  

**Expected outputs:**

- `work_plan[]`: ordered list of `{worker_kind, need_id?, tool_allowlist, skip?}`  
- Trace: `role=delegator`, `needs_count`  

**Potential challenges:**

- Empty needs[] — plan only re-run [5] or return warning to Coordinator  
- Duplicate need_ids — dedupe  
- Very large N needs — respect future concurrency cap (open question)  

##### Task: Optional backend skip

**Steps:**

1. Check capability flags (e.g. Neo4j projected empty).  
2. Mark fleet Worker tool subset without `neo4j_cypher_read` when skip applies.  
3. Never skip **required** fleet SQL tools solely because Neo4j is empty.  

**Expected outputs:**

- Plan entries with reduced allowlist or `skip_tools: [neo4j_cypher_read]`  

**Potential challenges:**

- Stale capability flags — prefer soft skip + empty tool result over hard crash  

##### Sample walkthrough: three needs

```text
needs: [N1, N2, N3]
neo4j_available: false

Plan:
  fleet(N1, tools=[retrieve_*, filter_*, availability])  # no neo4j
  pricing(N1, tools=[predict_asset_price])
  fleet(N2, ...)
  pricing(N2, ...)
  fleet(N3, ...)
  pricing(N3, ...)
```

#### C. Contextual awareness

| Block | Content |
|-------|---------|
| **Layers** | **L1** (flags, allowlists), **L3** (`indexing_ok`), **L5** (`needs[]`) |
| **Must read** | `indexing_ok`; `needs[]` from Worker [5]; capability flags (`neo4j_available`, pricing model present); tool catalog allowlists for fleet vs pricing |
| **Must not assume / invent** | Extra needs; that Neo4j is populated; that **`assets`** rows exist without scheduling fleet tools; free-form tool sets outside allowlist |
| **Dynamic adaptation** | Empty `needs[]` → do not fan-out fleet; signal gap / re-run [5]; `neo4j_available=false` → strip `neo4j_cypher_read` from fleet allowlist but keep **`assets`/`bookings`** tools; large N → respect fan-out cap when configured |
| **Personalization / grounding** | Work plan shaped only by **this run’s** needs and flags — not historical **`ai_recommendations`** |
| **Handoff** | `work_plan[]` with `{worker_kind, need_id, tool_allowlist, skip?}` for Workers [6]×N / [7]×N |

**Sample:** Three unit needs after decomposer; Neo4j empty → six Worker slots still scheduled against Postgres-Haystack **`assets`/`bookings`**, without graph tool.

#### D. State space representation

| Block | Content |
|-------|---------|
| **Partitions** | Owns **`work_plan` only**; views `run.indexing_ok`, `project.needs`, L1 flags |
| **Must read** | `run.indexing_ok`, `run.mode`, `project.needs[]`, capability flags in `run` or env projection |
| **May write** | `work_plan[]` (ordered `{worker_kind, need_id, tool_allowlist, skip?}`) |
| **Must not write** | `fleet_by_need`, `prices_by_need`, `recommendation`, invent `needs` |
| **Available actions** | Expand fan-out; strip optional tools (e.g. Neo4j); refuse plan if gate failed |
| **Terminal success** | Complete `work_plan` covering all needs (or explicit empty/gap plan) |
| **Invariants** | No fleet/pricing plan items if `indexing_ok` is false; only allowlisted `worker_kind` values |

**Example fragment:**

```json
{
  "work_plan": [
    {"worker_kind": "fleet", "need_id": "need_access", "tool_allowlist": ["retrieve_fleet_assets", "filter_fleet_candidates", "check_booking_availability"]},
    {"worker_kind": "pricing", "need_id": "need_access", "tool_allowlist": ["predict_asset_price"]}
  ]
}
```

#### E. Environment modeling

| Question | Answer |
|----------|--------|
| **Systems in scope** | Capability flags / health projections (`neo4j_available`, pricing model present, mode); shared state `project.needs` — **not** the DB drivers themselves |
| **Out of scope** | Executing fleet SQL, Neo4j, or pricing; inventing needs; free-form planner tools |
| **Static rules** | Allowlisted `worker_kind` + per-kind tool allowlists only; no free ReAct; no plan if gate failed |
| **Dynamic conditions** | Empty `needs[]`; Neo4j empty/unhealthy; large N needs; model missing (still schedule pricing Worker with fallback path) |
| **Response to change** | Strip optional tools; empty/gap plan; respect fan-out caps when configured |
| **Compliance / safety** | Deterministic, auditable plans; log skip reasons |

#### F. Integration and interaction patterns

##### F-1 Event-driven updates

| | |
|--|--|
| **Emits** | `WORK_PLAN_READY` |
| **Handles** | `NEEDS_DECOMPOSED`; `INDEXING_SUCCEEDED`/`FAILED`; `NEO4J_UNAVAILABLE` / capability flags |
| **State updates** | Writes `work_plan[]` only |
| **Does not poll** | Does not poll Neo4j/DB health in a tight loop — uses flags/tool probes once |

##### F-2 State validation and consistency

| | |
|--|--|
| **Transitions** | Replace/set `work_plan` |
| **Dependencies** | Non-empty policy for needs (or explicit gap plan); `indexing_ok` for fleet/pricing items |
| **Business rules** | Only allowlisted `worker_kind` + tool names; fleet before price within need |
| **On failure** | Empty/refuse plan + warning — do not schedule illegal Workers |

#### G. Monitoring and adaptation

##### G-1 Monitoring

| | |
|--|--|
| **Emits** | Plan build latency; `needs_count` / fan-out width; skip-tool rate; gate-blocked plan count |
| **Observes** | Capability flags; empty needs |
| **Traces** | `role=delegator`, `node=router`, needs_count |

##### G-2 Adaptation

| Trigger | Allowed adaptation |
|---------|-------------------|
| `NEO4J_UNAVAILABLE` | Strip neo4j from allowlists |
| Empty needs | Gap plan / signal re-run [5] |
| Large N | Cap concurrent Worker fan-out when configured |
| Gate fail | No fleet/pricing plan items |

**Hard rules:** no free ReAct; no invent needs.

#### H. Agent memory architecture

| Kind | This agent |
|------|------------|
| **H-1 STM** | **Reads** `run.indexing_ok`, `project.needs`, flags; **writes** `work_plan` only; cleared at run end |
| **H-2 LTM** | Capability/health flags only — **not** a fleet DB reader |
| **H-3 Episodic** | Optional plan metrics in traces; does not load past recommends to invent needs |

#### I. Context management

##### I-1 Context hierarchy

| Level | Content for Delegator |
|-------|----------------------|
| **Global** | Allowlists, capability flags, gate policy |
| **Session** | `indexing_ok`, `project.needs[]` |
| **Task** | Build one `work_plan` for this run |

##### I-2 Context switching

| | |
|--|--|
| **Preserve** | Needs list and flags when emitting plan |
| **Restore** | N/A beyond reading STM after [5] |
| **Merge** | Expand needs into ordered work items (fleet→price per need) |
| **Must not** | Drop needs; schedule without gate; invent extra needs |

#### J. Integration with decision-making

##### J-1 Information retrieval

| | |
|--|--|
| **Sources** | `project.needs`, `indexing_ok`, capability flags |
| **Filter** | Allowlisted worker kinds only |

##### J-2 Pattern recognition

| | |
|--|--|
| **Uses** | Neo4j often empty → skip pattern; large N needs → concurrency cap |
| **Forbidden** | Invent needs from “typical projects” |

##### J-3 Decision optimization

| | |
|--|--|
| **Options** | Plan shapes (tools in/out, order) |
| **Constraints** | Gate; allowlists; fleet before price within need |
| **Risk** | Gap plan if no needs |
| **Artifact** | `work_plan[]` |

#### K. Workflow optimization

##### K-1 Task classification & prioritization

| | |
|--|--|
| **Path** | **Primary workflow optimizer** after [5]: expands needs into seq/parallel work items |
| **Depends on** | `needs[]`, `indexing_ok` |
| **Priority** | P0 planning; within-need fleet **before** price is hard |

##### K-2 Resource management

| | |
|--|--|
| **Consumes** | Negligible compute; encodes caps into plan |
| **Caps** | `max_parallel_needs` (config); strip expensive optional tools |

##### K-3 Dynamic workflow adjustment

| Signal | Adjustment |
|--------|------------|
| High N / load | Cap parallel fan-out; queue remainder |
| Neo4j down | Remove from allowlists |
| Empty needs | Gap plan—no fleet storm |
| Model down | Still schedule pricing with fallback path |

**Must not skip under pressure:** gate check; within-need order fleet→price.

#### L. Sequential and parallel processing

##### L-1 Sequential

| | |
|--|--|
| **Must wait** | After [5]; **before** any [6] |
| **Why** | Plan needs needs; encode fleet→price edges (hotel after flight stock) |

##### L-2 Parallel

| | |
|--|--|
| **Decides** | Which need pipelines may run **\|\|** (capped) |
| **Isolation** | Each plan item has `need_id` + allowlist |

##### L-3 Hybrid

| | |
|--|--|
| **Role** | **Mode selector**: sequential backbone + parallel ribs |
| **Forbidden** | Parallel without gate; parallel price before fleet for same need |

---

### 10.4 Worker [5] — Project / needs

`role=worker` · `worker_kind=project` · once per run (shared)

#### A. Defining objectives

**Objective:** Act as the project-context Worker that extracts **needs, constraints, and site facts** from the uploaded project specification (vector store + KG-1), so later Workers and the Coordinator can ground recommendations.

**Core functions:**

- Retrieve project passages via `project_vector_search`  
- Query KG-1 via `project_kg_query`  
- Decompose unit needs via `decompose_project_needs` when in recommend mode  
- Produce structured needs + research/graph notes for Delegator and synthesis  
- Support Call 3 Q&A prep with the same tools (without fleet)

**Constraints:**

- Allowlisted tools only: `project_vector_search`, `project_kg_query`, `decompose_project_needs`  
- Do not invent equipment fleet inventory, rates, or bookings  
- Do not call fleet SQL, Neo4j KG-2, or pricing tools  
- Do not produce the final user-facing recommend DTO (Coordinator owns [8])  
- Require successful project session / **[4]** for durable multi-user path  

**Behavior:**

- Always ground claims in tool hits; quote or cite meta when available  
- Prefer structured facts (capacities, soil, timeline, constraints) from KG when present  
- If retrieval empty, say so explicitly  
- Separate “facts found” from “inferred need labels”  

#### B. Task specifications

##### Task: Vector research over project-spec

**Steps:**

1. Reformulate user/query or recommend-prep prompt into search text.  
2. Call `project_vector_search`.  
3. Summarize grounded bullets + passage snippets with meta.  

**Expected outputs:**

- `research_notes`, `research_hits[]`  

**Potential challenges:**

- Ambiguous query; poor chunking; multi-language specs  

##### Task: KG-1 graph query

**Steps:**

1. Call `project_kg_query` with entity-focused terms.  
2. Collect node types / previews / optional 1-hop neighbors.  
3. Emit graph notes without inventing nodes.  

**Expected outputs:**

- `graph_notes`, `graph_hits[]`  

**Potential challenges:**

- Sparse KG; substring misses; conflicting node properties  

##### Task: Decompose unit needs (recommend mode)

**Steps:**

1. Combine research + graph evidence + request dates/budget if present.  
2. Call `decompose_project_needs` (or stub decomposer in CI).  
3. Emit `needs[]` with stable `need_id`, equipment_type hints, constraints.  

**Expected outputs:**

- `needs[]` for Delegator fan-out  

**Potential challenges:**

- Over-splitting or under-splitting needs; missing dates; budget absent (do not invent)  

##### Sample walkthrough: extract access + earthwork needs

```text
Initial context:
  Capture project site type, height work, earthmoving mentions
  Note start/end if present; do not invent budget

Search process:
  project_vector_search("elevated work indoor 8m")
  project_kg_query("platform height soil")
  decompose_project_needs(...)

Presentation to Delegator:
  needs: [
    {need_id: "need_access", equipment_type_hint: "scissor_lift", ...},
    {need_id: "need_earthwork", equipment_type_hint: "excavator", ...}
  ]

Outputs:
  research_notes, graph_notes, needs[]
```

#### C. Contextual awareness

| Block | Content |
|-------|---------|
| **Layers** | **L2–L4** + project tools on **L3** (vector + KG-1). Does **not** read L6 fleet tables |
| **Must read** | `user_id`, `ingest_id`, query / recommend-prep brief, rental dates if on request, project session tools only |
| **Must not assume / invent** | Fleet stock from **`assets`**; availability from **`bookings`**; rates; payments; needs not supported by project evidence |
| **Dynamic adaptation** | Empty vector/KG → explicit empty notes; sparse spec → fewer `needs[]` + gaps; missing budget → omit (do not invent) |
| **Personalization / grounding** (“destination intelligence”) | Site type, indoor/outdoor, height, soil, timeline, regulatory notes **from this project-spec** only |
| **Handoff** | `needs[]`, `research_notes`, `graph_notes`, hits for Delegator + Coordinator |

**Sample:** Spec mentions indoor elevated work ~8m → need_access hint scissor/boom; no excavator language → do not add earthwork need just because fleet has excavators in **`assets`**.

#### D. State space representation

| Block | Content |
|-------|---------|
| **Partitions** | Owns **`project.*`** (notes, hits, `needs`); views `run` tenant/request |
| **Must read** | `run.user_id`, `run.ingest_id`, `run` dates/query, session binding |
| **May write** | `project.research_notes`, `project.graph_notes`, hits, `project.needs[]` |
| **Must not write** | `fleet_by_need`, `prices_by_need`, `recommendation`, `work_plan` |
| **Available actions** | `project_vector_search`, `project_kg_query`, `decompose_project_needs` |
| **Terminal success** | Notes populated (or explicit empty); recommend mode has `needs[]` for Delegator |
| **Invariants** | Needs grounded in tool evidence; no fleet ids |

**Example fragment:**

```json
{
  "project": {
    "needs": [
      {"need_id": "need_access", "equipment_type_hint": "scissor_lift", "constraints": {"platform_height_m": 8}}
    ],
    "research_notes": "Indoor elevated work ~8m…",
    "graph_notes": "…"
  }
}
```

#### E. Environment modeling

| Question | Answer |
|----------|--------|
| **Systems in scope** | `project_vector_search` → InMemory/Pgvector; `project_kg_query` → KG-1; `decompose_project_needs` |
| **Out of scope** | **`assets`/`bookings`/Neo4j/pricing**; raw file bytes; Spring primary writes |
| **Static rules** | Allowlisted project tools only; multi-tenant meta filters; files never in LLM context |
| **Dynamic conditions** | Empty retrieval; sparse KG; missing budget/dates on request |
| **Response to change** | Explicit empty notes; fewer/clearer `needs[]`; do not invent budget |
| **Compliance / safety** | Ground claims in tool hits; no fleet invent |

#### F. Integration and interaction patterns

##### F-1 Event-driven updates

| | |
|--|--|
| **Emits** | `PROJECT_RESEARCH_DONE` / `PROJECT_KG_DONE` / `NEEDS_DECOMPOSED` (as applicable) |
| **Handles** | Request start; prior research notes when sequencing graph after vector |
| **State updates** | `project.research_*`, `project.graph_*`, `project.needs` |
| **Does not poll** | Single tool invocations per task — not continuous store polling |

##### F-2 State validation and consistency

| | |
|--|--|
| **Transitions** | Project partition only |
| **Dependencies** | Session/`ingest_id` available for retrieve |
| **Business rules** | Multi-tenant filters; no fleet/price fields; needs grounded in evidence |
| **On failure** | Empty notes / fewer needs + explicit gaps |

#### G. Monitoring and adaptation

##### G-1 Monitoring

| | |
|--|--|
| **Emits** | Vector empty rate; KG hit rate; decompose latency; tool error rate |
| **Observes** | Session presence; query quality proxies (empty hits) |
| **Traces** | `role=worker`, `worker_kind=project`, tool names, duration_ms |

##### G-2 Adaptation

| Trigger | Allowed adaptation |
|---------|-------------------|
| Empty retrieval/KG | Explicit empty notes; fewer/clearer needs |
| Missing budget/dates | Omit—do not invent |
| High latency | Bound tool top_k; do not skip grounding |

**Hard rules:** no fleet invent; multi-tenant filters stay on.

#### H. Agent memory architecture

| Kind | This agent |
|------|------------|
| **H-1 STM** | **Writes** `project.research_*`, `graph_*`, `needs`; **reads** `run` tenant/request; cleared at run end |
| **H-2 LTM** | Project knowledge only: vector store + **KG-1** via tools (`ProjectKnowledgeSession` / Pgvector). **Not** fleet mirror |
| **H-3 Episodic** | Tool traces for this run; no requirement to retrieve prior Q&A episodes in Phase 7 |

#### I. Context management

##### I-1 Context hierarchy

| Level | Content for Worker [5] |
|-------|------------------------|
| **Global** | Mode (qa vs recommend prep), tool allowlist for project tools |
| **Session** | `user_id`, `ingest_id`, project LTM session, query/dates |
| **Task** | Current research / KG / decompose sub-step |

##### I-2 Context switching

| | |
|--|--|
| **Preserve** | Research notes before KG; both before decompose |
| **Restore** | Session store by `ingest_id` (Call 2/3 after Call 1) |
| **Merge** | Vector + KG notes into needs (evidence-first); conflicts stated |
| **Must not** | Lose session keys; invent budget; pull fleet into project context |

**Scenario:** Like corporate travel policy + meeting times—here project constraints (height, indoor, dates) stay in session while task steps refine needs.

#### J. Integration with decision-making

##### J-1 Information retrieval

| | |
|--|--|
| **Sources** | Project LTM tools (vector, KG-1, decomposer); session query/dates |
| **Filter** | top_k; multi-tenant meta; evidence-first |

##### J-2 Pattern recognition

| | |
|--|--|
| **Uses** | Recurring constraint language in spec (height, soil, indoor) |
| **Forbidden** | Infer fleet stock from project language alone |

##### J-3 Decision optimization

| | |
|--|--|
| **Options** | How to split/label unit needs |
| **Constraints** | Grounding in tool hits; no invent budget |
| **Risk** | Fewer needs + gaps if sparse |
| **Artifact** | `project.needs[]` + notes |

#### K. Workflow optimization

##### K-1 Task classification & prioritization

| | |
|--|--|
| **Path** | Once per run on critical path **before** fan-out |
| **Depends on** | Gate (recommend); session LTM |
| **Internal order** | Research → KG → decompose (sequential preferred) |

##### K-2 Resource management

| | |
|--|--|
| **Consumes** | Vector/KG tools; optional LLM decomposer |
| **Caps** | top_k; stub decomposer in CI |

##### K-3 Dynamic workflow adjustment

| Signal | Adjustment |
|--------|------------|
| Sparse retrieval | Fewer needs + gaps—do not invent needs to fill pipeline |
| Latency | Bound top_k—not skip grounding |

**Must not skip under pressure:** multi-tenant filters; tool grounding.

#### L. Sequential and parallel processing

##### L-1 Sequential

| | |
|--|--|
| **Must wait** | Gate (recommend); preferred research→KG→decompose order |
| **Why** | Evidence before need split; before fan-out |

##### L-2 Parallel

| | |
|--|--|
| **Not parallel with** | Fleet/price for same recommend run (sits on critical path before ribs) |
| **Internal** | Tools sequential unless independent |

##### L-3 Hybrid

| | |
|--|--|
| **Role** | Sequential stem feeding parallel need ribs |
| **Forbidden** | Spawn fleet Workers itself |

---

### 10.5 Worker [6] — Fleet / Neo4j (per need)

`role=worker` · `worker_kind=fleet` · **fan-out per `need_id`**

#### A. Defining objectives

**Objective:** Act as the fleet-context Worker for **one unit need**: retrieve and filter candidate assets from Postgres-Haystack, check availability, and optionally enrich with Neo4j KG-2 relationships — without pricing or final ranking policy.

**Core functions:**

- `retrieve_fleet_assets` / `filter_fleet_candidates` for the need’s category/size constraints  
- `check_booking_availability` for the rental window  
- Optional `neo4j_cypher_read` for graph-neighbor context (templates only)  
- Return candidate list + availability + graph notes for that `need_id`  
- Leave pricing to Worker [7] and final rank to Coordinator  

**Constraints:**

- Allowlisted tools only (fleet SQL + optional Neo4j read); no free-form SQL/Cypher  
- Scope: **single `need_id`** per invocation  
- Do not call `predict_asset_price`  
- Do not invent assets if tools return empty — return empty candidates + warning  
- Do not write primary OLTP or treat mirror as writable SoT  
- `trigger_neo4j_populate` is ops/async only — do not block recommend on full rebuild  

**Behavior:**

- Prefer precise filters over dumping entire fleet  
- Log `role=worker`, `worker_kind=fleet`, `need_id`  
- Distinguish “no match” from “tool error”  
- Keep candidate payload schema stable for pricing Worker  

#### B. Task specifications

##### Task: Retrieve and filter candidates

**Steps:**

1. Read `need_id` constraints (category, capacity, height, location hints).  
2. Call `retrieve_fleet_assets` / `filter_fleet_candidates`.  
3. Normalize candidate rows (`asset_id`, category, condition, capacity, …).  

**Expected outputs:**

- `candidates_by_need[need_id][]`  

**Potential challenges:**

- Mirror lag; category taxonomy mismatch; over-filter to zero  

##### Task: Availability check

**Steps:**

1. For shortlisted candidates, call `check_booking_availability` for window.  
2. Drop or flag unavailable assets per policy.  

**Expected outputs:**

- Candidates with availability flags; warnings if all busy  

**Potential challenges:**

- Missing bookings table data; timezone/date edge cases  

##### Task: Optional Neo4j context

**Steps:**

1. If plan includes Neo4j tool, run constrained `neo4j_cypher_read` template.  
2. Attach neighbor context notes; do not invent relationships.  

**Expected outputs:**

- `graph_context_by_need[need_id]` (may be empty)  

**Potential challenges:**

- Empty KG-2 projection; template mismatch  

##### Sample walkthrough: scissor-lift need

```text
need_id: need_access
constraints: indoor, ~8m platform, window 2026-09-01..2026-09-14

Steps:
  1. filter_fleet_candidates(category=scissor_lift, min_platform_height=8)
  2. check_booking_availability(asset_ids, window)
  3. neo4j_cypher_read skipped (plan flag)

Outputs:
  candidates: [{asset_id: "SL-12", ...}, ...]
  unavailable: [...]
  warning: null | "no fleet match"
```

#### C. Contextual awareness

| Block | Content |
|-------|---------|
| **Layers** | **L4** (rental window), **L5** (this `need_id` slice), **L6** via tools on **`assets`**, **`bookings`**, optional **`rental_plan`**, optional Neo4j KG-2 |
| **Must read** | Need constraints from plan; `start_date`/`end_date`; allowlisted tool results from Postgres-Haystack **`heavy_rental.assets`** (category, condition, capacity, platform_height, rate bounds) and **`bookings`** (overlap / status for availability) |
| **Must not assume / invent** | Assets not returned by tools; that primary has newer stock than mirror without reading mirror; payment clearance from **`payments`** unless tool returns it; prices (Worker [7] owns rates) |
| **Dynamic adaptation** (“cancelled flight” analogue) | Overlapping **`bookings`** → mark unavailable; re-filter remaining **`assets`**; zero candidates → empty list + warning (do not invent substitute id); Neo4j skip if plan says so; mirror lag → prefer tool empty/error semantics + warning, not hallucinated stock |
| **Personalization / grounding** | Match **this need’s** equipment_type/capacity/height from project constraints to **`assets`** attributes; respect **`rental_plan`** constraints only if tool provides them |
| **Handoff** | `candidates_by_need[need_id][]` with stable `asset_id` + attributes for pricing Worker |

**Sample:** Need access 8m indoor, window Sept 1–14 → tool reads **`assets`** scissor lifts ≥8m; **`bookings`** drops units with CONFIRMED/PENDING overlap; remaining candidates only.

**Table → tool mapping (illustrative):**

| Table | Tool / use |
|-------|------------|
| **`assets`** | `retrieve_fleet_assets` / `filter_fleet_candidates` |
| **`bookings`** | `check_booking_availability` (+ util aggregates for pricing path) |
| **`rental_plan`** | Optional filter if allowlisted |
| **`payments`** | Generally out of fleet Worker scope |
| **`recommendation_items` / `ai_recommendations`** | Not read as fleet SoT |

#### D. State space representation

| Block | Content |
|-------|---------|
| **Partitions** | Owns **`fleet_by_need[need_id]` only** for assigned need |
| **Must read** | `work_plan` item for this invocation; matching `project.needs` entry; `run.start_date`/`end_date`; `run.indexing_ok` |
| **May write** | `fleet_by_need[need_id].candidates`, `.unavailable`, `.source_tables`, optional graph notes |
| **Must not write** | Other needs’ fleet slices; `prices_by_need`; `recommendation` |
| **Available actions** | Allowlisted fleet tools only (`retrieve_*`, `filter_*`, `check_booking_availability`, optional `neo4j_cypher_read`) |
| **Terminal success** | Slice written (possibly empty candidates + warning trace) |
| **Invariants** | `source_tables` reflect tools used (`assets`, `bookings`, …); no candidate without tool hit; no rates |

**Example fragment:**

```json
{
  "fleet_by_need": {
    "need_access": {
      "candidates": [
        {"asset_id": "AST-SL-001", "category": "scissor lift", "platform_height": 10.0, "condition": "GOOD", "min_daily_rate": 120, "max_daily_rate": 280}
      ],
      "unavailable": [],
      "source_tables": ["assets", "bookings"]
    }
  }
}
```

#### E. Environment modeling

| Question | Answer |
|----------|--------|
| **Systems in scope** | Allowlisted tools → Postgres-Haystack **`heavy_rental.assets`**, **`bookings`**; optional **`rental_plan`**; optional Neo4j KG-2 read templates |
| **Out of scope** | `predict_asset_price`; free-form SQL/Cypher; writes to primary OLTP; **`payments`** unless tool allowlisted |
| **Static rules** | Read-only mirror; single `need_id` scope; tool allowlist from Delegator plan |
| **Dynamic conditions** | Booking overlaps; zero candidates; mirror lag; Neo4j empty; DB errors vs empty sets |
| **Response to change** | Empty candidates + warning; skip Neo4j if planned; do not invent substitute assets |
| **Compliance / safety** | Distinguish empty vs error in traces; never treat project KG as inventory |

#### F. Integration and interaction patterns

##### F-1 Event-driven updates

| | |
|--|--|
| **Emits** | `FLEET_CANDIDATES_READY` / `FLEET_EMPTY`; `BOOKING_OVERLAP_DETECTED` (per asset) |
| **Handles** | `WORK_PLAN_READY` item for this `need_id`; tool return payloads |
| **State updates** | `fleet_by_need[need_id]` only |
| **Does not poll** | No continuous **`bookings`** scan loop — one availability tool pass (or bounded batch) |

**Example (travel flight-change analogue):** tool reports overlap on AST-SL-001 → treat as `BOOKING_OVERLAP_DETECTED` → move to `unavailable[]` → remaining candidates only.

##### F-2 State validation and consistency

| | |
|--|--|
| **Transitions** | Only own need’s fleet slice |
| **Dependencies** | `indexing_ok`; need exists in `project.needs` / plan |
| **Business rules** | Candidates only from tool DTOs; `source_tables` accurate; no rates |
| **On failure** | Empty candidates + warning; do not invent ids |

#### G. Monitoring and adaptation

##### G-1 Monitoring

| | |
|--|--|
| **Emits** | Candidate count; unavailable/overlap rate; tool error vs empty; tool latency |
| **Observes** | Mirror empty/error distinction; Neo4j skip flags |
| **Traces** | `role=worker`, `worker_kind=fleet`, `need_id`, tools, duration_ms |

##### G-2 Adaptation

| Trigger | Allowed adaptation |
|---------|-------------------|
| All busy / empty | Empty candidates + warning |
| Neo4j down | Skip graph tool (plan) |
| DB errors | Error warning—not invent stock |
| High latency | Bound candidate list size—not skip availability check when dates set |

**Hard rules:** no invent `asset_id`; no prices in this Worker.

#### H. Agent memory architecture

| Kind | This agent |
|------|------------|
| **H-1 STM** | **Writes** `fleet_by_need[need_id]` only; **reads** plan item + need + dates; cleared at run end |
| **H-2 LTM** | Fleet knowledge via tools on **`postgres_haystack` / `heavy_rental`** (**`assets`**, **`bookings`**, optional **`rental_plan`**) — data **synced from `postgres-primary`**; optional Neo4j projection. **Read-only**; never write primary or mirror |
| **H-3 Episodic** | Overlap / empty-fleet events in `tool_traces`; does not invent stock from past `ai_recommendations` |

#### I. Context management

##### I-1 Context hierarchy

| Level | Content for Worker [6] |
|-------|------------------------|
| **Global** | Read-only mirror policy; tool allowlist from plan |
| **Session** | Rental window on `run`; shared `project.needs` |
| **Task** | **Only this `need_id`** fleet retrieval + availability |

##### I-2 Context switching

| | |
|--|--|
| **Preserve** | Write `fleet_by_need[need_id]` before exit |
| **Restore** | Load need constraints + dates from STM; re-open tools to **haystack** mirror |
| **Merge** | Filter + availability into one candidate list; overlaps → unavailable |
| **Must not** | Leak other needs’ candidates into this slice; invent assets; write primary |

**Scenario:** Switching from `need_access` to `need_earthwork` is a task-context switch; session dates and global allowlists stay; prior need’s fleet context remains preserved in STM for Coordinator.

#### J. Integration with decision-making

##### J-1 Information retrieval

| | |
|--|--|
| **Sources** | Tools on **`postgres_haystack`** (**`assets`**, **`bookings`**, optional Neo4j) ← synced from **`postgres-primary`**; need constraints from STM |
| **Filter** | Category/size/height filters; availability window; plan allowlist |

##### J-2 Pattern recognition

| | |
|--|--|
| **Uses** | Overlap clusters; category/capacity fit to need |
| **Forbidden** | “Usually available” without tool hit |

##### J-3 Decision optimization

| | |
|--|--|
| **Options** | Which mirror rows enter `candidates` vs `unavailable` |
| **Constraints** | Need fit + bookings + read-only mirror |
| **Risk** | Empty set + warning |
| **Artifact** | `fleet_by_need[need_id]` |

#### K. Workflow optimization

##### K-1 Task classification & prioritization

| | |
|--|--|
| **Path** | Parallelizable **across** needs (capped); sequential **before** pricing for same need |
| **Depends on** | Work plan item + need + gate |
| **Downstream** | Unblocks [7] for this need |

##### K-2 Resource management

| | |
|--|--|
| **Consumes** | Read-only SQL on **`postgres_haystack`** (mirror of primary); optional Neo4j |
| **Caps** | Candidate list size; bounded availability batch; tool retries limited |

##### K-3 Dynamic workflow adjustment

| Signal | Adjustment |
|--------|------------|
| Empty/all busy | Emit empty; skip pricing for need |
| Neo4j slow | Plan already stripped—do not block on graph |
| DB errors | Fail soft with warning—not invent stock |

**Must not skip under pressure:** availability check when dates set; gate.

#### L. Sequential and parallel processing

##### L-1 Sequential

| | |
|--|--|
| **Must wait** | Plan item + **before [7] same need** |
| **Why** | Candidates required for prices (flight stock before rate) |

##### L-2 Parallel

| | |
|--|--|
| **May run \|\|** | Other needs’ [6] (and later their [7]) under cap |
| **Isolation** | Only `fleet_by_need[need_id]` |

##### L-3 Hybrid

| | |
|--|--|
| **Role** | Parallel rib start; sequential handoff to pricing |
| **Forbidden** | Price in parallel with own fleet incomplete; invent candidates to unblock parallel |

---

### 10.6 Worker [7] — Pricing (per need)

`role=worker` · `worker_kind=pricing` · **fan-out per `need_id`**

#### A. Defining objectives

**Objective:** Act as the pricing Worker for **one unit need**: obtain **clamped daily rates** for fleet candidates using only the in-process `predict_asset_price` tool (or documented category fallback), never free-text invented prices.

**Core functions:**

- Build feature rows from fleet candidate attributes + rental duration  
- Call `predict_asset_price` per candidate (or batch policy if tool supports)  
- Attach clamp metadata, model version, explanation  
- Apply fallback category table when model missing — **never silent zeros**  
- Return priced candidates for Coordinator merge  

**Constraints:**

- Allowlisted tool: **`predict_asset_price` only** for rates  
- Scope: **single `need_id`**; requires prior fleet candidates for that need  
- Do not invent rates; do not rank globally across needs  
- Not a public HTTP price API  
- Neo4j / project KG are context for agents only — not untrained model features unless retrain says so  

**Behavior:**

- Fail loud with warning + fallback policy  
- Preserve `asset_id` linkage to rates  
- Log `role=worker`, `worker_kind=pricing`, `need_id`, `model_version`  
- Transparent when `was_clamped`  

#### B. Task specifications

##### Task: Price candidates for one need

**Steps:**

1. Load candidates for `need_id` from Worker [6] output.  
2. If empty candidates: emit empty prices + warning; stop.  
3. For each candidate: assemble features (category, condition, duration_days, capacity, distance_km, platform_height, optional util/lead time).  
4. Call `predict_asset_price(...)`.  
5. Record daily_rate, clamp flags, model_version; optional total = rate × days.  

**Expected outputs:**

- `prices_by_need[need_id][]` aligned to `asset_id`  
- Warnings on tool failure / fallback used  

**Potential challenges:**

- Missing features (NaN platform_height); model artifact absent; feature schema drift  
- Distance default proxies — document defaults  

##### Sample walkthrough: price top candidates

```text
need_id: need_access
candidates: [SL-12, SL-07]
duration_days: 14

Steps:
  1. predict_asset_price(category=scissor_lift, ..., asset_id=SL-12)
  2. predict_asset_price(..., asset_id=SL-07)
  3. Attach was_clamped / model_version

Outputs:
  prices: [
    {asset_id: SL-12, daily_rate: 185, currency: EUR, was_clamped: false, ...},
    {asset_id: SL-07, daily_rate: 170, ...}
  ]
```

#### C. Contextual awareness

| Block | Content |
|-------|---------|
| **Layers** | **L4** duration/window, **L5** candidates for `need_id`, **L7** model/fallback; features drawn from **L6** attributes already on candidates (**`assets`**) and live aggregates from **`bookings`** when Phase 1e wired |
| **Must read** | Candidate rows (`asset_id`, category, condition, capacity, platform_height, min/max daily rate); `duration_days` from L4; optional `period_utilization` / `lead_time_days` from **`bookings`** aggregates; clamp policy |
| **Must not assume / invent** | Rates without `predict_asset_price` (or documented fallback); payment amounts from **`payments`** as model output; that **`recommendation_items.mlPredictedPrice`** history is the current prediction |
| **Dynamic adaptation** | Empty candidates → no prices + warning; model missing → category fallback + warning (**never silent zero**); clamp to **`assets.minDailyRate`/`maxDailyRate`** when available; feature NaNs (e.g. platform_height) per schema |
| **Personalization / grounding** | Price **this** need’s candidates for **this** rental duration/window — not a generic catalogue rate card alone |
| **Handoff** | `prices_by_need[need_id][]` for Coordinator; later persistence may write predicted price into **`recommendation_items`** |

**Sample:** Candidates SL-12/SL-07 from **`assets`**; util from overlapping **`bookings`** in same category+spec-band; tool returns clamped `price_per_day` with `model_version`.

**Table → pricing context:**

| Table | Role |
|-------|------|
| **`assets`** | Feature attributes + guardrail clamp bounds |
| **`bookings`** | Live `period_utilization` / window for `lead_time_days` |
| **`rental_plan`** | Optional commercial constraints if tool exposes |
| **`payments`** | Not a predict-price input |
| **`recommendation_items`** | Output field for `mlPredictedPrice` after merge — not mid-Worker invent source |
| **`ai_recommendations`** | Parent envelope after Coordinator — not pricing input |

#### D. State space representation

| Block | Content |
|-------|---------|
| **Partitions** | Owns **`prices_by_need[need_id]` only** |
| **Must read** | `fleet_by_need[need_id].candidates`; `run` duration/window; clamp fields on candidates |
| **May write** | `prices_by_need[need_id][]` (`asset_id`, `daily_rate`, clamp/model metadata) |
| **Must not write** | New candidates; `recommendation`; other needs’ prices |
| **Available actions** | `predict_asset_price` only (or documented fallback path recorded in traces) |
| **Terminal success** | Price rows for candidates, or empty + warning if no candidates / tool failure with fallback policy |
| **Invariants** | Every priced `asset_id` ∈ candidates; never silent zero; no invent rates |

**Example fragment:**

```json
{
  "prices_by_need": {
    "need_access": [
      {"asset_id": "AST-SL-001", "daily_rate": 185, "currency": "SGD", "was_clamped": false, "model_version": "…"}
    ]
  }
}
```

#### E. Environment modeling

| Question | Answer |
|----------|--------|
| **Systems in scope** | `predict_asset_price` → in-process model / `pricing_client`; feature inputs from candidate DTOs (**`assets`** attrs) + optional live aggregates from **`bookings`** |
| **Out of scope** | Public price HTTP API; free SQL; inventing candidates; writing **`recommendation_items`** mid-Worker |
| **Static rules** | Allowlisted pricing tool only; clamp policy; never silent zeros; not a ranker across needs |
| **Dynamic conditions** | Model artifact missing; clamp hits; NaN features; empty candidates |
| **Response to change** | Category fallback + warning; empty prices if no candidates; record `model_version` / `was_clamped` |
| **Compliance / safety** | Transparent fallback; rates only for known `asset_id`s |

#### F. Integration and interaction patterns

##### F-1 Event-driven updates

| | |
|--|--|
| **Emits** | `PRICE_READY` / `PRICE_FALLBACK` / `PRICE_FAILED` |
| **Handles** | `FLEET_CANDIDATES_READY` (or empty → skip) for this `need_id` |
| **State updates** | `prices_by_need[need_id]` only |
| **Does not poll** | No re-training or continuous model reload mid-request |

##### F-2 State validation and consistency

| | |
|--|--|
| **Transitions** | Price rows for existing candidates only |
| **Dependencies** | `fleet_by_need[need_id].candidates` non-empty for pricing attempts |
| **Business rules** | `asset_id` ∈ candidates; never silent zero; record clamp/fallback |
| **On failure** | Warning + fallback policy or empty prices — no invented rates |

**Example (travel payment/seat checks):** like “confirm only if payment valid and seats open” — emit price only after tool returns clamped rate for a still-listed candidate.

#### G. Monitoring and adaptation

##### G-1 Monitoring

| | |
|--|--|
| **Emits** | Pricing latency; clamp rate; fallback rate; model error rate; `model_version` tag |
| **Observes** | Empty candidates (skip); feature NaNs |
| **Traces** | `role=worker`, `worker_kind=pricing`, `need_id`, was_clamped, duration_ms |

##### G-2 Adaptation

| Trigger | Allowed adaptation |
|---------|-------------------|
| Model missing / fail | Category fallback + warning — **never silent zero** |
| High clamp rate | Surface was_clamped; ops review bounds—not invent rates |
| Empty candidates | Empty prices + warning |
| Seasonal util shift | Live `period_utilization` from **`bookings`** when Phase 1e wired |

**Hard rules:** no invent rates; no public price HTTP; asset_id must match candidates.

#### H. Agent memory architecture

| Kind | This agent |
|------|------------|
| **H-1 STM** | **Writes** `prices_by_need[need_id]`; **reads** candidates + duration from STM; cleared at run end |
| **H-2 LTM** | Pricing model artifacts + clamp policy; feature attrs already on candidates (from mirror **`assets`**); live util from **`bookings`** on **haystack** mirror when Phase 1e wired. **Not** write path to primary |
| **H-3 Episodic** | `model_version` / fallback in traces; later line items may store `mlPredictedPrice` on **`recommendation_items`** after Coordinator persist |

#### I. Context management

##### I-1 Context hierarchy

| Level | Content for Worker [7] |
|-------|------------------------|
| **Global** | Pricing policy (clamp, no silent zero, no public HTTP) |
| **Session** | Duration/window from `run` |
| **Task** | Price **this need’s** candidates only |

##### I-2 Context switching

| | |
|--|--|
| **Preserve** | Write `prices_by_need[need_id]` before exit |
| **Restore** | Candidates from STM fleet slice for this need (not re-invent) |
| **Merge** | Per-candidate tool results into price list; fallback flagged |
| **Must not** | Price other needs; invent rates; ignore clamp context |

#### J. Integration with decision-making

##### J-1 Information retrieval

| | |
|--|--|
| **Sources** | STM candidates; model LTM; optional util from **`bookings`** on haystack mirror |
| **Filter** | Only candidate `asset_id`s for this need |

##### J-2 Pattern recognition

| | |
|--|--|
| **Uses** | Clamp/fallback frequency; util/lead-time signals |
| **Forbidden** | Guess catalogue rates without tool |

##### J-3 Decision optimization

| | |
|--|--|
| **Options** | Model price vs fallback table per candidate |
| **Constraints** | Clamp bounds; never silent zero |
| **Risk** | Fallback + warning; empty if no candidates |
| **Artifact** | `prices_by_need[need_id]` |

#### K. Workflow optimization

##### K-1 Task classification & prioritization

| | |
|--|--|
| **Path** | After fleet for **same** need; parallel across needs only after each need’s [6] |
| **Depends on** | `fleet_by_need[need_id]` |
| **Downstream** | Feeds Coordinator rank |

##### K-2 Resource management

| | |
|--|--|
| **Consumes** | Model inference / fallback table; optional util queries on haystack |
| **Caps** | One price path per candidate; no retrain mid-request |

##### K-3 Dynamic workflow adjustment

| Signal | Adjustment |
|--------|------------|
| No candidates | Skip pricing (empty prices) |
| Model fail | Fallback—never silent zero |
| Load | Bound candidates priced—not invent rates |

**Must not skip under pressure:** clamp policy; asset_id ∈ candidates.

#### L. Sequential and parallel processing

##### L-1 Sequential

| | |
|--|--|
| **Must wait** | After [6] for **same** `need_id` |
| **Why** | No rate without candidates (payment/price before confirm) |

##### L-2 Parallel

| | |
|--|--|
| **May run \|\|** | Other needs’ pipelines once their fleets done |
| **Isolation** | Only `prices_by_need[need_id]` |

##### L-3 Hybrid

| | |
|--|--|
| **Role** | Parallel rib end → join at Coordinator |
| **Forbidden** | Parallel invent rates; price other needs’ assets |

---

### 10.7 As-built Stage-1 specializations (Q&A)

Today’s graph (`research_agent` → `graph_agent` → `synthesis_agent`) maps as:

| As-built node | C/W/D role | Template |
|---------------|------------|----------|
| `research_agent` | Worker (vector slice of [5]) | below |
| `graph_agent` | Worker (KG slice of [5]) | below |
| `synthesis_agent` | Coordinator [8] in **qa** mode | §10.2 synthesis rules (Q&A markdown; still tool-free; still no invent fleet/rates) |

#### 10.7.1 Research Worker (Stage-1)

##### A. Defining objectives

**Objective:** Retrieve project-specification passages that answer or constrain the user query.

**Core functions:**

- Call `project_vector_search` with query or focused reformulation  
- Produce research notes and passage quotes only  

**Constraints:**

- Tool: `project_vector_search` only  
- Do not invent stock/prices; do not final-answer  

**Behavior:**

- Always call the tool; explicit empty result if no hits  

##### B. Task specifications

**Task: Dense retrieval**

- **Steps:** reformulate → `project_vector_search` → notes + passages  
- **Expected outputs:** `## Research notes`, `## Passages`  
- **Potential challenges:** empty store; vague query  

##### C. Contextual awareness

| Block | Content |
|-------|---------|
| **Layers** | L2–L3 + query (L4); **no L6 fleet tables** |
| **Must read** | `user_id`, `ingest_id`, `query`, session vector store via tool |
| **Must not invent** | Fleet **`assets`**, **`bookings`**, rates, payments |
| **Adaptation** | Empty hits → say empty; do not fall back to inventing inventory |
| **Handoff** | `research_notes`, `research_hits` |

##### D. State space representation

| Block | Content |
|-------|---------|
| **Partitions** | Owns `research_notes`, `research_hits` in `ProjectKnowledgeAgentState` |
| **Must read** | `user_id`, `ingest_id`, `query`, `top_k` |
| **May write** | `research_notes`, `research_hits`; append `tool_traces` |
| **Must not write** | `graph_*`, `final_answer`, fleet/price fields |
| **Available actions** | `project_vector_search` |
| **Terminal success** | Notes/hits set (possibly empty) |
| **Invariants** | No invent fleet; Stage-1 state only |

##### E. Environment modeling

| Question | Answer |
|----------|--------|
| **Systems** | `project_vector_search` → session DocumentStore only |
| **Out of scope** | KG tool, fleet DB, pricing |
| **Static rules** | Always call tool; no final answer |
| **Dynamic** | Empty store / weak query |
| **Response** | Explicit empty research notes |

##### F. Integration and interaction patterns

- **F-1:** Emits `PROJECT_RESEARCH_DONE` (edge to graph); handles query start; no polling.  
- **F-2:** May write only `research_*`; reject writes to `final_answer`/fleet.

##### G. Monitoring and adaptation

- **G-1:** Empty-hit rate; tool latency; `role=worker` traces.  
- **G-2:** Explicit empty notes on miss—never invent fleet/passages.

##### H. Agent memory architecture

- **H-1 STM:** `research_notes` / `research_hits`.  
- **H-2 LTM:** session DocumentStore only (project).  
- **H-3:** tool_traces for this run.

##### I. Context management

- **I-1:** Session = project session + query; task = vector retrieval step.  
- **I-2:** Preserve research notes for graph/synthesis; no fleet context.

##### J. Integration with decision-making

- **J-1:** `project_vector_search` only.  
- **J-2:** Empty-hit patterns.  
- **J-3:** Notes only—no fleet/price decisions.

##### K. Workflow optimization

- **K-1:** First on Q&A critical path (sequential).  
- **K-2:** Single tool call + top_k.  
- **K-3:** No parallel fan-out; empty notes on miss.

##### L. Sequential and parallel processing

- **L-1:** First step; must complete before graph.  
- **L-2:** None in Stage-1.  
- **L-3:** Pure sequential chain only.

*(Maps to `RESEARCH_AGENT_SYSTEM` in `app/agents/prompts.py`.)*

#### 10.7.2 Graph Worker (Stage-1)

##### A. Defining objectives

**Objective:** Query project KG-1 for entities, relations, or document-node facts supporting multi-hop reasoning.

**Core functions:**

- Call `project_kg_query`; prefer structured facts  

**Constraints:**

- Tool: `project_kg_query` only  
- Do not invent nodes; do not final-answer  

**Behavior:**

- Always call the tool; report empty matches  

##### B. Task specifications

**Task: KG-1 lookup**

- **Steps:** entity terms → `project_kg_query` → graph notes + node previews  
- **Expected outputs:** `## Graph notes`, `## Nodes`  
- **Potential challenges:** sparse graph; weak substring match  

##### C. Contextual awareness

| Block | Content |
|-------|---------|
| **Layers** | L2–L3 + query (L4); KG-1 only — **not** Neo4j KG-2 / **`assets`** |
| **Must read** | Query terms, KG-1 session via `project_kg_query` |
| **Must not invent** | Nodes/relations not returned; fleet or booking facts |
| **Adaptation** | Sparse graph → explicit empty; no silent fill from rental DB |
| **Handoff** | `graph_notes`, `graph_hits` |

##### D. State space representation

| Block | Content |
|-------|---------|
| **Partitions** | Owns `graph_notes`, `graph_hits` |
| **Must read** | `query`, session; may read research fields for context but must not overwrite them |
| **May write** | `graph_notes`, `graph_hits`; append `tool_traces` |
| **Must not write** | `final_answer`, research fields, fleet/price |
| **Available actions** | `project_kg_query` |
| **Terminal success** | Graph notes/hits set (possibly empty) |
| **Invariants** | No invent nodes; Stage-1 state only |

##### E. Environment modeling

| Question | Answer |
|----------|--------|
| **Systems** | `project_kg_query` → KG-1 session only |
| **Out of scope** | Vector tool, Neo4j KG-2, **`assets`/`bookings`** |
| **Static rules** | Always call tool; no invent nodes; no final answer |
| **Dynamic** | Sparse KG / weak matches |
| **Response** | Explicit empty graph notes |

##### F. Integration and interaction patterns

- **F-1:** Handles research completion edge; emits `PROJECT_KG_DONE`.  
- **F-2:** May write only `graph_*`; no invent nodes.

##### G. Monitoring and adaptation

- **G-1:** Empty-node rate; tool latency; traces.  
- **G-2:** Explicit empty graph notes—never invent KG edges.

##### H. Agent memory architecture

- **H-1 STM:** `graph_notes` / `graph_hits`.  
- **H-2 LTM:** KG-1 session only.  
- **H-3:** tool_traces for this run.

##### I. Context management

- **I-1:** Session = same project session; task = KG lookup.  
- **I-2:** Restore after research edge; merge is Coordinator’s job (cite Vector vs Graph).

##### J. Integration with decision-making

- **J-1:** `project_kg_query` only.  
- **J-2:** Sparse-graph patterns.  
- **J-3:** Graph notes only—no final answer or fleet rank.

##### K. Workflow optimization

- **K-1:** After research, sequential.  
- **K-2:** Single KG tool.  
- **K-3:** Fixed edge—no dynamic fan-out.

##### L. Sequential and parallel processing

- **L-1:** After research; before synthesis.  
- **L-2:** None.  
- **L-3:** Fixed sequential only.

*(Maps to `GRAPH_AGENT_SYSTEM` in `app/agents/prompts.py`.)*

**Stage-1 Coordinator (synthesis):** D–L from §10.2 (qa subset)—sequential after research+graph; no parallel invent.

---

### 10.8 Mapping to runtime prompts (target)

| Template (§) | Runtime target | Notes |
|--------------|----------------|-------|
| Coordinator §10.2 | `RECOMMEND_SYNTHESIS_*` + policy; Stage-1 `SYNTHESIS_AGENT_*` for qa | Phase **7.7**; state §10.0.3 / §10.2 D |
| Delegator §10.3 | Router node (code-first; optional short policy prompt) | Writes `work_plan` only |
| Worker [5] §10.4 | `PROJECT_WORKER_*` (may subsume research+graph+decompose) | Writes `project.*` |
| Worker [6] §10.5 | `FLEET_WORKER_*` | Writes `fleet_by_need[need_id]` |
| Worker [7] §10.6 | `PRICING_WORKER_*` | Writes `prices_by_need[need_id]` |
| §10.7 Research/Graph | Existing `RESEARCH_AGENT_*` / `GRAPH_AGENT_*` | `ProjectKnowledgeAgentState` |
| Recommend state type | `RecommendAgentState` TypedDict + F-2 validation | **S7.0 as-built** (`app/agents/recommend_state.py`); graph wire S7.3–7.4 |

Phase 7.7 implements recommend prompts **from these templates (A–L)**. Stage-1 prompts remain until recommend mode ships; do not contaminate Q&A synthesis with fleet instructions. §10.0.1–§10.0.11 cover tools through **sequential/parallel processing**. Fleet LTM = **`postgres_haystack` synced from `postgres-primary`**. Inject tools via DI; assert traces; illegal transitions rejected; preserve session keys; tool-backed decisions only; **respect DAG: seq within need, parallel across needs (capped)**.

---

### 10.9 Non-agents (no full A–L agent template)

These nodes **are environment / memory / workflow infrastructure**, not full agent personas:

| Node | Seq / par role |
|------|----------------|
| **[4] indexing gate** | **Mandatory sequential** blocker before recommend |
| In-process tools | Sequential or parallel only as Worker plan allows |
| `postgres_haystack_sync` | **Background parallel** to requests (not in-graph) |
| Job workers (202, Neo4j populate) | **Background parallel**; backpressure via queue/SSE |

Indexing gate checklist: validate `user_id` + sources + MIME → run index service → stamp meta → KG hard-fail → set `indexing_ok`. Does not read fleet **`assets`/`bookings`**.

---

## 11. Relation to implementation plan Phase 7

| Phase 7 step | C/W/D impact | Status |
|--------------|--------------|--------|
| **S7.0** state + F-2 | STM partitions; illegal writes rejected | **As-built** |
| **S7.1** fleet/needs tools | Execution layer; allowlist; fake/SQL DI | **As-built** |
| **S7.2** Neo4j tools | Optional graph templates | Todo |
| **S7.3** recommend LangGraph | DAG §10.0.10–§10.0.11: **seq** gate→[5]→plan; **par** across needs (capped); **seq** [6]→[7] within need; barrier [8] | Todo |
| **S7.4** tool-free synthesis | Coordinator **[8]** sequential barrier — A–L; merge tool-backed partitions only | Todo |
| **S7.5** HTTP Call 2 enrich | Same quote DTO; multi-agent behind flag | Todo |
| **S7.6** `tool_traces` | `role` / `need_id` / duration; G-1 metrics feed K-3 / parallel width | Todo |
| **S7.7** recommend prompts | **Derive from §10 A–L** (incl. **seq/par** L-1/L-2/L-3); tool DI; tests: within-need order + across-need parallel + no invent | Todo |

**Safeguards unchanged:** no recommend if **[4]** failed; no invent inventory; no silent zeros; no free-form SQL/Cypher in nodes.

---

## 12. Hard rules (restated — do not dilute)

1. Tools are **in-process only** (no FastMCP/MCP server).  
2. **[4]** is a **forced non-agent tool edge** under Coordinator; files never enter LLM context as raw bytes.  
3. Synthesis **[8]** is **tool-free**; must not invent `asset_id` or rates.  
4. Narrow tools; no mega-tool `recommend_everything`.  
5. KG-1 (project) and KG-2 (fleet Neo4j) stay separate planes.  
6. Agent **Worker** ≠ job **worker** (ops).  
7. Delegator is an **explicit router**, not unrestricted ReAct.  
8. Every agent role has an **A–L instruction template** (§10: … + **sequential/parallel processing** L-1/L-2/L-3); non-agents do not.  
9. Fleet/pricing context from Postgres-Haystack **`heavy_rental`** (`assets`, `bookings`, …) is **tool-mediated only** — never free-form SQL in agent nodes.  
10. Agents write **only their state partition**; global invariants in §10.0.3 hold for the whole graph.  
11. Environment is **role-partitioned** (§10.0.4) — no mega-agent with all integration points.  
12. Prefer **event/edge-driven** updates; **validate** transitions before apply (§10.0.5) — no busy-polling, no illegal writes.  
13. **Adapt only within hard rules** (§10.0.6) — never invent stock/rates to improve fill-rate metrics.  
14. **Fleet LTM** is **`postgres_haystack`**, **synced from `postgres-primary`** — read mirror only; primary remains write SoT (§10.0.7).  
15. **Context hierarchy + switching** (§10.0.8): preserve session keys; merge tool-backed facts; never invent gaps.  
16. **Decisions** use retrieval + patterns + optimization only over **tool-backed** options (§10.0.9)—never invent to optimize.  
17. **Workflow** respects critical path and within-need fleet→price order; cap parallel fan-out; never skip gate/availability under load (§10.0.10).  
18. **Sequential vs parallel** (§10.0.11): gate and within-need fleet→price are **must-seq**; across-need fan-out is **may-par (capped)**; Workers do not spawn siblings.

---

## 13. Non-goals

- Runtime rename of Stage-1 nodes in this study’s delivery  
- Free-form LLM Delegator that re-plans every turn  
- Indexing as an LLM Worker agent  
- Changing OpenSpec FR text in this docs-only change  
- Spring saga redesign  
- Shipping `app/agents/prompts.py` rewrites in this docs-only change (Phase 7.7)

---

## 14. Open questions (remaining)

1. Max parallel fan-out width (cap concurrent need Workers)?  
2. Should Call 3 Q&A adopt an explicit Delegator, or keep fixed edges forever?  
3. Exact metric names / log schema ownership (app vs platform)?  
4. Delegator: pure code router vs short LLM policy prompt on top of allowlists?  

*(Product decisions for [4] placement, router Delegator, per-need fan-out, and C/W/D labels are **closed** in §4.3. Template structure **A–L** is **closed** in §10.)*

---

## 15. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-11 | Initial: C/W/D as alias layer; **[4]** forced non-agent edge; explicit Delegator router; fan-out Workers per need; C/W/D logs |
| **1.0.1** | 2026-08-11 | Authority note; folder-wide alignment with dual-plane 2.6.0 / impl plan 1.2.0 |
| **1.1.0** | 2026-08-11 | **§10 Agent instruction templates** (A objectives + B task specs) for all C/W/D agents + Stage-1 specializations |
| **1.2.0** | 2026-08-11 | **§10 C Contextual awareness** + L1–L7; Postgres-Haystack `heavy_rental` tables (`assets`, `bookings`, `payments`, `rental_plan`, `recommendation_items`, `ai_recommendations`) |
| **1.3.0** | 2026-08-11 | **§10 D State space representation**; shared `RecommendAgentState` target; per-agent read/write partitions |
| **1.4.0** | 2026-08-11 | **§10 E Environment modeling** + §10.0.4 static/dynamic shared environment; per-agent systems/rules/dynamics |
| **1.5.0** | 2026-08-11 | **§10 F Integration patterns** (F-1 event-driven + F-2 validation); §10.0.5 event catalog |
| **1.6.0** | 2026-08-11 | **§10 G Monitoring and adaptation** (G-1 metrics + G-2 bounded adaptation); §10.0.6 |
| **1.7.0** | 2026-08-11 | **§10 H Agent memory** (STM/LTM/episodic); fleet LTM = **`postgres_haystack` synced from `postgres-primary`** |
| **1.8.0** | 2026-08-11 | **§10 I Context management** (hierarchy global/session/task + switching preserve/restore/merge); §10.0.8 |
| **1.9.0** | 2026-08-11 | **§10 J Decision integration** (retrieval + patterns + optimization); §10.0.9; role decision authority |
| **2.0.0** | 2026-08-11 | **§10 K Workflow optimization** (DAG, fan-out caps, resources, dynamic adjustment); §10.0.10 |
| **2.1.2** | 2026-08-12 | **S7.0 + S7.1 as-built:** `RecommendAgentState` + F-2 validation; fleet tool catalog + DI factory; §11 status table |
| **2.1.1** | 2026-08-12 | HTTP Call 2 = recommend, Call 3 = chatbot Q&A (align portal) |
| **2.1.0** | 2026-08-11 | **§10 L Sequential and parallel processing** (must-seq vs may-par); §10.0.11 |

---

## 16. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Use Coordinator / Worker / Delegator vocabulary? | **Yes** — alias over Orchestrator design |
| Replace “Orchestrator / tools / synthesis” as primary terms? | **No** — keep both; C/W/D for roles/observability |
| **[4] indexing** | **Forced non-agent tool edge** under Coordinator |
| Delegator | **Explicit router node** + **primary workflow optimizer** / parallel-width chooser |
| Fleet/pricing Workers | **Fan-out per need** (parallel across N, sequential fleet→price within need) |
| Logs/metrics | **Emit `role` = coordinator \| delegator \| worker** (+ duration, need_id) |
| Agent instruction shape | **A–L** for every agent (§10) |
| State space / working memory | LangGraph state; Workers write **only their partition**; DTOs not raw DB rows |
| Environment modeling | Shared static/dynamic model §10.0.4; **role-partitioned** integration surfaces |
| Integration patterns | **F-1** event/edge-driven (no busy-poll); **F-2** validate transitions before apply |
| Monitoring / adaptation | **G-1** metric classes §10.0.6; **G-2** degrade/cap/fallback—**never invent** to improve fill rate |
| Memory architecture | **H-1** STM run state; **H-2** project store/KG-1 + fleet on **`postgres_haystack` (mirror of `postgres-primary`)**; **H-3** traces + `ai_recommendations` / items |
| Context management | **I-1** global/session/task; **I-2** preserve–restore–merge; multi-need = multi-task switch |
| Decision integration | **J-1** retrieve · **J-2** patterns · **J-3** optimize **only over tool-backed options** |
| Workflow optimization | **K-1** critical path + priorities · **K-2** resource caps · **K-3** dynamic fan-out/load adjust—never skip gate |
| Sequential vs parallel | **L-1** must-seq (gate, fleet→price within need, Q&A chain) · **L-2** may-par across needs (capped) · **L-3** hybrid DAG |
| Fleet DB context | **`postgres-primary`** = write SoT; **`postgres_haystack` / `heavy_rental`** = synced read mirror for agents; **`recommendation_items`/`ai_recommendations`** = episodic output |
| Free ReAct mega-agent | **No** |
| FastMCP tool server | **No** |
| Synthesis invents rates/assets? | **No** |
