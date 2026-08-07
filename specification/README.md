# Specification reading order

This folder is the SDD source of truth for `haystack-fast-api`.  
**Start here**, then follow a path. Do not treat all SPECs as equally “live.”

---

## Runtime flow (as-built)

```text
Portal
  │  user_id (required) + project_text | file
  ▼
POST /api/v1/recommendations/from-project-spec
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ 5 · INDEXING  (SPEC-indexing-file-type-router)              │
│  FileTypeRouter → convert → dual clean/split                │
│       text_splitter ──┐                                     │
│       csv_splitter  ──┴→ final_doc_joiner                     │
│                            │                                │
│              ┌─────────────┴─────────────┐                  │
│              ▼                           ▼                  │
│       doc_embedder → writer      6 · KNOWLEDGE GRAPH        │
│       InMemoryDocumentStore      (SPEC-knowledge-graph)     │
│                                  mandatory after joiner     │
│                                  transforms only on         │
│                                  KnowledgeGraphGenerator    │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
IngestFromProjectSpecResponse
  (ingest_id, user_*, data_kind, documents_written, kg_*)

        ─ ─ ─ ─ deferred (not default HTTP) ─ ─ ─ ─
Recommend FR-010 (service) → pricing  → results_by_need
```

---

## Path A — Onboard (always)

| Step | Document | Role |
|------|----------|------|
| **0** | [This file](./README.md) | Map & flow |
| **1** | [`00-overview.md`](./00-overview.md) | Vision, as-built vs target |
| **2** | [`01-domain.md`](./01-domain.md) | Ubiquitous language |
| **3** | [`SPEC-project.md`](./SPEC-project.md) | Repo identity |
| **4** | [`SPEC-project-setup.md`](./SPEC-project-setup.md) | Stack, uv, Postgres, layering, env |

---

## Path B — Live project-spec pipeline ★ primary

| Step | Document | Runtime step |
|------|----------|--------------|
| **5** | [`SPEC-indexing-file-type-router.md`](./SPEC-indexing-file-type-router.md) | Live HTTP: index dual-branch → DocumentStore; **`user_id` required** |
| **6** | [`SPEC-knowledge-graph.md`](./SPEC-knowledge-graph.md) | After `final_doc_joiner`: **mandatory** user-scoped KG (hard-fail); Ragas transforms **only** on generator |
| **7** | [`.env.example`](../.env.example) | `INDEXING_*`, `KG_*` |
| **8** | [`../postman/README.md`](../postman/README.md) | Manual live HTTP (include `user_id`) |

**Tasks:** [`tasks-indexing-file-type-router.md`](./tasks-indexing-file-type-router.md) · [`tasks-knowledge-graph.md`](./tasks-knowledge-graph.md)

---

## Path C — Deferred recommend (service / reattach)

Read only when working on FR-010 rank/price or reattaching recommend HTTP.

| Step | Document | Status |
|------|----------|--------|
| **9** | [`SPEC-recommendation-intake.md`](./SPEC-recommendation-intake.md) | Deferred `results_by_need` envelope; live identity on index SPEC |
| **10** | [`SPEC-recommendation-pipeline.md`](./SPEC-recommendation-pipeline.md) | FR-010.1–8 **service-level** |
| **11** | [`SPEC-dynamic-pricing.md`](./SPEC-dynamic-pricing.md) | `predict_price` for recommend |
| **12** | [`SPEC-recommendation-intake-and-pipeline-front.md`](./SPEC-recommendation-intake-and-pipeline-front.md) | **Historical** HR-65 |

---

## Path D — Parent product + verification

| Step | Document | Role |
|------|----------|------|
| **13** | [`SPEC-agentic-equipment-recommendation-and-pricing.md`](./SPEC-agentic-equipment-recommendation-and-pricing.md) | Full product SDD; §11 KG vision |
| **14** | [`SPEC-recommendation-pipeline-testing-guide.md`](./SPEC-recommendation-pipeline-testing-guide.md) | Pytest / curl (live = ingest + `user_id`) |
| **15** | [`SPEC-recommendation-postman-testing-guide.md`](./SPEC-recommendation-postman-testing-guide.md) | **Deferred** recommend Postman |

---

## Conflict rules (short)

| Concern | Wins |
|---------|------|
| Live `POST .../from-project-spec` fields & index graph | **Indexing SPEC** |
| Mandatory KG after joiner / transforms location | **Knowledge-graph SPEC** |
| FR-010 components / seed fleet | **Recommendation-pipeline SPEC** (service) |
| Deferred recommend JSON envelope | **Recommendation-intake SPEC** (labeled deferred) |

---

## Suggested first read (new engineer)

1. This README (flow)  
2. `00-overview` (as-built blurb)  
3. `SPEC-indexing-file-type-router` (live API)  
4. `SPEC-knowledge-graph` (mandatory KG)  
5. `.env.example` + `postman/README`  

Then domain / project-setup / parent as needed.
