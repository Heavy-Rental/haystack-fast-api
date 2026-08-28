# Use OpenSpec + Spec-kit + OpenSPDD + MADR as the SDD stack

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-10 |
| **Deciders** | haystack-fast-api maintainers |
| **Amended** | 2026-08-27 (MADR log added; OpenSpec/OpenSPDD already in force) |

## Context and Problem Statement

How should this service record behaviour, design, implementation tasks, and architectural choices so coding agents and engineers share one source of truth?

## Considered Options

* Chat-only plans and scattered markdown
* OpenSpec (`specs/` + `changes/`) only
* OpenSpec + GitHub Spec-kit constitution/tasks + OpenSPDD REASONS + MADR ADRs

## Decision Outcome

Chosen option: **OpenSpec + Spec-kit + OpenSPDD + MADR**.

| Artifact | Owns |
|----------|------|
| `openspec/specs/<cap>/spec.md` | WHAT — Requirements + Scenarios |
| `openspec/specs/<cap>/design.md` | HOW — OpenSPDD REASONS Canvas |
| `openspec/changes/<name>/` | One unit of work (proposal, delta spec, tasks, optional `adr.md`) |
| `.specify/memory/constitution.md` | Immutable process principles |
| `openspec/adrs/` | Numbered architectural choices |
| `app/agents/prompts.py` / `recommend_prompts.py` | First-class structured prompts |

When behaviour is wrong: **fix spec/prompt first, then code**.

### Consequences

* Good: dual-folder OpenSpec model; REASONS Norms/Safeguards constrain agents; ADRs keep “why we chose X” out of FR tables.
* Bad / accepted: four complementary formats; agents must follow `openspec/AGENTS.md` reading order rather than treating every markdown file as equal.
