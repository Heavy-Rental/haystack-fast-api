# `FLEET_BACKEND` fake CI / sql live; quote `equipment.id` = `assets.id`

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-13 |
| **Deciders** | haystack-fast-api |
| **Trace** | S4; `openspec/specs/spring-entity-repository/fleet-read-contract.md` |

## Context and Problem Statement

Call 2 must return equipment Spring can FK. Seed catalog ids (`AST-*`) are not `assets.id`. Live SQL vs CI isolation also conflict.

## Considered Options

* Always seed catalog (CI-shaped quotes in production)
* Always SQL (CI needs a live fleet DB)
* Flag: `FLEET_BACKEND=fake` (CI default) vs `sql` (live); no silent seed fallback on sql

## Decision Outcome

Chosen option: **flag with no silent fallback**.

- Live SQL: quote `equipment.id` = `assets.id` (PK). Internal DTO `asset_id` stays `assets.name`.
- Missing assets row → omit the item + warning (never emit seed `AST-*` on the sql path).
- `PRICING_SCHEMA` remaps fleet/pricing ORM reads only (`primary_snapshot` CI default; `public` live).

### Consequences

* Good: Spring can persist `recommendation_items.asset_id` as a real FK; pytest stays isolated.
* Bad / accepted: two identity fields (`equipment.id` vs DTO `asset_id`) must stay documented on the Call 2 contract.
