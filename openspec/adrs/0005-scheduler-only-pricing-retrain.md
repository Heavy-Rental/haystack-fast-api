# Default-disabled monthly APScheduler is the sole retrain trigger

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-19 |
| **Deciders** | haystack-fast-api + pricing |
| **Trace** | dynamic-pricing Phase 3a–3d; `docs/dynamic-pricing-scheduled-retrain-plan.md` |

## Context and Problem Statement

Phase 2 spec'd a manual “retrain now” HTTP endpoint as a demo safety net. It was never built. Automated monthly retrain can regress against production guardrails (why Phase 2d/2e gated promotion exists).

## Considered Options

* Manual HTTP retrain endpoint (US-2)
* Unlimited/always-on background retrain
* Default-disabled in-process APScheduler with validate-before-promote

## Decision Outcome

Chosen option: **scrap the HTTP endpoint**. Sole runtime trigger is `AsyncIOScheduler` in FastAPI lifespan, default **off** (`PRICING_RETRAIN_ENABLED=false`), interval 30 days.

Pipeline: blend real+synthetic rows → train **candidate** artifacts → `promotion_gate` (min-asset mode) → promote only on pass with one rolling backup and rollback on promotion failure. Job never raises. No retrain route in OpenAPI.

### Consequences

* Good: CI `TestClient` lifespan does not start training; serving model cannot be swapped by an unauthenticated HTTP call.
* Bad / accepted: worst-case wait is the interval (or one coalesced misfire); no “retrain now” operator button; `distance_km` remains imputed.
