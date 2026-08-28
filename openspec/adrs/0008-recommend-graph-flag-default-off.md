# `RECOMMEND_VIA_AGENT_GRAPH` default off; same Call 2 quote DTO

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Deciders** | haystack-fast-api |
| **Trace** | S7.5 / S7.6 |

## Context and Problem Statement

Phase 7 built a C/W/D LangGraph for recommend. Call 2 MVP already returns a quote via `RecommendationService`. Switching the public route to the graph overnight would couple portal contract to agent gate failures.

## Considered Options

* Always run the recommend graph on Call 2
* Graph-only new route
* Same Call 2 path; flag `RECOMMEND_VIA_AGENT_GRAPH` (default false)

## Decision Outcome

Chosen option: **flag, default off**. When on, `SessionRecommendService` runs `run_recommend_graph` and still maps to the same quote DTO. Gate refuse → HTTP 400. `tool_traces` stay on graph state, never on the public body.

### Consequences

* Good: portal contract is stable; CI forces the flag off in `conftest.py`.
* Bad / accepted: production default remains the service MVP until an explicit SDD flips the flag.
