# Feasibility Study: Multi-Agent Synthesis Output — Recommended Assets + Predicted Rent Price

| Field | Value |
|------

> **Call numbering (as-built 2026-08-12):** HTTP **Call 2** = recommend / quote (`getassetrecommendations`). HTTP **Call 3** = chatbot Q&A (`project-knowledge/query`). This study’s multi-agent **synthesis [8] → assets + prices** is the **Call 2 recommend** path (richer graph may replace MVP behind the same route). Stage-1 Q&A synthesis is **Call 3**, not Call 2.

-|--------|
| **Document type** | Architecture / agent orchestration feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 1.4.5 |
| **Application** | `haystack-fast-api` Multi-Agent Orchestrator (LangGraph) |
| **Question** | Can the **synthesis** step under Multi-Agent Orchestrator output **recommended assets** and **predicted rent price** grounded in the **uploaded project specification**? |
| **As-built** | `app/agents/nodes.py` (`make_synthesis_node`), `app/agents/prompts.py`, Stage-1 Q&A only |
| **Target contract** | Align with `RecommendFromProjectSpecResponse` / `RecommendationItem` + `PricingPayload` (`app/schemas/recommendations.py`) |
| **Related** | [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) §4.1 [5]–[8] · [`ml-pricing-multi-agent.md`](./ml-pricing-multi-agent.md) · [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) |

---

## 1. Executive summary

### Question

After a project-spec is uploaded and indexed (**step [4]**), can Multi-Agent **synthesis ([8])** emit:

1. **Recommended assets** (equipment / fleet selections), and  
2. **Predicted rent price** (daily rate / total for the rental window),  

using evidence from the **uploaded project specification** plus fleet/pricing tools?

### Verdicts

| Question | Result |
|----------|--------|
| **Target architecture: synthesis outputs assets + prices?** | **GO** |
| **As-built Stage-1 synthesis already does this?** | **No** — Q&A markdown only; **forbids** inventing fleet/rates |
| Synthesis **calls** pricing / fleet tools itself? | **No** — synthesis is **tool-free**; consumes prior agent/tool results |
| Prices from LLM free-text without `predict_asset_price`? | **NO** — must use ML/fallback tool results only |
| Assets from project KG alone without fleet tools? | **NO** for production — project KG-1 has needs/constraints; **Postgres-Haystack / Neo4j** supply inventory |
| Grounding in uploaded project-spec? | **GO** — via [4] index + project tools [5] → needs/constraints into rank |
| Structured output vs markdown only? | **GO** — prefer structured JSON matching recommend DTO (+ optional narrative) |
| Prerequisites | [4] success; fleet mirror; pricing tool; recommend agent graph [5]–[7] before [8] |

**Overall:** **GO for target (R5 / M6).** Synthesis **can and should** assemble **recommended assets + predicted rent prices** on the **HTTP Call 2 recommend** path, but only as a **merge/rank node** over tool outputs—not by inventing stock or rates. Stage-1 **chatbot Q&A** synthesis is **HTTP Call 3** (`.../query`); as-built Call 2 MVP uses `RecommendationService` until full C/W/D graph lands.

---

## 2. As-built vs target

### 2.1 As-built (Stage-1)

```text
research_agent → project_vector_search
graph_agent    → project_kg_query
synthesis_agent → final_answer (markdown)   # NO tools, NO assets, NO prices
```

From `SYNTHESIS_AGENT_SYSTEM` / prompts:

- Tools: **none**  
- **Do not invent** equipment fleet inventory, rates, or bookings  
- Output: grounded Q&A answer (Vector vs Graph cites)

### 2.2 Target (post-[4] recommend graph)

```text
[4] indexing gate (Coordinator; non-agent tool edge → Pgvector + KG-1)
[5] project / needs Worker     → project_* , decompose_project_needs
    Delegator router           → expand work items per need_id
[6] fleet / graph Workers ×N   → retrieve_fleet_*, neo4j_*, availability  (per need)
[7] pricing Workers ×N         → predict_asset_price  (per need / candidates)
[8] SYNTHESIS (Coordinator)    → structured recommendation
      results_by_need[]:
        need_id, item { asset_id, equipment_type, rank, rationale,
                        pricing { daily_rate, total_price, currency, … } }
```

**Role vocabulary:** synthesis **[8]** is **Coordinator**-owned and tool-free; **[5]–[7]** are **Workers** (fleet/pricing **fan-out per need**); routing is an **explicit Delegator**; **[4]** is a **forced non-agent gate** under the Coordinator — see [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md).

**Building blocks as-built (S7.0–S7.6):** `RecommendAgentState` + F-2 validation (`app/agents/recommend_state.py`); allowlisted tools via `fleet_tools` + `tool_factory`; recommend DAG (`app/agents/recommend_graph.py` / `recommend_nodes.py`); **stub Coordinator [8]** (`app/agents/recommend_synthesis.py`); Call 2 HTTP enrich behind `RECOMMEND_VIA_AGENT_GRAPH` (`SessionRecommendService`); G-1 `tool_traces` (`recommend_traces.py`). Prompts A–L remain **S7.7**.

**Instruction template:** Coordinator synthesis behavior is defined in C/W/D **§10.2** (**A–L**). **L-1** sequential barrier after need pipelines; **L-2** does not parallel-invent. Multi-need **parallel** fan-out is Delegator/Workers; synthesis is **sequential** merge. **J-3** ranks only priced STM candidates. Fleet via Workers on **`postgres_haystack`←`postgres-primary`** (C/W/D §10.0.5–§10.0.11).

Project-spec document grounds **what** is needed; fleet + pricing tools ground **what is offered** and **at what rate**.

---

## 3. What synthesis is allowed to do

| Responsibility | In synthesis? | Source of truth |
|----------------|---------------|-----------------|
| Choose rank order among **already priced** candidates | **Yes** | Policy + tool hits + project constraints |
| Fill `RecommendationItem` + `PricingPayload` | **Yes** | Copy prices from [7]; assets from [6] |
| Write human rationale tied to project-spec passages | **Yes** | [5] research/KG notes + tool traces |
| Call SQL / XGBoost from synthesis | **No** | Prior agents only |
| Invent asset_id or daily_rate | **No** | — |
| Skip [4] and still recommend | **No** | Gate |

### 3.1 Output contract (illustrative — align OpenSpec FR-010 when reattached)

Prefer **structured** state fields (not only markdown):

```text
recommendation:
  recommendation_id: str
  start_date / end_date: optional
  results_by_need: [
    { need_id, item: { equipment_type, asset_id, rank, rationale,
                       pricing: { daily_rate, total_price, currency,
                                  deposit_rate, model_version, explanation },
                       availability },
      warnings: [] }
  ]
  tool_traces: […]
  sources_used: […]   # project_vector_search, retrieve_fleet_*, predict_asset_price, …
final_answer: optional markdown summary for humans
```

Map 1:1 to existing `RecommendFromProjectSpecResponse` / Call 2 quote envelope where possible so Spring Call 2 stays stable.

### 3.2 Stub vs LLM synthesis

| Mode | Feasible for assets+prices? |
|------|----------------------------|
| **Stub** (deterministic merge) | **GO** and preferred for CI — pick top candidate per need, attach tool pricing |
| **LLM** synthesis | **GO** for rationale text only; **must not** override numeric prices or invent assets — validate against tool payload |

---

## 4. Grounding chain from uploaded project-spec

```text
Upload project-spec
    → [4] Index + KG-1
    → [5] Vector/KG/needs tools  → equipment hints, duration, site constraints
    → [6] Fleet tools (Postgres-Haystack + Neo4j)
    → [7] predict_asset_price
    → [8] Synthesis: match needs → assets + attach prices + rationale
```

| If missing… | Synthesis behaviour |
|-------------|---------------------|
| [4] failed | **No recommend** |
| No fleet match | `item: null` + warnings (as FR-010 style) |
| Pricing tool failed | Fallback pricing with `model_version` explained, or item with `pricing: null` + warning — never silent zeros |
| No rental dates | Duration default policy (document) or warning |

---

## 5. Feasibility matrix

| Claim | Feasible? | Notes |
|-------|-----------|--------|
| Synthesis outputs recommended assets from project-spec journey | **GO** (target) | Needs [5]+[6] before [8] |
| Synthesis outputs predicted rent price | **GO** (target) | From [7] tool only |
| Same graph as Stage-1 Q&A synthesis | **Extend** | New recommend graph or mode flag `qa` vs `recommend` |
| Single HTTP after upload returns recommend | **RISKY** | Prefer split ingest vs recommend or 202 job (resilience study) |
| Synthesis replaces RecommendationService entirely | **GO later** | Service path can become thin façade over orchestrator |

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| LLM hallucinates prices | Structured merge; schema validation; LLM only for rationale |
| Project-spec-only “recommend” without fleet | Product forbid; empty item + warning |
| Stage-1 prompt still forbids fleet in shared synthesis | Separate `RECOMMEND_SYNTHESIS_*` prompts / node |
| Partial tool failures | Per-need warnings; don’t fail entire envelope unless hard policy |

---

## 7. Phasing

| Phase | Work |
|-------|------|
| **Now** | Stage-1 synthesis stays Q&A-only |
| **R5 / M6** | Recommend graph [5]–[8]; synthesis emits structured assets+prices |
| **Tests** | Stub synthesis: fixture tool hits → DTO equals expected rates/assets |
| **OpenSpec** | Reattach FR-010 response to agent path when product ready |

---

## 8. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial: synthesis **GO** for assets+prices as merge node; as-built Q&A gap |
| **1.1.0** | 2026-08-10 | Tools are in-process (no FastMCP) |
| **1.2.0** | 2026-08-11 | §2.2 cross-link Coordinator / Worker / Delegator vocabulary (synthesis = Coordinator) |
| **1.3.0** | 2026-08-11 | Target graph: Delegator + [6]×N / [7]×N; decision card fan-out / Coordinator |
| **1.3.1** | 2026-08-11 | Point synthesis persona to C/W/D §10.2 A/B instruction template |
| **1.3.2** | 2026-08-11 | Coordinator template includes **C** contextual awareness |
| **1.3.3** | 2026-08-11 | Coordinator **D** state space / partition write rules for synthesis |
| **1.3.4** | 2026-08-11 | Coordinator **E** environment: no fleet tools at synthesis |
| **1.3.5** | 2026-08-11 | Coordinator **F** integration: events + state validation before merge |
| **1.3.6** | 2026-08-11 | Coordinator **G** monitoring/adaptation: no invent to improve fill rate |
| **1.3.7** | 2026-08-11 | Coordinator **H** memory: STM merge; episodic persist; no direct fleet LTM |
| **1.3.8** | 2026-08-11 | Coordinator **I** context management: merge multi-need task contexts |
| **1.3.9** | 2026-08-11 | Coordinator **J** decision integration: rank only tool-backed candidates |
| **1.4.0** | 2026-08-11 | Coordinator **K** workflow: barrier synthesis after fan-out |
| **1.4.5** | 2026-08-12 | **S7.5 as-built:** Call 2 graph enrich behind `RECOMMEND_VIA_AGENT_GRAPH` (same quote DTO) |
| **1.4.4** | 2026-08-12 | **S7.4 as-built:** stub Coordinator [8] + S7.3 DAG; HTTP Call 2 still MVP (S7.5) |
| **1.4.3** | 2026-08-12 | Note S7.0/S7.1 as-built building blocks (state + fleet tools); synthesis graph still TARGET |
| **1.4.2** | 2026-08-12 | Align HTTP Call 2 = recommend, Call 3 = chatbot Q&A |
| **1.4.1** | 2026-08-11 | Coordinator **L** sequential barrier vs parallel need ribs |

---

## 9. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Synthesis outputs recommended assets + rent prices? | **Yes (target GO)** |
| As-built today? | **No** (Q&A only) |
| Synthesis role | **Coordinator [8]** (tool-free merge) |
| How prices appear | Only from **`predict_asset_price`** via **pricing Workers [7]×N** (or documented fallback) |
| How assets appear | Only from fleet tools via **fleet Workers [6]×N** after needs extraction |
| Multi-need | **Fan-out Workers per need**; partial failure → per-need warning |
| Project-spec role | Grounds needs/constraints via [4]+[5] |
| Synthesis tools | **None** — merge/rank only |
| Output shape | Structured recommend DTO + optional markdown |
