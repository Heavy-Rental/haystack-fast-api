# Feasibility Study: Recommender Matching Quality and Named Entity Recognition

| Field | Value |
|-------|--------|
| **Document type** | Architecture / matching-quality feasibility study |
| **Status** | Complete (study only — **not** as-built; no NER on the recommend path today) |
| **Date** | 2026-08-30 |
| **Version** | 1.0.0 |
| **Application** | `haystack-fast-api` Call 2 recommend (FR-010 service MVP + optional S7 C/W/D graph) |
| **Questions** | (1) Is the recommender done properly? (2) Is NER implemented for recommend? (3) Can domain NER be set up without breaking FR-010 / no-invent rules? |
| **As-built code** | `app/services/recommendations.py` · `app/services/session_recommend.py` · `app/services/need_decomposer.py` · `app/services/llm_need_decomposer.py` · `app/pipelines/catalog.py` · `app/pipelines/asset_candidate_filter.py` · `app/pipelines/rank_rationale_generator.py` · `app/agents/recommend_graph.py` · `app/agents/recommend_nodes.py` · `app/pipelines/kg/generator.py` |
| **OpenSpec** | [`../openspec/specs/recommendation-pipeline/spec.md`](../openspec/specs/recommendation-pipeline/spec.md) · [`../openspec/specs/equipment-recommendation/spec.md`](../openspec/specs/equipment-recommendation/spec.md) · [`../openspec/specs/knowledge-graph/spec.md`](../openspec/specs/knowledge-graph/spec.md) |
| **Related studies** | [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) · [`multi-agent-synthesis-recommend-output.md`](./multi-agent-synthesis-recommend-output.md) · [`implementation-plan.md`](./implementation-plan.md) |

> **Normative product rules** remain in OpenSpec. This study records an as-built matching audit and a **GO-with-constraints** design for domain entity extraction. It is **not** runtime source of truth.

---

## 1. Executive summary

| Question | Result |
|----------|--------|
| Is Call 2 recommend **spec-correct as an MVP** (FR-010)? | **Yes** — resolve → decompose → expand → filter → availability → `predict_price` → rank one item; no invented `asset_id` / rates |
| Is it a **learned / semantic recommender**? | **No** — keyword catalog match + 4-term heuristic rank |
| Is **named entity recognition** used to pick assets? | **No** |
| Do KG-1 / vector hits change `asset_id`? | **No** — Worker [5] notes only (`research_notes` / `graph_notes`) |
| Can domain NER / entity extraction be added? | **GO with constraints** |
| Generic spaCy / `dslim/bert-base-NER` (PER/ORG/LOC)? | **NO** for matching — wrong label set |
| Enable `KG_APPLY_TRANSFORMS` as a substitute for recommend NER? | **NO** — Q&A enrichment only; default off; does not change quote `items[]` |

**Overall:** the recommend path is a **well-engineered MVP** (pipeline, tests, no-invent, live SQL option). Matching quality is still a **constrained keyword matcher**. NER is **feasible** if it is **domain-labeled**, env-gated, and wired into **decompose → fleet filter / rank** — not dropped in as CoNLL tags or Ragas transforms.

---

## 2. As-built recommend matching

### 2.1 Two Call 2 implementations, one quote DTO

| Path | Flag | Behaviour |
|------|------|-----------|
| **MVP service** `RecommendationService` | Default (`RECOMMEND_VIA_AGENT_GRAPH=false`) | Haystack intake FR-010.1–3 then per-unit 4–8 |
| **LangGraph C/W/D** `run_recommend_graph` | Opt-in (`RECOMMEND_VIA_AGENT_GRAPH=true`) | Gate → Worker [5] → Delegator → fleet [6] / price [7] → Coordinator [8]; **same** quote DTO; traces off HTTP body |

Both paths end in `SessionRecommendService.map_recommend_to_quote`. Synthesis **must not** invent `asset_id` or rates.

```text
project text / session chunks
        │
        ▼
  decompose needs          ← stub keywords (default) or LLM JSON (NEED_DECOMPOSER=llm)
        │
        ▼
  expand quantity          ← need_N + quantity 2 → need_N__u1, need_N__u2
        │
        ▼
  filter catalog           ← four approved types only (FR-011)
        │
        ▼
  booking overlap          ← dates missing → all pass
        │
        ▼
  predict_price()          ← production model + clamp; no silent zeros
        │
        ▼
  rank exactly one item    ← heuristic match_score; else item: null + warning
```

### 2.2 Need extraction (not NER)

`NeedDecomposer` protocol → `StubNeedDecomposer` (CI default) or `LlmNeedDecomposer`.

- **Stub / LLM-empty fallback:** `split_needs_from_text` + `_KEYWORD_TO_MODEL` in `app/pipelines/catalog.py`. One need per approved type mentioned. Quantity is a nearby-number window (`two`/`2` … `five`/`5`).
- **LLM mode:** OpenAI-compatible chat completions; JSON array of `{need_id, description, equipment_hints, quantity}`; hints restricted to four slugs; timeout twice then keyword fallback (**FR-P-014**).

`DecomposedNeed` fields today: `need_id`, `description`, `equipment_hints`, `quantity`. No capacity / height / terrain / location constraints.

### 2.3 Keyword table (collision surface)

From `app/pipelines/catalog.py`:

| Keyword | Model category |
|---------|----------------|
| boom lift, boom, aerial | boom lift |
| scissors lift, scissor lift, scissors, scissor, elevated, **platform** | scissor lift |
| fork lift, forklift, **fork**, **warehouse**, loading | forklift |
| excavator, excavate, **trench** | excavator |

Substring `find` / `in` matching. False positives (e.g. “loading dock” → forklift, “platform” in unrelated text → scissor lift) are expected.

Approved display types only: Boom Lift, Scissors Lift, Fork Lift, Excavator.

### 2.4 Rank (as-built vs parent target)

`score_need_match` (`app/pipelines/rank_rationale_generator.py`):

| Signal | Weight |
|--------|--------|
| Category hit | 0.50 |
| Platform height ≥ need (`~N m` regex on description) | 0.20 |
| Available | 0.15 |
| Priced (`daily_rate > 0`) | 0.15 |

Tie-break: condition (EXCELLENT > … > NEEDS_REPAIR), then capacity. Rationale is a template one-liner from the same signals (`build_evidence_rationale`). Parent **target** ranking (Haystack `PromptBuilder` + Generator / Bedrock) is **not** as-built. Hybrid BM25 + dense retrieval over fleet is **not** as-built.

`filter_fleet_candidates` already accepts `min_platform_height` and `unit_need.constraints` (`platform_height_m` / `min_platform_height`). Nothing on the live path populates `constraints`.

### 2.5 What already looks like extraction (but is not NER)

| Extractor | Where | Recommend effect |
|-----------|--------|------------------|
| Rental dates | `project_spec_dates.py` (Call 1; request overrides text) | Availability window |
| Budget | `project_spec_budget.py` (Call 1; never invent) | Display only — not a rank feature |
| Height regex | `_HEIGHT_M` in ranker | +0.20 match_score if asset height ≥ parsed metres |
| Keyword type | catalog table | **The** candidate filter |

### 2.6 KG / vector on the recommend graph (S7.8)

Worker [5] calls `project_vector_search` then `project_kg_query` **before** `decompose_project_needs`. Hits become `research_notes` / `graph_notes` (and optional `research_hits` / `graph_hits`). **Decompose still runs on source text.** Fleet filter does not read those notes.

Default KG-1 (`KG_APPLY_TRANSFORMS=false`): **document nodes only**, empty `relationships`. Sample artifacts under `artifacts/kg/` confirm `"type": "document"`.

Neo4j KG-2 (`neo4j_cypher_read` asset-neighbors) runs **after** candidates exist. Context for notes, not for picking the category.

Parent spec: KG **does not** replace Asset SQL / availability / `predict_price`. This study agrees.

### 2.7 Eval snapshot (limits)

Committed pack [`../docs/eval/call1-call2-eval-results.md`](../docs/eval/call1-call2-eval-results.md): 12 cases, mean need F1 ~0.97, Hit@1 1.0. Runtime uses `NEED_DECOMPOSER=stub`, `FLEET_BACKEND=fake`, `RECOMMEND_VIA_AGENT_GRAPH=false`, and **injected gold needs** (`_FixedDecomposer`). It proves pipeline + quote mapping, **not** live LLM extract or NER.

---

## 3. Is the recommender “done properly”?

### 3.1 Yes as MVP / FR-010

- One ranked `item` per unit-need or `null` + warning (Scenario C).
- Four-type hard filter; no invented catalog ids or rates.
- Availability via booking overlap; live SQL when `FLEET_BACKEND=sql` (no silent seed fallback).
- Production `predict_price()` + clamp; quote hydration (`equipment.id` = `assets.id` on live SQL).
- Quantity expand then Call 2 collapse (**FR-P-013**).
- Evidence `matchScore` / `confidenceScore`; allowlisted tools; F-2 partition writes on the graph path.
- Strong pytest coverage for the sockets that exist.

### 3.2 No as a full recommender

| Gap | As-built | Product / industry “proper” |
|-----|----------|-----------------------------|
| Need understanding | Keywords or LLM JSON slugs | Structured entities (type, qty, capacity, height, site) |
| Candidate generation | Category equality | Constraints + optional retrieval / KG-2 |
| Ranking | 4-term heuristic + template rationale | Learned rank or LLM rationale with schema-gap callouts (parent AC 6) |
| User / history | None | Not in MVP scope (constitution) |
| Catalog breadth | Four SG types | Same product cap — not a defect |
| Agent graph | Default **off** | Target production-default graph |
| KG-1 in matching | Notes only | Multi-hop was a **target**, explicitly not a substitute for SQL filter |

**Verdict:** **GO to keep the MVP.** Matching quality work is a **follow-on** (this study), not a rewrite of FR-010.

---

## 4. Named entity recognition — as-built

**None on the recommend path.**

| Mechanism | In repo? | Used to pick `asset_id`? |
|-----------|----------|--------------------------|
| Haystack `NamedEntityExtractor` / `TransformersNamedEntityExtractor` / `SpacyNamedEntityExtractor` | **No** | — |
| spaCy / GLiNER / Stanza / Flair / token-classifier training data | **No** | — |
| Keyword table + LLM JSON decomposer | Yes | **Yes** (type + quantity only) |
| Ragas `NERExtractor` inside `default_transforms` | Indirect, optional | **No** |

Ragas full transforms (`KnowledgeGraphGenerator` when `KG_APPLY_TRANSFORMS=true`) **can** include LLM `NERExtractor` + NER overlap edges (Ragas testset default pipeline). Constraints:

1. Default is **off** (document nodes).
2. Intended for **KG-1 Q&A (Call 3)**, not Call 2 ranking.
3. Current call is `default_transforms()` with **no** documents / LLM / embedding args — not a production NER pipeline.
4. Transform failures are **warnings**, not hard-fail (unlike KG document-node build).

Haystack 2.x still ships `NamedEntityExtractor` but it is **deprecated toward 3.0** (moved to `transformers-haystack` / `spacy-haystack`). A custom `@component` is the durable option in this repo.

---

## 5. Can NER be set up? — GO with constraints

### 5.1 Domain labels (not CoNLL)

Generic PER/ORG/LOC/MISC will not tag “scissors lift” or “20-ton”. Recommend NER means **domain information extraction**:

| Label | Example | Fleet / rank use |
|-------|---------|------------------|
| `EQUIPMENT_TYPE` | scissors lift, 20-ton excavator | Map to four catalog slugs → `equipment_hints` |
| `QUANTITY` | two boom lifts | Existing expand path |
| `CAPACITY` | 20-ton, 3 tonne | Filter vs `assets.capacity` (new constraint) |
| `PLATFORM_HEIGHT` | 10 m working height | Already scored; populate `constraints.platform_height_m` |
| `TERRAIN` / site | soft clay | **Rationale only** until a fleet column exists (known schema gap) |
| `LOCATION` | Jurong, warehouse | Weak; must **not** let “warehouse” force forklift if type is boom |
| `DATE` / `BUDGET` | already extracted | Leave regex extractors; do not duplicate |

### 5.2 Insertion points

```text
Call 1 ingest                 Call 2 recommend
project text/file  →  [NER] → decompose  →  filter fleet  →  availability  →  price  →  rank
                         ▲                    ▲
                    hints + constraints   use constraints
                         │
                    KG-1 NER (optional) ── Call 3 Q&A only
```

1. **Intake / Worker [5] (highest value).** After `SourceTextResolver` (or inside `NeedDecomposer`). Entities → `equipment_hints` + optional `constraints` on `DecomposedNeed`.
2. **Fleet filter / rank (required for quote impact).** Feed constraints into `AssetCandidateFilter` / `filter_fleet_candidates` (hooks exist). Rank already uses height.
3. **KG-1 (out of scope for matching).** Do **not** treat `KG_APPLY_TRANSFORMS=true` as recommend NER.

If entities land only on KG nodes, **recommendations will not change**.

### 5.3 Backend options

| Approach | Fit | Ops | Decision |
|----------|-----|-----|----------|
| spaCy `en_core_web_sm` | Generic NER | Model download | **Reject** for matching |
| HF `dslim/bert-base-NER` | Same generic labels | Model load | **Reject** unless later fine-tuned on rental specs |
| **GLiNER** (zero-shot label list) | Custom labels without training | Local model; Haystack `warm_up()` | **Preferred NER backend** |
| **Extend `LlmNeedDecomposer` JSON** | Same DigitalOcean / OpenAI-compatible path | Latency; FR-P-014 fallback already exists | **Fastest ship**; IE, not token-level NER |
| Ragas `NERExtractor` | KG-1 | LLM cost; default off | **Call 3 later only** |
| Fine-tuned token classifier | Best long-term accuracy | Training set + promotion | **Later**; not required to start |

**Packaging (hard rules from folder-wide principles):**

- In-process Haystack `@component` + existing decomposer protocol. **No** MCP / extra microservice.
- Env-gated: `NER_BACKEND=off|gliner|llm` (name illustrative). Default **`off`** so CI stays stub.
- Load once in app lifespan (`warm_up`), same as LLM decomposer.
- Timeout / missing model → **keyword fallback** (FR-P-014 pattern). Never fail closed into invented types.
- Map extracted types through the **same four-slug catalog**. Unmapped labels → ignore (no invent).
- Tools stay allowlisted; if exposed as a tool, name it (e.g. `extract_project_entities`) and add to Worker [5] allowlist — do not free-form SQL/Cypher.

Haystack custom component (GLiNER) is the documented extension path when the stock extractor’s label set is wrong ([Haystack discussion #8198](https://github.com/deepset-ai/haystack/discussions/8198)).

### 5.4 Schema / filter changes (when implemented)

- Extend `DecomposedNeed` / unit-need dicts with optional `constraints` (`platform_height_m`, `capacity_min`, …). Omit from public Call 1 lean body unless a later OpenSpec change says otherwise (`needs_summary[]` can stay hints + quantity).
- Do not invent fleet columns (terrain / operator-required remain schema-gap callouts in rationale).
- Quote DTO unchanged: still one `item` per unit-need, same `equipment.id` rules.

### 5.5 Tests (minimum pack if a stage ships)

| Case | Expect |
|------|--------|
| Scissors + “10 m” | Hint scissor lift; height constraint; aerial with `platform_height >= 10` preferred |
| Excavator + “20-ton” | Hint excavator; capacity constraint vs fleet |
| Quantity “two boom lifts” | Expand two unit-needs (existing expand) |
| No-match helicopter / submarine | Empty candidates; `item: null` (Scenario C) |
| Collision: “warehouse” + explicit boom | Boom, **not** forklift |
| `NER_BACKEND=off` | Identical stub behaviour; default pytest green without model download |

Eval pack must **not** silently inject gold needs when claiming NER quality.

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Generic NER looks “on” but matches worse | Domain labels only; reject PER/ORG/LOC as matching features |
| KG transforms mistaken for recommend NER | Spec + this study: transforms ≠ `asset_id` |
| LLM invents types outside catalog | Allowlist slugs; drop unknown; keyword fallback |
| Model download breaks CI | Default `off`; optional marker / extra dep group |
| Haystack stock extractor removed in 3.0 | Custom `@component`, not `NamedEntityExtractor` |
| Terrain extracted with no fleet field | Rationale / warning only |
| Latency on Call 2 | Lifespan warm_up; Worker [5] already sequential; keep timeout fallback |
| Dual decomposer + NER disagreement | Single owner: NER feeds decomposer (or NER *is* the decomposer JSON schema) |

---

## 7. Phasing (proposed; not started)

| Phase | Work | Status |
|-------|------|--------|
| **N0** | This study + OpenSpec change when code is scheduled | **This document** |
| **N1** | Domain label list + catalog map + `constraints` on need DTO (no model) | **Not started** |
| **N2** | Wire constraints into `filter_fleet_candidates` / rank (height already partial) | **Not started** |
| **N3** | `NER_BACKEND=llm` — extend need JSON schema (fastest) **or** GLiNER component | **Not started** |
| **N4** | Optional: Worker [5] allowlisted `extract_project_entities` tool; traces `role=worker` | **Not started** |
| **N5** | Optional: Ragas NER for KG-1 Q&A only; fix `default_transforms(...)` args; keep default off | **Not started** |
| **N6** | Optional later: fine-tune token classifier; eval pack without gold-need inject | **Not started** |

Suggested implementation-plan stage if scheduled: **S7.9** (app; depends on S7.1 decomposer / filter sockets; default CI `NER_BACKEND=off`).

---

## 8. Non-goals

- Replacing FR-010 SQL filter / availability / `predict_price` with a knowledge graph.
- Collaborative filtering / user history.
- Expanding the four-type catalog.
- Making `KG_APPLY_TRANSFORMS=true` the recommend default.
- Public HTTP NER API.
- Training data collection in this study.

---

## 9. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-30 | Initial: MVP matching audit; NER absent on recommend path; domain NER **GO with constraints** |

---

## 10. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Is recommend “done properly”? | **Yes as FR-010 MVP; no as semantic/NER matcher** |
| NER today? | **No** (keywords + optional LLM JSON; KG document nodes) |
| Add NER? | **GO** — domain labels, env-gated, in-process |
| Generic spaCy / BERT-NER? | **No** for matching |
| Preferred first backend | **Extend LLM need JSON** (ship) or **GLiNER** (true NER) |
| Must change `asset_id`? | Wire into **decompose + filter/rank**; not KG-only |
| `KG_APPLY_TRANSFORMS`? | Stay **off** for recommend; optional later for Call 3 |
| CI default | **`off` / stub** — keyword fallback |
| Invent types / assets / rates? | **Forbidden** |
| Haystack stock `NamedEntityExtractor`? | **Avoid** (deprecated toward 3.0); custom `@component` |
| Agent packaging | In-process tool only; allowlist if exposed to Worker [5] |
