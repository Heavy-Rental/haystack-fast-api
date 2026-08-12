# Feasibility Study: Indexing Pipeline as a Haystack SuperComponent

| Field | Value |
|-------|--------|
| **Document type** | Architecture / Haystack packaging feasibility study |
| **Status** | Complete (study only — no implementation) |
| **Date** | 2026-08-10 |
| **Version** | 1.2.1 |
| **Application** | `haystack-fast-api` indexing (Plane B step **[4]**) |
| **Question** | Can the existing **indexing pipeline** (`build_indexing_pipeline` / `run_indexing_pipeline`) be packaged as a Haystack **SuperComponent**? |
| **As-built** | `app/pipelines/indexing/pipeline.py`, `app/services/indexing.py` |
| **Haystack ref** | [SuperComponents](https://docs.haystack.deepset.ai/docs/supercomponents) · hierarchy in `openspec/specs/equipment-recommendation/` (Component → Pipeline → SuperComponent → Tool → Agent) |
| **Related studies** | [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md) §4 · [`multi-agent-coordinator-worker-delegator.md`](./multi-agent-coordinator-worker-delegator.md) (**[4]** = Coordinator gate, not Worker) |

---

## 1. Executive summary

### Question

Is it **feasible** to wrap the dual-branch FileTypeRouter indexing **Pipeline** as a **SuperComponent** so Multi-Agent / tools / outer pipelines see a single component with a simple `run(sources=…)` interface?

### Verdicts

| Question | Result |
|----------|--------|
| Can the **Pipeline graph** be wrapped as SuperComponent? | **GO** |
| Prefer `@super_component` decorator + `self.pipeline`? | **Yes** (Haystack recommended) |
| Drop `build_indexing_pipeline` / keep factory inside SuperComponent `__init__`? | **Either** — factory remains; SuperComponent owns one built pipeline |
| SuperComponent alone replaces `run_indexing_pipeline` summary logic? | **Partial** — need **output mapping** and/or thin post-process adapter for API parity |
| SuperComponent includes **mandatory KG-1**? | **NO** — keep KG in `IndexingIngestService` (or separate component) after index |
| SuperComponent as body of agent indexing tool? | **GO** — service/SC; prefer multipart on FastAPI for Spring |
| Required for Stage-1 / dual-plane T0–T1? | **No** — optional packaging refactor (R1-friendly) |
| Blockers | Intermediate outputs (`include_outputs_from`), per-ingest DocumentStore, multi-MIME router sockets |

**Overall:** **GO with design constraints.** Turning the indexing pipeline into a SuperComponent is **Haystack-idiomatic** and aligns with the product hierarchy (SuperComponent → Tool → Agent). It **simplifies** reuse as step **[4]** for Multi-Agent, but **must not** swallow service-layer concerns (user/ingest stamping, KG hard-fail, HTTP DTO assembly).

---

## 2. As-built indexing shape

### 2.1 Pipeline graph (`build_indexing_pipeline`)

```text
file_type_router
  ├─ MIME → converters (text/md/pdf/html/docx/json/xlsx)
  │         → unstructured_doc_joiner → sanitizer → cleaner → splitter ─┐
  └─ CSV → csv_converter → csv_cleaner → csv_splitter ──────────────────┤
                                                                         ▼
                                                                  final_doc_joiner
                                                                         │
                                                                   doc_embedder
                                                                         │
                                                                      writer  → DocumentStore
```

- **Input socket (logical):** `file_type_router.sources` ← `list[ByteStream | path]`  
- **Side effect:** `DocumentWriter` writes embeddings to injected **DocumentStore** (as-built InMemory per ingest; **target Pgvector** I1)  
- **Many internal components** (~15+); dual-branch MIME fan-out

### 2.2 `run_indexing_pipeline` (not pure SuperComponent output)

Today’s runner:

1. `pipeline.run({file_type_router: {sources}}, include_outputs_from={router, joiners, splitters, embedder, writer})`  
2. **Post-processes** router buckets → `data_kind`, counts, filenames  
3. Merges **chunk_documents** / `final_doc_joiner_documents` / `documents_written` for **KG input** and HTTP DTO  

A naïve SuperComponent with only `writer.documents_written` would **lose** KG-friendly chunk lists unless **output_mapping** (or a small adapter) exposes them.

### 2.3 Service layer (`IndexingIngestService`)

Outside the Pipeline:

| Concern | Where |
|---------|--------|
| `user_id` / `ingest_id` meta stamp on ByteStreams | Service |
| Per-ingest **InMemory** store (or future Pgvector factory) | Service |
| Embedder settings from config | Service → `build_indexing_pipeline` |
| **Mandatory KG-1** after chunks | Service (`run_knowledge_graph`) |
| Session registry put | Service |
| Lean `IngestFromProjectSpecResponse` (`ingest_id`, `user_id`, `user_requirement_summary`, `warnings`) | Service (public HTTP); SC must not own this DTO |

**SuperComponent boundary:** wrap **only** the Haystack graph (convert → split → embed → write), not the full ingest saga or lean public response assembly.

---

## 3. What SuperComponent is (Haystack)

From Haystack docs:

- **`@super_component`** class with a **`pipeline`** attribute — recommended  
- Optional **`input_mapping`** / **`output_mapping`** to simplify sockets  
- Runs like a single **component** (`run(...)`)  
- Use cases: reuse complex pipeline, nest in outer Pipeline, expose to tools  

Related (not the same):

| Construct | Role |
|-----------|------|
| **SuperComponent** | Pipeline as one component |
| **PipelineTool** / **ComponentTool** | Expose pipeline/component to LLM tools |

Product OpenSpec already targets SuperComponents for **recurring subgraphs** (equipment-recommendation FR-019a); indexing is a natural **first** candidate for Plane B.

---

## 4. Feasibility analysis

### 4.1 Wrapping the graph — **GO**

Illustrative (non-normative):

```python
from haystack import Pipeline, super_component
from haystack.dataclasses import ByteStream
from app.pipelines.indexing.pipeline import build_indexing_pipeline

@super_component
class IndexingPipelineSuperComponent:
    """Dual-branch file-type indexing as a single component."""

    def __init__(self, document_store, embedder=None, **split_kwargs):
        self.pipeline = build_indexing_pipeline(
            document_store=document_store,
            embedder=embedder,
            **split_kwargs,
        )
        # Optional explicit maps (recommended for multi-MIME router):
        # self.input_mapping = {"sources": ["file_type_router.sources"]}
        # self.output_mapping = {
        #     "writer.documents_written": "documents_written",
        #     "final_doc_joiner.documents": "documents",
        #     "doc_embedder.documents": "embedded_documents",
        # }
```

| Aspect | Assessment |
|--------|------------|
| Graph already a `Pipeline` | **GO** — no rewrite of converters |
| Single logical input `sources` | **GO** — map to `file_type_router.sources` |
| Inject store / embedder | **GO** — constructor deps (per-ingest store still built by service) |
| Nest in larger Pipeline | **GO** — e.g. outer agent pipeline step |
| Serialize with `to_dict` | **Optional** with decorator path |

### 4.2 Output / observability — **CONDITIONAL**

| Need | SuperComponent alone | Mitigation |
|------|----------------------|------------|
| `documents_written` | Map `writer.documents_written` | **GO** |
| Chunks for KG (`final_doc_joiner` / embedder docs) | Map intermediate outputs | **GO** with `output_mapping` + ensure pipeline surfaces them |
| `data_kind` / MIME summary | Not a native component output | Keep **`summarize_router_output`** in adapter **or** add a tiny `@component` at end of graph |
| `include_outputs_from` parity | SuperComponent exposes mapped sockets only | Explicit maps for joiner/embedder/writer/router if needed |
| Unclassified sources list | Router side outputs | Map or summarize in adapter |

**Recommendation:** SuperComponent returns **documents + documents_written** (+ optional router raw); service/adapter still builds **ingest DTO** and runs **KG**.

### 4.3 Multi-user / Pgvector — **GO** (factory pattern)

| Mode | SuperComponent usage |
|------|----------------------|
| As-built per-ingest InMemory | `IndexingPipelineSuperComponent(document_store=session_store)` each ingest |
| I1 Pgvector shared store | One SC with shared store; meta filters on docs still stamped pre-run |
| Tests inject pipeline | Keep inject path: pass prebuilt Pipeline into SC **or** bypass SC in tests |

### 4.4 Multi-Agent — **GO** as packaging for tool **[4]** (Coordinator gate)

**[4]** is a **forced non-agent tool edge** under the **Coordinator** — not an LLM **Worker** agent. SuperComponent (if used) is only packaging for the dual-branch pipeline inside the service path.

```text
Multi-Agent Orchestrator (Coordinator)
  └─ gate tool run_indexing_from_request   # non-LLM forced edge
        └─ IndexingIngestService  (meta + KG + session)
              └─ IndexingPipelineSuperComponent.run(sources=…)
                    └─ dual-branch Pipeline
```

| Path | Feasible? |
|------|-----------|
| Coordinator gate tool → service → SuperComponent | **Preferred** |
| Gate tool → SuperComponent only | **Risky** — loses KG hard-fail & DTO |
| PipelineTool(LLM) wrapping full index | **Avoid for [4]** — free-form LLM tool calling must not own the gate (forced index edge) |

### 4.5 What should **not** be inside the SuperComponent

| Leave outside | Why |
|---------------|-----|
| KG-1 generation | Hard-fail product rule; separate pipeline/runner |
| Session registry | App state, not Haystack graph |
| HTTP / multipart parse | FastAPI layer |
| Spring auth / user_id validation | API layer |
| Fleet / Neo4j / pricing | Different tools after [4] |

---

## 5. Options comparison

| Option | Description | Extra complexity | Recommendation |
|--------|-------------|------------------|----------------|
| **A. Status quo** | `build_*` + `run_*` + service | Low | Keep until packaging pain |
| **B. SuperComponent wrapper** | `@super_component` around existing builder | Low–medium | **Recommended next packaging step** |
| **C. SuperComponent + end-of-graph Summarizer component** | Move summary into pipeline | Medium | If DTO fields must be pure pipeline outputs |
| **D. PipelineTool only** | Skip SuperComponent; tool wraps Pipeline | Medium | Use if only LLM tools need it; SuperComponent still nicer for nesting |
| **E. Entire ingest+KG as SuperComponent** | One mega SC | High | **Avoid** — violates separation of index vs KG |

---

## 6. Risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Lost intermediate outputs for KG | High | Map `final_doc_joiner.documents` / embedder docs; keep adapter tests |
| MIME fan-out confuses auto I/O maps | Medium | Explicit `input_mapping` / `output_mapping` |
| Per-ingest store vs long-lived SC | Medium | Construct SC per ingest or inject store carefully; Pgvector is shared |
| Double API: `run_indexing_pipeline` + SC | Medium | SC calls shared builder; deprecate direct run helper or make run call SC |
| Test churn | Medium | Keep pipeline unit tests; add SC smoke test |
| Over-wrapping with KG | High | Spec boundary: index SC only |

---

## 7. Phasing (optional)

| Phase | Work | Depends on | Status |
|-------|------|------------|--------|
| **S0** | This study | — | Done (study) |
| **R1 / impl S3** | Agent tool `run_indexing_from_request` + Coordinator gate (service wrap; not raw SC) | — | **As-built** (FR-IX-026; flag default off) |
| **S1** | Add `IndexingPipelineSuperComponent` wrapping `build_indexing_pipeline` | — | Deferred (optional S3.3) |
| **S2** | `IndexingIngestService` uses SC; preserve KG + DTO | S1 | Deferred |
| **S3** (SC study numbering) | Agent tool calls same service (not raw SC) | R1 | **Done via R1** (tool → service; SC not required) |
| **S4** | Optional: nest SC in outer Haystack pipeline | Product need | Deferred |
| **S5** | I1: SC writer → Pgvector store | I1 | Deferred |

**Not on critical path** for fleet sync T0–T1 or Stage-1 Q&A. SuperComponent packaging remains optional after R1.

---

## 8. Relationship to other feasibility topics

| Topic | Interaction |
|-------|-------------|
| Dual-plane **[4]** indexing tool | SuperComponent is the **Haystack packaging** of that tool’s core graph |
| Agent `run_indexing_from_request` | Prefer service (index + KG), which may call SuperComponent |
| Pgvector I1 | Writer store behind SC constructor |
| Recommend **[5]–[8]** | Only after SC/index + KG succeed |

---

## 9. Open questions

1. Expose SuperComponent publicly in `app/pipelines/indexing/__init__.py` or keep internal to service?  
2. Is a pipeline-native **Summarizer** component worth it for pure SC outputs?  
3. Prefer **PipelineTool** for free ReAct later, or forced LangGraph edge only?  

---

## 10. References

- Haystack: [SuperComponents](https://docs.haystack.deepset.ai/docs/supercomponents)  
- Haystack: [PipelineTool](https://docs.haystack.deepset.ai/docs/pipelinetool) (tool wrapper alternative)  
- As-built: `app/pipelines/indexing/pipeline.py`, `app/services/indexing.py`  
- OpenSpec: `openspec/specs/indexing/`, equipment-recommendation SuperComponent hierarchy  
- Dual-plane: [`postgres-haystack-neo4j-realtime-sync.md`](./postgres-haystack-neo4j-realtime-sync.md)  

---

## 11. Document control

| Version | Date | Notes |
|---------|------|--------|
| **1.0.0** | 2026-08-10 | Initial: indexing Pipeline → SuperComponent **GO** with boundary (no KG inside) |
| **1.1.0** | 2026-08-10 | Remove FastMCP packaging language |
| **1.2.0** | 2026-08-11 | **[4]** = Coordinator gate (non-agent); not Worker; LLM PipelineTool avoided for gate |
| **1.2.1** | 2026-08-11 | Service owns lean Call 1 DTO; SuperComponent stays pipeline-only |

---

## 12. One-page decision card

| Decision | Recommendation |
|----------|----------------|
| Indexing pipeline as SuperComponent? | **Yes (GO)** |
| Mechanism | **`@super_component`** + existing `build_indexing_pipeline` |
| Include KG-1 in SuperComponent? | **No** |
| Include HTTP DTO / session registry? | **No** |
| Required now? | **No** — optional packaging |
| Multi-Agent [4] | **Coordinator gate** → service → SuperComponent.run(sources) |
| [4] is LLM Worker? | **No** |
| Agent indexing tool | Wrap service/SC; Spring stays REST multipart |
| Outputs | Map documents + documents_written; keep summary adapter if needed |
| Avoid | Mega SuperComponent (index+KG+session); silent loss of chunk outputs for KG |
