# Feasibility Study: ML Pricing Model for Multi-Agent Recommend Path

| Field | Value |
|-------|--------|
| **Document type** | Architecture / ML integration feasibility study |
| **Status** | Complete (study); **S6 tool as-built**; **S7.3 Workers [7]×N as-built**; **S7.5 HTTP enrich as-built** (`RECOMMEND_VIA_AGENT_GRAPH`, default off) |
| **Date** | 2026-08-10 (study); 2026-08-12 (S6 tool) |
| **Version** | 1.2.4 |
| **Application** | `haystack-fast-api` equipment recommendation |
| **Question** | Can the **ML pricing model** supply structured context for Multi-Agent **recommend after [4]** when agents invoke tools **in-process** (including fleet data from Postgres-Haystack)? |
| **Primary sources** | [`docs/dynamic-pricing-masterplan.md`](../docs/dynamic-pricing-masterplan.md) · [`docs/dynamic-pricing-execution-plan.md`](../docs/dynamic-pricing-execution-plan.md) · [`openspec/specs/dynamic-pricing/`](../openspec/specs/dynamic-pricing/) · `ml-experiments/` · `app/services/pricing_client.py` |
| **Related studies** | [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) §4.1 [7] · [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) · [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) |

> **Normative product rules** for pricing remain in OpenSpec dynamic-pricing. This study maps pricing into the **in-process multi-agent tool** path (no separate tool server).

---

## 1. Executive summary

| Question | Result |
|----------|--------|
| ML pricing as **in-process agent tool** (`predict_asset_price`)? | **GO** |
| Tool returns **`price_per_day` (+ clamp metadata)**; app computes **total**? | **GO** |
| Pricing is **public Spring-facing HTTP**? | **NO** — internal only |
| Masterplan “in-process function call”? | **Aligns** — agents call same path as `pricing_client` / `predict_price` |
| Feature vector from fleet + booking data? | **Almost** — assets from Postgres-Haystack; live util needs Phase 1e |
| Neo4j / project KG as model features? | **No** without retrain — use for agent rank/explain only |
| Fallback when model missing? | **GO** — category table (as-built) |

**Overall:** **GO.** Price via **in-process** tool after fleet candidates exist; synthesis merges prices into the recommendation.

---

## 2. Baseline

| Source | Role |
|--------|------|
| `ml-experiments/predict_price.py` | Experimental `predict_price()` + category guardrails |
| `app/services/pricing_client.py` | App import site → ml-experiments or fallback |
| `app/pipelines/predict_price_adapter.py` | Prices each candidate on service recommend path |

### Feature set (model inputs)

| Feature | Source in multi-agent world |
|---------|----------------------------|
| `category`, `condition`, `capacity`, `platform_height` | Postgres-Haystack Asset row |
| `duration_days` | Request rental window |
| `distance_km` | Site vs yard (default/proxy today) |
| `period_utilization`, `lead_time_days` | Bookings on mirror (Phase 1e) |

**Target:** `price_per_day`; total = rate × days. Guardrails: category stand-in now → per-asset min/max in Phase 2a.

---

## 3. Role after step [4]

```text
[4] Coordinator gate (indexing succeeds; non-agent)
[5] project / needs Worker (in-process tools)
    Delegator → fan-out per need_id
[6] fleet Workers ×N → Postgres-Haystack (+ Neo4j context)
[7] pricing Workers ×N → predict_asset_price (in-process tool)
[8] Coordinator synthesis → assets + prices
```

| Layer | Pricing responsibility |
|-------|------------------------|
| **Coordinator** (Orchestrator policy) | When recommend may price; rank; totals; rationale at **[8]** |
| **Delegator** | Routes pricing **Workers** per `need_id` after fleet candidates exist |
| **Pricing Worker [7]** | Invokes allowlisted tool only; no invent rates |
| **`predict_asset_price` tool** | Model + clamp; return daily rate + metadata |
| **Postgres-Haystack** | Asset attributes + booking util |
| **Neo4j / project KG** | Agent context only, not untrained XGBoost features |

### Tool contract (illustrative)

```text
predict_asset_price(
  category, condition, duration_days, capacity, distance_km,
  platform_height | null,
  period_utilization | null, lead_time_days = 0,
  asset_id | null
) -> { daily_rate, total_price?, currency, was_clamped, model_version, explanation }
```

---

## 4. Packaging

| Mode | Recommendation |
|------|----------------|
| **In-process in app** (as-built / target) | **Primary** — `pricing_client` → model |
| Separate pricing microservice | Optional later scale-out only |

No separate tool-server process is required for multi-agent pricing.

---

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Missing model.pkl | Category fallback; surface `model_version` |
| Silent zero prices | Forbidden |
| Feature mismatch | Shared `feature_schema` |
| Distance default 15 km | Later: project/site tools |

---

## 6. Phasing

| Phase | Work | Status |
|-------|------|--------|
| P1 | Keep as-built `pricing_client` on service path | **As-built** |
| P2 | Phase 1e live utilization | **As-built** |
| P3 | Phase 2a `app/services/pricing/` + per-asset clamp | **As-built** (+ 2b pipeline wire, 2c quote API) |
| P4 | Wire `predict_asset_price` as multi-agent tool (in-process) | **As-built S6** — `app/agents/tools.py` → `pricing_client` |
| P5 | Recommend graph: pricing **Workers [7]×N** + Coordinator **[8]** when `include_pricing` | **As-built S7.3–S7.5** (graph + stub merge + Call 2 flag) |

### As-built tool (P4 / S6)

```text
predict_asset_price(...) → pricing_client.predict_price_for_asset(...)
                         → app.services.pricing.model.predict_price(...)
```

Returns `{ daily_rate, total_price, currency, deposit_rate, was_clamped, model_version, explanation }` (+ optional `asset_id` echo). Silent zeros raise `ValueError`. Tests: `tests/test_predict_asset_price_tool.py`. Archive: `openspec/changes/archive/2026-08-12-s6-predict-asset-price-tool/`.

---

## 7. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial (with FastMCP packaging options) |
| **1.1.0** | 2026-08-10 | **Remove FastMCP**; in-process multi-agent tool only |
| **1.2.0** | 2026-08-11 | C/W/D roles: pricing Worker fan-out per need; Coordinator synthesis |
| **1.2.1** | 2026-08-12 | Feasibility README pin (pre-S6 tool) |
| **1.2.4** | 2026-08-12 | **S7.5 as-built**: Call 2 graph enrich behind `RECOMMEND_VIA_AGENT_GRAPH` |
| **1.2.3** | 2026-08-12 | **S7.3/S7.4 as-built**: pricing Workers [7]×N + stub [8]; P5 graph path live; HTTP still S7.5 |
| **1.2.2** | 2026-08-12 | **S6 as-built**: `predict_asset_price` tool; P1–P4 marked done; P5 remains Phase 7 |

---

## 8. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| ML pricing as agent tool? | **Yes (GO)** in-process |
| Multi-agent role | **Pricing Worker [7]** fan-out per need; tool executes model |
| Public price HTTP API? | **No** |
| Target variable | **`price_per_day`** |
| Feature sources | **Postgres-Haystack** + request window |
| Neo4j / project KG | Agent context only |
| Packaging | **In-app** `pricing_client` / predict_price |
