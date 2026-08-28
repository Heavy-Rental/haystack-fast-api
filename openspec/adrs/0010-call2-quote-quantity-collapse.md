# Collapse Call 2 unit-need siblings that share `equipment.id`

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-20 |
| **Deciders** | haystack-fast-api |
| **Trace** | FR-P-013 |
| **OpenSpec** | [`../specs/recommendation-pipeline/spec.md`](../specs/recommendation-pipeline/spec.md) |
| **Change** | [`../changes/archive/2026-08-20-call2-quote-quantity-collapse/`](../changes/archive/2026-08-20-call2-quote-quantity-collapse/) |

## Context and Problem Statement

FR-006 expands `quantity: N` into N unit-needs. `RecommendationItem` MUST NOT carry `quantity`. Mapping each unit-need to its own Call 2 line shows duplicate equipment rows when siblings resolve to the same `equipment.id`.

A first implementation used `needId.split("_")` / `pop()`; that breaks ids such as `need_access__u1` and dropped the wrong row.

## Considered Options

* Collapse all unit-needs of a parent regardless of equipment id
* Collapse globally by `equipment.id`
* Put `quantity` on `RecommendationItem`
* Collapse only on the Call 2 quote by `(parent_need_id, equipment.id)` using `{base}__u{i}`

## Decision Outcome

Chosen option: **quote-layer collapse after `map_recommend_to_quote`**.

- Merge key: parent `{base}` of `{base}__u{i}` **and** `equipment.id`
- Merged `quantity` = duplicate count; `lineTotal` summed; `needId` = parent
- `quantity > 1` → `equipment.available = false`
- Quantity-1 availability reads `bookings` + `return_records`
- Do not merge across parent needs or distinct equipment ids
- Internal `results_by_need` stays expanded

### Consequences

* Good: portal quote is a commercial line; FR-006 / FR-P-005 / FR-P-010 remain true on the service path.
* Bad / accepted: `items[]` length can be smaller than `results_by_need`; ranking uniqueness of physical assets is out of scope.
