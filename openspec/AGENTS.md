# Agent & engineer guide — haystack-fast-api SDD

This folder is the **SDD source of truth**. Standards:

| Standard | Role |
|----------|------|
| **OpenSpec** | Capability behaviour in `specs/<cap>/spec.md` |
| **GitHub Spec-kit** | Constitution (`.specify/memory/constitution.md`), user stories, contracts, tasks, converge |
| **OpenSPDD** | REASONS Canvas in `design.md`; structured prompts; **fix prompt/spec first, then code** |

**Start here**, then follow a path. Do not treat all capabilities as equally “live.”

---

## Runtime flow (as-built)

```text
Portal / Spring
  │  user_id (required) + project_text | file
  ▼
POST /internal/v1/recommendations/submitprojectspecification
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ INDEXING  (specs/indexing)                                  │
│  FileTypeRouter → convert → dual clean/split                │
│       text_splitter ──┐                                     │
│       csv_splitter  ──┴→ final_doc_joiner                     │
│                            │                                │
│              ┌─────────────┴─────────────┐                  │
│              ▼                           ▼                  │
│       doc_embedder → writer      KNOWLEDGE GRAPH            │
│       InMemoryDocumentStore      (specs/knowledge-graph)    │
│                                  Part A: mandatory KG after │
│                                  joiner + JSON artifact     │
│                                  Part B: session registry   │
│                                  for multi-agent tools      │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
IngestFromProjectSpecResponse (lean public body — S1a + S1b)
  as-built: ingest_id, user_id, user_requirement_summary,
            tentative_start/end_date (echo request when supplied), warnings[]
  TARGET (FR-IX-023): + needs_summary, free-text date extract,
                      expected_budget (not ranked assets / ML rent)
  Technical documents[] / kg_* stay internal (session meta)

  │  optional Stage-1 Q&A (Call 2)
  ▼
POST /internal/v1/recommendations/project-knowledge/getassetrecommendations
  LangGraph: research → graph → synthesis
  tools: project_vector_search + project_kg_query
  prompts: app/agents/prompts.py (OpenSPDD)
  query required (free-form or predefined prompt + summary)

        ─ ─ ─ ─ deferred (not default HTTP) ─ ─ ─ ─
Call 3 Recommend FR-010 (service) → fleet + pricing → results_by_need
KG-2 equipment stockpile (Stage 2)
```

---

## Path A — Onboard (always)

| Step | Document | Role |
|------|----------|------|
| **0** | [This file](./AGENTS.md) | Map, conflict rules, workflow |
| **1** | [`project.md`](./project.md) | Vision, identity, as-built vs target |
| **2** | [`specs/domain/spec.md`](./specs/domain/spec.md) | Ubiquitous language & invariants |
| **3** | [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) | Immutable principles |
| **4** | [`specs/project-setup/spec.md`](./specs/project-setup/spec.md) | Stack, env, layering (behaviour) |
| **5** | [`specs/project-setup/design.md`](./specs/project-setup/design.md) | Layout, uv runbooks |

---

## Path B — Live project-spec pipeline ★ primary

| Step | Document | Runtime step |
|------|----------|--------------|
| **6** | [`specs/indexing/spec.md`](./specs/indexing/spec.md) | Live HTTP index dual-branch; **`user_id` required** |
| **7** | [`specs/indexing/contracts/ingest-from-project-spec.md`](./specs/indexing/contracts/ingest-from-project-spec.md) | Request/response field tables |
| **8** | [`specs/knowledge-graph/spec.md`](./specs/knowledge-graph/spec.md) | Mandatory KG + Stage-1 multi-agent |
| **9** | [`.env.example`](../.env.example) | `INDEXING_*`, `KG_*`, `PROJECT_AGENT_*` |
| **10** | [`../postman/README.md`](../postman/README.md) | Manual live HTTP |

**Design / prompts:** [`specs/indexing/design.md`](./specs/indexing/design.md) · [`specs/knowledge-graph/design.md`](./specs/knowledge-graph/design.md) · [`../app/agents/prompts.py`](../app/agents/prompts.py)

**Archived tasks:** [`changes/archive/`](./changes/archive/)

---

## Path C — Deferred recommend (service / reattach)

| Step | Document | Status |
|------|----------|--------|
| **11** | [`specs/recommendation-intake/spec.md`](./specs/recommendation-intake/spec.md) | Deferred `results_by_need` envelope |
| **12** | [`specs/recommendation-pipeline/spec.md`](./specs/recommendation-pipeline/spec.md) | FR-010.1–8 **service-level** |
| **13** | [`specs/dynamic-pricing/spec.md`](./specs/dynamic-pricing/spec.md) | `predict_price` for recommend |
| **13.5** | [`specs/domain-seed-data/spec.md`](./specs/domain-seed-data/spec.md) | Seed-data richness required for §13 to be verifiable — executed on the Spring Boot side, not this repo |

---

## Path D — Parent product + verification

| Step | Document | Role |
|------|----------|------|
| **14** | [`specs/equipment-recommendation/spec.md`](./specs/equipment-recommendation/spec.md) | Full product SDD |
| **15** | [`../docs/testing/recommendation-pipeline-testing-guide.md`](../docs/testing/recommendation-pipeline-testing-guide.md) | Pytest / curl (live = ingest + `user_id`) |
| **16** | [`../docs/testing/recommendation-postman-testing-guide.md`](../docs/testing/recommendation-postman-testing-guide.md) | **Deferred** recommend Postman |

---

## Conflict rules

| Concern | Wins |
|---------|------|
| Live `POST .../submitprojectspecification` fields & index graph | **`specs/indexing/`** |
| Mandatory KG after joiner / multi-agent Stage 1 | **`specs/knowledge-graph/`** |
| FR-010 components / seed fleet | **`specs/recommendation-pipeline/`** (service) |
| Deferred recommend JSON envelope | **`specs/recommendation-intake/`** (deferred) |

---

## How agents should work (Spec-kit + OpenSPDD + OpenSpec)

1. **Read** constitution + Path B specs for live work (or Path C if reattach).
2. **Propose** changes under `openspec/changes/<name>/` with:
   - `proposal.md` (why/scope)
   - `specs/<cap>/spec.md` deltas (`## ADDED|MODIFIED|REMOVED Requirements`)
   - `design.md` as **REASONS Canvas** (Requirements, Entities, Approach, Structure, Operations, Norms, Safeguards)
   - `tasks.md` checkbox list
3. **Structured prompts:** if agents change, edit `app/agents/prompts.py` (or `openspec/spdd/prompts/`) **before** or **with** code — never only in chat.
4. **Implement** tasks; keep specs/prompts/code in the same change set.
5. **Converge:** verify tests + scenarios; on mismatch, fix spec/prompt first.
6. **Archive** completed changes into `changes/archive/` and merge requirements into `specs/`.

### Suggested first read (new engineer)

1. This file (flow)  
2. `project.md`  
3. `specs/indexing/spec.md`  
4. `specs/knowledge-graph/spec.md`  
5. `.env.example` + `postman/README`  

---

## Legacy path

Old flat files lived under `specification/`. That directory now holds **redirect stubs** only. Prefer `openspec/` for all new work.
