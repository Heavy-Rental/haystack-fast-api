# Architectural Decision Records (MADR)

This directory is the **accepted decision log** for `haystack-fast-api`.

| Standard | Owns |
|----------|------|
| **OpenSpec** (`../specs/`) | Observable behaviour (Requirements + Scenarios) |
| **OpenSPDD** (`../specs/<cap>/design.md`, `../spdd/`) | Design contract (REASONS Canvas) and structured prompts |
| **MADR** (this folder) | One architecturally significant *choice* and its rationale |

ADRs do **not** replace capability specs. Specs say *what the system does*. ADRs say *which alternative we chose and why*.

Format: [Markdown Architectural Decision Records](https://adr.github.io/madr/) (short/medium template). Status values: Proposed · Accepted · Deprecated · Superseded.

## Index

| ID | Title | Status | Date | Trace |
|----|-------|--------|------|-------|
| [ADR-0001](./0001-sdd-stack-openspec-openspdd-madr.md) | OpenSpec + Spec-kit + OpenSPDD + MADR as the SDD stack | Accepted | 2026-08-10 | constitution |
| [ADR-0002](./0002-postgres-hostname-postgres-haystack.md) | PostgreSQL hostname `postgres-haystack`, not `db` | Accepted | 2026-08-10 | project-setup |
| [ADR-0003](./0003-dual-hop-call1-ingest-call2-recommend-call3-qa.md) | Call 1 ingest, Call 2 recommend quote, Call 3 chatbot Q&A | Accepted | 2026-08-12 | portal-dual-hop FR-PDH-* |
| [ADR-0004](./0004-in-process-predict-price-no-renter-http.md) | In-process `predict_price`; no public renter pricing HTTP | Accepted | 2026-08-11 | dynamic-pricing US-1/US-3/US-4 |
| [ADR-0005](./0005-scheduler-only-pricing-retrain.md) | Default-disabled monthly APScheduler is the sole retrain trigger | Accepted | 2026-08-19 | dynamic-pricing Phase 3a–3d |
| [ADR-0006](./0006-fleet-backend-sql-quote-identity.md) | `FLEET_BACKEND` fake CI / sql live; quote `equipment.id` = `assets.id` | Accepted | 2026-08-13 | S4 / fleet-read-contract |
| [ADR-0007](./0007-document-store-memory-default-pgvector.md) | `INDEXING_DOCUMENT_STORE` memory default vs pgvector | Accepted | 2026-08-12 | FR-IX-027/028 |
| [ADR-0008](./0008-recommend-graph-flag-default-off.md) | `RECOMMEND_VIA_AGENT_GRAPH` default off; same Call 2 quote DTO | Accepted | 2026-08-12 | S7.5 |
| [ADR-0009](./0009-neo4j-fake-default-kg1-kg2-isolation.md) | `NEO4J_BACKEND` fake default vs bolt; KG-1 ≠ KG-2 | Accepted | 2026-08-13 | FR-KG-011 / S8.3 |
| [ADR-0010](./0010-call2-quote-quantity-collapse.md) | Collapse Call 2 unit-need siblings that share `equipment.id` | Accepted | 2026-08-20 | FR-P-013 |
| [ADR-0011](./0011-llm-need-decompose-timeout-retry.md) | LLM need-decompose: retry once on timeout, then keyword fallback | Accepted | 2026-08-20 | FR-P-014 |

## When to write an ADR

Write a numbered ADR when a change is **flag-gated**, **cross-boundary**, **irreversible**, or chooses among real alternatives. Record it in the OpenSpec change folder as `adr.md` **and** add the numbered file here before archive.

Do **not** write an ADR for every OpenSpec requirement. Behaviour belongs in `spec.md`.

## Template (short)

```markdown
# Title

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | YYYY-MM-DD |
| **Deciders** | team |

## Context and Problem Statement

## Considered Options

* Option A
* Option B

## Decision Outcome

Chosen option: "…", because …

### Consequences

* Good: …
* Bad / accepted: …
```
