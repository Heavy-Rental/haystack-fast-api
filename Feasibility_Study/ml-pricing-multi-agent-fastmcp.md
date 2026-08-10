# Feasibility Study: ML Pricing Model for Multi-Agent + FastMCP Recommend Path

| Field | Value |
|-------|--------|
| **Document type** | Architecture / ML integration feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 1.0.0 |
| **Application** | `haystack-fast-api` equipment recommendation |
| **Question** | Given existing dynamic-pricing docs and as-built code, what context is required for the Multi-Agent Orchestrator to call an ML pricing tool (including via **FastMCP**) after indexing step **[4]**, and is that **feasible**? |
| **Primary sources** | [`docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md) · [`docs/dynamic-pricing-execution-plan.md`](../docs/dynamic-pricing-execution-plan.md) · [`openspec/specs/dynamic-pricing/`](../openspec/specs/dynamic-pricing/) · `ml-experiments/` · `app/services/pricing_client.py` |
| **Related studies** | [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) §4.1 [7] · [`fastmcp-tool-consolidation-multi-agent.md`](./fastmcp-tool-consolidation-multi-agent.md) · [`mcp-multi-agent-devcontainer-digitalocean.md`](./mcp-multi-agent-devcontainer-digitalocean.md) |

> **Normative product rules** for pricing remain in OpenSpec dynamic-pricing (and future Phase 2 package). This study maps that work into the **dual-plane / FastMCP recommend** architecture. Personal masterplan notes are **decision context**, not a substitute for OpenSpec.

---

## 1. Executive summary

### Question

Can the **ML pricing model** (XGBoost experimental path in `ml-experiments/`, production target `app/services/pricing/`) supply **enough structured context** for Multi-Agent **recommend after [4]**, when agents invoke tools from a **FastMCP** catalog that also includes **Postgres-Haystack** and **Neo4j**?

### Verdicts

| Question | Result |
|----------|--------|
| ML pricing usable as a **narrow FastMCP tool** (`predict_asset_price`)? | **GO** |
| Tool returns **`price_per_day` (+ clamp metadata)**; app/orchestrator computes **total**? | **GO** (matches masterplan) |
| Pricing is **public Spring-facing HTTP**? | **NO** — internal tool only (in-process or FastMCP private network) |
| Masterplan “in-process, not HTTP route” vs FastMCP? | **Compatible** — FastMCP is **agent tool transport**, not a renter/public price API; server may still call `predict_price()` in-process |
| Feature vector complete from fleet + booking data alone? | **Almost** — asset features from Postgres-Haystack; **live** `period_utilization` needs booking mirror + **Phase 1e**; `distance_km` needs site/distance context |
| Can Neo4j / project KG enrich pricing features? | **CONDITIONAL** — good for **explain/rank context**, not for inventing numeric features the model was not trained on |
| Category fallback when model missing? | **GO** — as-built `pricing_client` already falls back |
| Package model on FastMCP sidecar image? | **GO** with version pin + artifact mount; or keep pricing on app process and only fleet tools on MCP (**hybrid**) |
| Phase status vs recommend R5 | **Phase 1c/1d done** (scratch); **1e / Phase 2 production package open** — recommend agents can use experimental path + fallback until 2a |

**Overall:** **GO with prerequisites.** The ML model is a **strong fit** as one FastMCP tool in the post-[4] recommend graph. Feasibility studies previously only named `predict_asset_price`; this document adds **feature contracts, guardrails, live signals, cold-start, and multi-agent feature assembly** from `docs/`.

---

## 2. Baseline from docs/ and code

### 2.1 Document map

| Source | Role |
|--------|------|
| `docs/dynamic-pricing-masterplan.md` | Locked decisions: target, features, architecture, rejected ideas |
| `docs/dynamic-pricing-execution-plan.md` | Phases 1a–1e, 2a–2b status, open blockers |
| `openspec/specs/dynamic-pricing/` | Normative FR when Phase 2 lands |
| `ml-experiments/predict_price.py` | Experimental `predict_price()` + static category guardrails |
| `ml-experiments/feature_schema.py` / `pricing_tables.py` | Feature build + bins / rates |
| `app/services/pricing_client.py` | App import site → ml-experiments or category fallback |
| `app/pipelines/predict_price_adapter.py` | Haystack component: prices each candidate |

### 2.2 Phase status (execution plan)

| Phase | Status | Relevance to FastMCP / agents |
|-------|--------|--------------------------------|
| **1a–1b** Synthetic data + train + SHAP | **Done** | `model.pkl` + feature schema exist |
| **1c** `predict_price()` prototype | **Done** | Callable today via `pricing_client` |
| **1d** `period_utilization`, `lead_time_days` | **Done** (ml-experiments) | Optional kwargs + defaults in prototype |
| **1e** Live SQL for utilization | **Not started** | Needs Asset/Booking models + repo; blocked on Spring enum/casing confirm |
| **2a** `app/services/pricing/` | **Not started** | Per-asset min/max clamp; production package |
| **2b** Pipeline integration tests | **Partial** | Adapter + client already used on service recommend path |
| **3** Scheduled retrain / seed blend | **Later** | Cold-start bootstrap → blend → cutover |

### 2.3 Locked model contract (from masterplan)

| Item | Decision |
|------|----------|
| **Target** | `price_per_day` (not total) |
| **Total price** | App/orchestrator: `daily_rate × duration_days` (+ fees later) |
| **Call style** | **In-process function** (not public `/predict-price` REST) |
| **Guardrails (prod)** | Clamp to **per-asset** `minDailyRate` / `maxDailyRate` |
| **Guardrails (prototype)** | Static per-category `CATEGORY_BASE_RATE` (stand-in only) |
| **Currency (as-built client)** | SGD; `deposit_rate` 0.30 |
| **No public renter price API** | Prediction internal to recommend path |

### 2.4 Feature set (model inputs)

| Feature | Type | Source in multi-agent world | Notes |
|---------|------|----------------------------|--------|
| `category` | One-hot name | Asset / fleet row (**Postgres-Haystack**) | Never raw `category_id` FK |
| `condition` | Ordinal 0–3 | Asset.condition | NEEDS_REPAIR…EXCELLENT |
| `duration_days` | Continuous | Request / Booking window | From Spring or agent state |
| `capacity` | Numeric | Asset | Within-category scale |
| `distance_km` | Numeric | Job site vs yard | Phase 1: sampled/proxy; real geocode deferred; default in adapter **15.0** today |
| `platform_height` | Numeric or **NaN** | Asset (aerial only) | **NaN** for forklift/excavator — not 0 |
| `period_utilization` | [0,1] live aggregate | **Bookings** on same category+spec-band | Needs Phase **1e** + booking mirror |
| `lead_time_days` | Derived | `startDate − today` | Optional; default 0.0 in prototype |

**Rejected / out of scope for model:** `operator_required`, fuel price, raw FK ids, `vehicle_vs_static`, `booking_month` (seasonality via utilization instead).

---

## 3. Fit to Multi-Agent Orchestrator after step [4]

### 3.1 Role in recommend graph

```text
[4] Indexing succeeds (project Pgvector + KG-1)
        │
        ▼
[5] Project / needs agents  → project_* tools, decompose_needs
[6] Fleet agents            → retrieve_fleet_*, Neo4j context
        │  candidates: category, condition, capacity, platform_height, asset_id, rates…
        ▼
[7] Pricing agent           → FastMCP predict_asset_price (per candidate)
        │  inputs assembled from [6] + request window + optional live util
        ▼
[8] Synthesis               → rank + recommendation JSON (orchestrator)
```

| Layer | Pricing responsibility |
|-------|------------------------|
| **Orchestrator** | Decide when to price; pass candidate fields; compute total; rank with price + availability + project fit |
| **FastMCP `predict_asset_price`** | Run model + guardrail clamp; return daily rate + metadata |
| **Postgres-Haystack** | Asset attributes + booking utilization query (1e+) |
| **Neo4j** | Optional **context** for agents (related assets, graph paths) — **not** a substitute feature vector unless explicitly engineered into schema |
| **Project KG / Pgvector** | Site constraints, duration hints, equipment types mentioned in spec — feed **agent reasoning** and maybe `distance_km` / duration, not untrained model features |

### 3.2 Feasibility: “more context” for pricing

| Context channel | Can improve pricing? | How |
|-----------------|----------------------|-----|
| **Postgres-Haystack Asset** | **Yes — required** | category, condition, capacity, platform_height, min/max rates |
| **Postgres-Haystack Booking** | **Yes — for live util / lead time** | Phase 1e `period_utilization`, `lead_time_days` |
| **Neo4j KG-2** | **Indirect** | Rank/explain; do **not** inject arbitrary graph embeddings into XGBoost without retrain |
| **Project Pgvector / KG-1** | **Indirect** | Infer duration, site, equipment class for tool args; optional `distance_km` estimate |
| **ML model itself** | **Yes** | Encodes duration discounts, condition, scarcity (once util live) |

**Conclusion:** More **structured** context **should** be assembled **before** calling the model (complete feature row). More **narrative** KG context helps the **orchestrator**, not the raw model, unless features are redesigned and retrained.

### 3.3 Recommended FastMCP tool contract (illustrative)

```text
predict_asset_price(
  category: str,
  condition: str,
  duration_days: float,
  capacity: float,
  distance_km: float,
  platform_height: float | null,
  period_utilization: float | null = null,  # live or default
  lead_time_days: float = 0.0,
  asset_id: str | null = null,              # for prod min/max guardrails
) -> {
  daily_rate, total_price?, currency, deposit_rate?,
  model_version, was_clamped, min_bound, max_bound, explanation
}
```

Align with `PriceResult` / `PricePrediction`. Prefer computing `total_price` in one place (client or tool) consistently with `pricing_client` today.

### 3.4 In-process vs FastMCP packaging

| Mode | When | Notes |
|------|------|--------|
| **A. In-process in app** (as-built) | Now / hybrid | `pricing_client` → ml-experiments; no MCP |
| **B. FastMCP wraps same `predict_price`** | M5 recommend tools | Model + joblib in MCP image; DSN for 1e util query on server |
| **C. Pricing stays on app; fleet on MCP** | Safer multi-instance if model load heavy | Orchestrator calls mix of tools |

Masterplan’s “no public HTTP price API” remains: FastMCP is **private** agent transport on `heavy-rental-network`, not Spring’s portal.

---

## 4. Data-plane prerequisites

| Prerequisite | Why pricing needs it | Track |
|--------------|----------------------|-------|
| Asset rows on **Postgres-Haystack** | Category, condition, capacity, height, rates | D1 / T1 fleet sync |
| Booking rows (non-cancelled) | Live `period_utilization` | D1 + Phase **1e** |
| Confirm Spring `BookingStatus` + column casing | 1e blocked without it | Open item in execution plan |
| **I1 Pgvector** | Not required for price math; required for full post-[4] recommend story | I1 |
| Neo4j T3 | Graph context for agents, not model input | T3 |
| `model.pkl` + feature_schema version pin | Reproducible tool | Artifacts in image or volume |
| Phase **2a** per-asset clamp | Production guardrails | Phase 2 |

Without 1e, tool still **GO** with prototype defaults (static utilization / lead_time=0) + category fallback — weaker scarcity signal.

---

## 5. Guardrails, fallback, and safety

| Concern | Guidance |
|---------|----------|
| Out-of-range model output | Clamp to min/max (category stand-in now; per-asset in 2a) |
| Missing model.pkl | Category table fallback (as-built) — **must** surface `model_version` / explanation |
| Silent zero prices | **Forbidden** — orchestrator must fail soft or use fallback with trace |
| Multi-replica model drift | Pin artifact version; shared volume or image bake |
| Retrain cold-start | Synthetic bootstrap → blend real bookings → per-category cutover (Phase 3 design in masterplan) |
| Explainability | SHAP offline; runtime `explanation` string only (lightweight) |

---

## 6. What agents must **not** do

- Feed free-form LLM text as model features without schema mapping  
- Use Neo4j Cypher results as raw numeric features without schema change + retrain  
- Call pricing before candidates exist (after [6])  
- Expose FastMCP pricing on the public internet  
- Treat MCP as source of truth for rates vs Spring primary asset rates  
- Re-scale `daily_rate` for a different duration without a new prediction  

---

## 7. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| 1e / Spring schema unconfirmed | High for live util | Keep optional kwargs; confirm enum before 1e |
| Prototype guardrails ≠ production | Medium | Document in tool explanation; Phase 2a required for prod |
| MCP image without model artifacts | High | Compose volume `ml-experiments/artifacts` or bake pkl |
| Feature mismatch app vs MCP | High | Shared library / same feature_schema module |
| Distance always default 15 km | Medium | Later: site from project tools / booking site fields |
| Heavy XGBoost load per request on MCP | Medium | Model load once at process start; batch candidates optional |

---

## 8. Phasing (align with existing tracks)

| Phase | Work | Depends on |
|-------|------|------------|
| **P0** | This study + tool allowlist entry `predict_asset_price` | — |
| **P1** | Keep as-built `pricing_client` on service recommend path | Done |
| **P2** | Phase 1e live utilization through adapter | Schema confirm + repo |
| **P3** | Phase 2a `app/services/pricing/` + per-asset clamp | P2 optional |
| **P4** | FastMCP tool wraps production or experimental predict | M5; model package |
| **P5** | Recommend graph [7] always prices via tool when `include_pricing` | M6 + [4] gate |
| **P6** | Phase 3 retrain / blend | Real bookings volume |

Do **not** block T0–T1 or I1 on full Phase 2 pricing package.

---

## 9. Cross-links: what to add to other feasibility files

| File | Add |
|------|-----|
| Dual-plane §4.1 [7] / §4.6.3 | Point here for feature list, guardrails, 1e dependency |
| Consolidation §5.1 / §5.3 | Feature assembly table; hybrid pricing packaging |
| MCP multi-agent M5 | Model artifact env; optional `period_utilization` from `db` |
| Spring resilience | No change to wire; call 3 still REST; pricing stays internal |

---

## 10. Open questions

1. Prefer **Mode B** (price on FastMCP) vs **Mode C** (price in-app, fleet on MCP) for first R5 demo?  
2. Should `distance_km` be filled from project-spec agents or stay default until geocoding?  
3. Retrain interval monthly vs quarterly (Phase 3)?  
4. When Phase 2a lands, retire ml-experiments path from `pricing_client` in the same PR?  

---

## 11. References

- [`docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md)  
- [`docs/dynamic-pricing-execution-plan.md`](../docs/dynamic-pricing-execution-plan.md)  
- [`openspec/specs/dynamic-pricing/spec.md`](../openspec/specs/dynamic-pricing/spec.md)  
- `ml-experiments/predict_price.py`, `feature_schema.py`, `pricing_tables.py`  
- `app/services/pricing_client.py`, `app/pipelines/predict_price_adapter.py`  
- Dual-plane recommend steps: [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md)  

---

## 12. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial study: ML pricing + multi-agent FastMCP from docs/; features; guardrails; 1e/2a gaps; post-[4] [7] |

---

## 13. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| ML pricing as FastMCP tool? | **Yes (GO)** |
| Public price HTTP API? | **No** |
| Target variable | **`price_per_day`**; total = rate × days |
| Feature sources | **Postgres-Haystack** assets + bookings; request window; optional project-derived distance |
| Neo4j / project KG | **Context for agents**, not untrained model features |
| Live utilization | **Phase 1e** + fleet booking mirror; defaults until then |
| Guardrails | Category stand-in now → **per-asset min/max** in Phase 2a |
| Fallback | Category table; never silent zeros |
| Packaging | Shared schema + pin `model.pkl`; FastMCP or in-app hybrid |
| After [4] recommend | Pricing agent step **[7]** after fleet candidates **[6]** |
