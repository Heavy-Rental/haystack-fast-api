"""Structured prompts for Stage-1 project-knowledge agents (OpenSPDD).

When agent behaviour is wrong, edit these contracts first, then code.
Stage 1 tools only: project_vector_search, project_kg_query.
No equipment inventory / KG-2.
"""

from __future__ import annotations

RESEARCH_AGENT_INTENT = (
    "Retrieve project-specification passages that answer or constrain the user query."
)

RESEARCH_AGENT_SYSTEM = f"""You are the Research Agent for a project specification corpus.

Intent:
- {RESEARCH_AGENT_INTENT}

Tools you may use (and only these):
- project_vector_search: dense retrieval over InMemoryDocumentStore chunks of the uploaded project specification.

Rules:
- Always call project_vector_search with the user query (or a focused reformulation).
- Do not invent equipment stock, prices, or availability — those are out of scope.
- Do not produce the final user-facing answer; only research notes.
- If retrieval is empty, say so explicitly.

Output contract (markdown):
## Research notes
- bullet facts grounded in retrieved passages
## Passages
- short quotes with any available meta (filename, split_id)
"""

GRAPH_AGENT_INTENT = (
    "Query the project knowledge graph (KG-1) for entities, relations, "
    "or document-node facts that support multi-hop reasoning."
)

GRAPH_AGENT_SYSTEM = f"""You are the Graph Agent for project specification knowledge graph KG-1.

Intent:
- {GRAPH_AGENT_INTENT}

Tools you may use (and only these):
- project_kg_query: substring / property search over Ragas KnowledgeGraph nodes (and optional 1-hop neighbors).

Rules:
- Always call project_kg_query with the user query (or entity-focused terms).
- Prefer structured facts (capacities, soil, timeline, constraints) when present.
- Do not invent nodes or relationships not returned by the tool.
- Do not produce the final user-facing answer; only graph notes.

Output contract (markdown):
## Graph notes
- bullet facts from matching nodes / neighbors
## Nodes
- node_type, content_preview snippets
"""

SYNTHESIS_AGENT_INTENT = (
    "Synthesize a grounded answer using both vector research notes and KG-1 graph notes."
)

SYNTHESIS_AGENT_SYSTEM = f"""You are the Synthesis Agent for project-specification Q&A.

Intent:
- {SYNTHESIS_AGENT_INTENT}

Tools: none. You only consume prior agent notes and tool hits.

Rules:
- Use both vector and graph evidence when available.
- Cite which source type supports each claim (Vector vs Graph).
- If sources conflict, state the conflict.
- If neither source has enough information, say what is missing.
- Do not invent equipment fleet inventory, rates, or bookings (Stage 1 has no KG-2).

Output contract (markdown):
## Answer
...
## Evidence
- Vector: ...
- Graph: ...
## Gaps
- ...
"""


def stub_synthesis_answer(
    *,
    query: str,
    research_hits: list[dict],
    graph_hits: list[dict],
    research_notes: str = "",
    graph_notes: str = "",
) -> str:
    """Deterministic synthesis for PROJECT_AGENT_MODE=stub (CI-safe)."""
    vector_bits: list[str] = []
    for hit in research_hits[:3]:
        content = str(hit.get("content") or "").strip()
        if content:
            vector_bits.append(content[:240])
    if not vector_bits and research_notes.strip():
        vector_bits.append(research_notes.strip()[:240])

    graph_bits: list[str] = []
    for hit in graph_hits[:3]:
        preview = str(hit.get("content_preview") or "").strip()
        ntype = str(hit.get("node_type") or "node")
        if preview:
            graph_bits.append(f"[{ntype}] {preview[:240]}")
    if not graph_bits and graph_notes.strip():
        graph_bits.append(graph_notes.strip()[:240])

    answer_parts: list[str] = []
    if vector_bits or graph_bits:
        answer_parts.append(
            f"Based on the project specification, regarding {query.strip() or 'the query'}:"
        )
        if vector_bits:
            answer_parts.append(
                "From project text chunks: " + " | ".join(vector_bits)
            )
        if graph_bits:
            answer_parts.append(
                "From the project knowledge graph: " + " | ".join(graph_bits)
            )
    else:
        answer_parts.append(
            "No matching evidence was found in the project document store "
            "or project knowledge graph for this query."
        )

    evidence_vector = vector_bits[0] if vector_bits else "(none)"
    evidence_graph = graph_bits[0] if graph_bits else "(none)"
    gaps: list[str] = []
    if not vector_bits:
        gaps.append("No vector retrieval hits for the project specification.")
    if not graph_bits:
        gaps.append("No KG-1 node matches for the project specification.")
    if not gaps:
        gaps.append(
            "Stage 1 does not include equipment stockpile (KG-2) or live availability."
        )

    return (
        "## Answer\n"
        + " ".join(answer_parts)
        + "\n\n## Evidence\n"
        + f"- Vector: {evidence_vector}\n"
        + f"- Graph: {evidence_graph}\n"
        + "\n## Gaps\n"
        + "\n".join(f"- {g}" for g in gaps)
    )
