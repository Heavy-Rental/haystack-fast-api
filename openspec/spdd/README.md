# OpenSPDD — REASONS canvases and prompt indexes

OpenSPDD treats **structured prompts** and **REASONS canvases** as first-class contracts.

**Rule:** when agent behaviour is wrong, **edit the prompt (and spec) first**, then code.

## Canvases

Live canvases live next to capability specs as `openspec/specs/<cap>/design.md` (not copies). `canvases/` is reserved for optional standalone canvases; do not duplicate a live `design.md` here.

| Capability | Canvas | Complete R-E-A-S-O-N-S? |
|------------|--------|-------------------------|
| project-setup | [`../specs/project-setup/design.md`](../specs/project-setup/design.md) | Yes |
| indexing | [`../specs/indexing/design.md`](../specs/indexing/design.md) | Yes |
| knowledge-graph | [`../specs/knowledge-graph/design.md`](../specs/knowledge-graph/design.md) | Yes |
| portal-dual-hop | [`../specs/portal-dual-hop/design.md`](../specs/portal-dual-hop/design.md) | Yes |
| recommendation-pipeline | [`../specs/recommendation-pipeline/design.md`](../specs/recommendation-pipeline/design.md) | Yes |
| equipment-recommendation | [`../specs/equipment-recommendation/design.md`](../specs/equipment-recommendation/design.md) | Yes |
| dynamic-pricing | [`../specs/dynamic-pricing/design.md`](../specs/dynamic-pricing/design.md) | Yes |
| domain-seed-data | [`../specs/domain-seed-data/design.md`](../specs/domain-seed-data/design.md) | Yes |
| domain | (Entities live in `spec.md`; no separate canvas) | n/a |
| recommendation-intake | Light behaviour-only (deferred envelope) | n/a |
| spring-entity-repository | Schema read-copy; not a behaviour canvas | n/a |

Heading convention: `## R — Requirements`, `## E — Entities`, `## A — Approach`, `## S — Structure`, `## O — Operations`, `## N — Norms`, `## S — Safeguards`.

## Prompts

| Index | Authoritative source |
|-------|----------------------|
| [`prompts/project-knowledge-agents.md`](./prompts/project-knowledge-agents.md) | `app/agents/prompts.py` (Call 3 Q&A) |
| [`prompts/recommend-agents.md`](./prompts/recommend-agents.md) | `app/agents/recommend_prompts.py` (Call 2 C/W/D A–L) |
