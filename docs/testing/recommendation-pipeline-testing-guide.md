# Testing Guide: Recommendation Pipeline (FR-010 MVP)

| Field | Value |
|-------|--------|
| **Document type** | SDD verification / testing guide (not behaviour SoT) |
| **Status** | Split (2026-08-07): FR-010 **service** tests still as-built; **HTTP** section points to indexing ingest |
| **Feature id** | `recommendation-pipeline-testing` |
| **Spec location** | `docs/testing/recommendation-pipeline-testing-guide.md` |
| **Normative behaviour (service)** | [`openspec/specs/recommendation-pipeline/spec.md`](../../openspec/specs/recommendation-pipeline/spec.md) |
| **Normative behaviour (live HTTP)** | [`openspec/specs/indexing/spec.md`](../../openspec/specs/indexing/spec.md) |
| **Parent** | [`openspec/specs/equipment-recommendation/spec.md`](../../openspec/specs/equipment-recommendation/spec.md) |
| **Live Postman** | [`../../postman/README.md`](../../postman/README.md) |
| **Deferred recommend Postman** | [`recommendation-postman-testing-guide.md`](./recommendation-postman-testing-guide.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD |
| **Audience** | Engineers verifying recommend service + live ingest HTTP |

This guide is the **how to test** companion. **Live HTTP** expects `ingest_id` / indexing fields, **not** `recommendation_id` / `results_by_need`. Service-level recommend tests still use `RecommendationService` directly.

---

## 0. Prerequisites

Work from the application module (where `pyproject.toml` and `app/` live):

```bash
cd haystack-fast-api
uv sync --all-groups
```

| Note | Detail |
|------|--------|
| Auth | Not required on recommend routes |
| Postgres | Not required for seed-fleet happy path; `/health` may show `degraded` if DB is down |
| Default decomposer | `NEED_DECOMPOSER=stub` (no LLM key) |
| Pricing model | Optional `ml-experiments/artifacts/model.pkl`; fallback pricing still works |
| Async offload | Live route offloads `IndexingIngestService` via `run_in_threadpool` |
| Pricing fields | On **service-level** recommend path: `daily_rate` + `total_price`; no fabricated `weekly_rate`. Not on live HTTP ingest response. |
| Pytest prereqs | **None optional** — default suite has no markers / skip-if-service patterns; `tests/conftest.py` forces `INDEXING_EMBEDDER=mock`, `INDEXING_EMBEDDING_DIM=384`, `PROJECT_AGENT_MODE=stub` so host `.env` does not break CI |
| Embed dim | Query embedder for vector tools must match document store dim (see knowledge-graph testing guide) |

### Live HTTP vs service recommend

| Layer | How to test | Expect |
|-------|-------------|--------|
| **HTTP** `POST .../submitprojectspecification` | `tests/test_recommendations_intake.py`, `postman/` | `ingest_id`, `data_kind`, `documents_written`, `has_embedding`, `kg_*` |
| **HTTP** multi-agent Q&A `POST .../project-knowledge/getassetrecommendations` | [`knowledge-graph-testing-guide.md`](./knowledge-graph-testing-guide.md); `tests/test_project_knowledge_*.py`; Postman folder **04** | `answer`, dual `sources_used` / `tool_traces` |
| **Service** FR-010 | `tests/test_recommend_pipeline_mvp.py`, `tests/test_pipeline_intake_front.py` | `recommendation_id`, `results_by_need`, singular `item` |

---

## 1. Automated tests (pytest)

```bash
cd haystack-fast-api

# Intake front — FR-010.1–3 (resolve → decompose → expand)
uv run pytest tests/test_pipeline_intake_front.py -v

# Pipeline MVP — FR-010.4–8 + e2e (asset, availability, price, rank, assemble)
uv run pytest tests/test_recommend_pipeline_mvp.py -v

# HTTP API
uv run pytest tests/test_recommendations_intake.py -v

# LLM decomposer (mocked HTTP; no DigitalOcean required)
uv run pytest tests/test_llm_need_decomposer.py -v

# Knowledge graph assembly + Stage-1 multi-agent (see knowledge-graph-testing-guide.md)
uv run pytest tests/test_knowledge_graph.py tests/test_project_knowledge_*.py -v

# Full suite (no optional -m filter; no live LLM / Neo4j / Pgvector required)
uv run pytest tests/ -v
```

### What each suite covers

| Test file | Proves |
|-----------|--------|
| `tests/test_pipeline_intake_front.py` | Source text resolve, quantity expansion, stub decompose, intake_front graph |
| `tests/test_recommend_pipeline_mvp.py` | Seed asset match, booking overlap, pricing payload, top-1 rank, e2e scissors item, qty=2, Scenario C no-match |
| `tests/test_recommendations_intake.py` | Public POST JSON/multipart **ingest** (indexing), 400 validation |
| `tests/test_llm_need_decomposer.py` | JSON parse, mocked chat completions, factory stub/llm |
| `tests/test_knowledge_graph.py` + `tests/test_project_knowledge_*.py` | Mandatory KG-1 + multi-agent Q&A — **normative steps in** [`knowledge-graph-testing-guide.md`](./knowledge-graph-testing-guide.md) |
| `tests/conftest.py` | Autouse isolation: mock embedder dim 384, stub agents, temp KG dir |

**Expect:** all tests pass under conftest isolation (host `INDEXING_*` overrides do not apply).

---

## 2. Start the server

```bash
cd haystack-fast-api
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

| Resource | URL |
|----------|-----|
| Base | `http://localhost:8000` |
| Health | `GET http://localhost:8000/health` |
| OpenAPI / Swagger | `http://localhost:8000/docs` |
| Project-spec (live **ingest**) | `POST http://localhost:8000/internal/v1/recommendations/submitprojectspecification` |

---

## 3. Happy path — free-text (curl) — **live indexing**

```bash
curl -s -X POST http://localhost:8000/internal/v1/recommendations/submitprojectspecification \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user_demo",
    "user_name": "Demo User",
    "project_text": "Indoor elevated work ~8m for scissors lift",
    "start_date": "2026-09-01",
    "end_date": "2026-09-12",
    "options": { "include_pricing": true }
  }' | python -m json.tool
```

### Expected result (live HTTP)

| Check | Expect |
|-------|--------|
| HTTP status | **200** |
| `user_id` | Echo `user_demo` |
| `ingest_id` | Starts with `ing_` |
| `data_kind` | `"unstructured"` |
| `documents_written` | ≥ 1 |
| `chunk_count` | ≥ 1 |
| `documents[0].has_embedding` | `true` |
| `kg_built` | `true` on successful ingest (KG is mandatory) |
| Response shape | **No** `recommendation_id` / `results_by_need` |

> **Service-level recommend** (not default HTTP): call `RecommendationService` in pytest — expect `rec_` / `results_by_need` / ranked `item` (see `test_recommend_pipeline_mvp.py`).

---

## 4. Happy path — Postman (**live indexing**)

Import [`../postman/README.md`](../postman/README.md) collection. Or:

| Field | Value |
|-------|--------|
| Method | **POST** |
| URL | `http://localhost:8000/internal/v1/recommendations/submitprojectspecification` |
| Headers | `Content-Type: application/json` |
| Body | **raw → JSON** (same body as §3) |
| Expect | `ingest_id`, `data_kind=unstructured`, `documents_written` ≥ 1 |

### Suggested collection

1. `GET Health`  
2. `POST Recommend scissors (JSON)` — §3  
3. `POST Recommend forklift (file)` — §5  
4. `POST Empty text (400)` — §6  
5. `POST Bad dates (400)` — §6  
6. `POST No match submarine (200, item null)` — §6  

Environment variable: `baseUrl` = `http://localhost:8000`  
Request URL: `{{baseUrl}}/internal/v1/recommendations/submitprojectspecification`

---

## 5. Happy path — Swagger UI

1. Open `http://localhost:8000/docs`
2. Expand **POST** `/internal/v1/recommendations/submitprojectspecification`
3. **Try it out** → paste JSON from §3 → **Execute**
4. Confirm response matches §3 expected result

---

## 6. File upload (multipart)

### Postman

**Body → form-data** (do **not** force JSON `Content-Type`):

| Key | Type | Value |
|-----|------|--------|
| `file` | **File** | `.txt` or `.md`, e.g. content: `Need one forklift for warehouse loading` |
| `start_date` | Text | `2026-09-01` (optional) |
| `end_date` | Text | `2026-09-12` (optional) |
| `project_text` | Text | optional extra text |
| `include_pricing` | Text | `true` (optional) |

### Expected

- Status **200**
- Forklift-related `item` when text matches catalog keywords
- PDF/DOCX → **400** (not in MVP)

---

## 7. Negative and edge cases

| Case | Request | Expect |
|------|---------|--------|
| Empty / whitespace text | `{"project_text": "   "}` | **400** `{"error":"bad_request","message":"..."}` |
| Missing body | `{}` | **400** |
| Invalid date window | `start_date` after `end_date` + non-empty text | **400** |
| Empty multipart | no `file`, no `project_text` | **400** |
| No catalog match | `"project_text": "Need a submarine for underwater work"` | **200**, `item: null`, non-empty `warnings` |
| Quantity 2 (injected decomposer / LLM) | see pytest or §8 | Two unit-need rows (`…__u1`, `…__u2`) when decomposer returns `quantity: 2` |

---

## 8. Optional — DigitalOcean Inference Router (LLM decompose)

Default CI path does **not** need this. Use only for manual multi-need / natural-language decompose tests.

### `.env` (never commit secrets)

```bash
NEED_DECOMPOSER=llm
LLM_BASE_URL=https://inference.do-ai.run/v1
LLM_API_KEY=dop_v1_...                 # your DigitalOcean token
LLM_MODEL=router:your-router-name      # exact Inference Router name
LLM_TIMEOUT_SECONDS=60
LLM_TEMPERATURE=0
```

See also [`.env.example`](../.env.example).

### Steps

1. Create/configure a DigitalOcean Inference Router and API token.  
2. Set env vars above.  
3. Restart uvicorn.  
4. POST free text that implies multiple equipment units, e.g.:

```json
{
  "project_text": "Need two scissors lifts for indoor 8m work and one excavator for trenching.",
  "start_date": "2026-09-01",
  "end_date": "2026-09-12"
}
```

5. If the model returns structured needs with quantities, expect multiple `results_by_need` rows and/or `__u1`/`__u2` ids; each matched row should still have singular `item` (or null if no fleet match).

### Reset for CI / default

```bash
NEED_DECOMPOSER=stub
```

---

## 9. What is in scope for this branch (pass criteria)

| Behaviour | Live now? |
|-----------|-----------|
| Free-text / `.txt` intake | Yes |
| Seed fleet match → full `item` (type, rank, rationale, pricing) | Yes |
| Pricing via ml-experiments or category fallback | Yes |
| Template rank + schema-gap rationale | Yes |
| Availability filter on seed bookings | Yes |
| Real Spring SQL Asset/Booking | No (seed only) |
| Multi-need from English without LLM | No (stub = one need from full text); pytest injects multi-need |
| PDF/DOCX | No |

---

## 10. Troubleshooting

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| `item` always null | Text has no catalog keywords | Use “scissors lift”, “forklift”, “excavator”, “boom lift” |
| **400** on valid JSON | Date order or empty text | Check `end_date >= start_date`; non-empty `project_text` |
| Pricing `fallback-category-table` | Missing `ml-experiments/artifacts/model.pkl` | OK for MVP; train/copy model for experimental path |
| LLM mode startup error | `NEED_DECOMPOSER=llm` without `LLM_API_KEY` | Set key or switch to `stub` |
| LLM returns empty → **400** | Model output not valid needs JSON | Check prompt/logs; try another model on the router |
| Import / pipeline errors | Wrong working directory | Run from `haystack-fast-api/` app root |

---

## 11. Related specs

| Spec | Role |
|------|------|
| [`openspec/specs/indexing/spec.md`](../../openspec/specs/indexing/spec.md) | **Live** HTTP ingest contract |
| [`openspec/specs/knowledge-graph/spec.md`](../../openspec/specs/knowledge-graph/spec.md) | KG assembly + Stage-1 multi-agent |
| [`knowledge-graph-testing-guide.md`](./knowledge-graph-testing-guide.md) | KG verification (pytest / curl / Postman) |
| [`../../postman/README.md`](../../postman/README.md) | Live Postman collection (ingest + folder 04 multi-agent) |
| [`openspec/specs/recommendation-pipeline/spec.md`](../../openspec/specs/recommendation-pipeline/spec.md) | Normative FR-010.1–8 **service** SDD |
| [`openspec/specs/recommendation-intake/spec.md`](../../openspec/specs/recommendation-intake/spec.md) | Request shapes + deferred recommend response |
| [`recommendation-postman-testing-guide.md`](./recommendation-postman-testing-guide.md) | Deferred recommend Postman |
| [`openspec/changes/archive/2026-08-07-hr-65-intake-front/`](../../openspec/changes/archive/2026-08-07-hr-65-intake-front/) | Historical HR-65 + LLM notes |
| [`openspec/specs/equipment-recommendation/spec.md`](../../openspec/specs/equipment-recommendation/spec.md) | Parent product SDD |
| [`openspec/AGENTS.md`](../../openspec/AGENTS.md) | Reading order & conflict rules |

---

## 12. Change control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-05 | Initial testing guide for recommendation pipeline MVP (pytest, curl, Postman, Swagger, negatives, DigitalOcean LLM, expectations) |
| **1.1.0** | 2026-08-07 | Spec reconcile: live HTTP = indexing |
| **1.2.0** | 2026-08-07 | Live curl requires `user_id`; kg_built note; sequential map |
| **1.3.0** | 2026-08-08 | Pointers to knowledge-graph multi-agent testing + Postman folder 04 |
| **1.4.0** | 2026-08-10 | Moved under `docs/testing/`; links to openspec (OpenSpec · Spec-kit · OpenSPDD) |
| **1.5.0** | 2026-08-12 | Document default pytest isolation (mock embedder + dim 384; no optional markers/prereqs) |

**Reading order:** [Map](../../openspec/AGENTS.md) · live contract [Indexing](../../openspec/specs/indexing/spec.md) · [Knowledge graph testing](./knowledge-graph-testing-guide.md) · [Postman live](../../postman/README.md)

When test commands or expected results change, update this guide and normative SPECs together.
