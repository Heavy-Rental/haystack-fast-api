# OpenSPDD Prompt Index: Project Knowledge Agents

| Field | Value |
|-------|--------|
| **Capability** | `knowledge-graph` Part B (Stage 1) |
| **Authoritative prompts** | [`app/agents/prompts.py`](../../../app/agents/prompts.py) |
| **Behaviour** | [`openspec/specs/knowledge-graph/spec.md`](../../specs/knowledge-graph/spec.md) |
| **Design** | [`openspec/specs/knowledge-graph/design.md`](../../specs/knowledge-graph/design.md) |

> **OpenSPDD rule:** When agent behaviour is wrong, **edit the structured prompts in `app/agents/prompts.py` first**, then code (and update the capability spec/design if contracts change). Do not rely on chat-only prompt tweaks.

Stage 1 tools only: `project_vector_search`, `project_kg_query`. **No** equipment inventory / KG-2.

---

## Intents & tool allowlists

| Constant | Agent | Intent (summary) | Tools |
|----------|-------|------------------|-------|
| `RESEARCH_AGENT_INTENT` | Research | Retrieve project-specification passages that answer or constrain the user query. | **`project_vector_search` only** (dense retrieval over InMemoryDocumentStore chunks) |
| `GRAPH_AGENT_INTENT` | Graph | Query project knowledge graph **KG-1** for entities, relations, or document-node facts that support multi-hop reasoning. | **`project_kg_query` only** (substring / property search over Ragas nodes + optional 1-hop neighbors) |
| `SYNTHESIS_AGENT_INTENT` | Synthesis | Synthesize a grounded answer using both vector research notes and KG-1 graph notes. | **None** — consumes prior agent notes and tool hits only |

System prompt constants: `RESEARCH_AGENT_SYSTEM`, `GRAPH_AGENT_SYSTEM`, `SYNTHESIS_AGENT_SYSTEM`.

---

## Output contracts (normative markdown)

### Research

```text
## Research notes
- bullet facts grounded in retrieved passages
## Passages
- short quotes with any available meta (filename, split_id)
```

**Rules (prompt):** Always call `project_vector_search`; do not invent equipment stock/prices/availability; do not produce the final user-facing answer; state empty retrieval explicitly.

### Graph

```text
## Graph notes
- bullet facts from matching nodes / neighbors
## Nodes
- node_type, content_preview snippets
```

**Rules (prompt):** Always call `project_kg_query`; prefer structured facts (capacities, soil, timeline, constraints); do not invent nodes/relationships; graph notes only.

### Synthesis

```text
## Answer
...
## Evidence
- Vector: ...
- Graph: ...
## Gaps
- ...
```

**Rules (prompt):** Use both vector and graph evidence when available; cite source type; state conflicts; state missing info; do not invent fleet inventory/rates/bookings (Stage 1 has no KG-2).

---

## Stub synthesis (CI)

`stub_synthesis_answer(...)` in the same module builds a deterministic markdown answer from `research_hits` / `graph_hits` (and optional notes) when `PROJECT_AGENT_MODE=stub`. Use `llm` only with `LLM_*` configured.

---

## Topology binding

Fixed sequential LangGraph (Stage 1):

```text
research_agent → graph_agent → synthesis_agent
```

Env: `PROJECT_AGENT_MODE` (`stub` \| `llm`), `PROJECT_AGENT_TOP_K` (default 5).
