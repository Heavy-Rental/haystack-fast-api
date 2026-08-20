# ADR: Collapse duplicate Call 2 equipment quotes by parent need + equipment.id

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-20 |
| **Capability** | recommendation-pipeline (Call 2 quote) |
| **Trace** | FR-P-013 |
| **OpenSpec** | [`specs/recommendation-pipeline/spec.md`](../../specs/recommendation-pipeline/spec.md) |
| **OpenSPDD** | [`design.md`](./design.md) |

## Context

FR-006 expands `quantity: N` into N independent unit-needs before ranking.
`RecommendationItem` MUST NOT carry `quantity`. Call 2 maps each unit-need to a
portal quote line with `quantity=1`.

When unit-needs of the same parent (`need_1__u1`, `need_1__u2`, `need_1__u3`)
select the same catalog asset, the quote shows identical `equipment` objects.
The portal envelope is a commercial quote (`quoteRef`, `lineTotal`, `quantity`),
so duplicate rows are worse than one line with `quantity` equal to the duplicate
count (3 copies → `quantity: 3`).

A first implementation attempted to detect duplicates by `needId.split("_")`
and mutate the list while iterating. That heuristic is wrong for
`need_access__u1`, `pop()` removes the wrong item, and the collapsed list was
never returned.

## Decision

Collapse **only on the Call 2 quote**, after `results_by_need` is mapped:

1. Identify unit-need ids with the expansion suffix `{base}__u{i}`.
2. Group by `(parent_need_id, equipment.id)`.
3. Merge groups larger than one: `quantity` = number of grouped duplicates
   (each Call 2 line is `quantity=1`, so 3 copies → `quantity: 3`),
   `lineTotal` = sum, `needId` = parent `{base}`, keep the first line's
   equipment and daily rate.
4. If merged `quantity > 1`, set `equipment.available = false` — one
   physical `assets.id` cannot fulfill N concurrent units. Do not count
   other machines in the same category.
5. Quantity-1 availability reads live-hold `bookings` (via `booking_items`)
   and `return_records.returned_at` (`PRICING_SCHEMA=public` →
   `heavy_rental.public`). A return ends the hold on that day.
6. Leave ungrouped lines unchanged (including qty-1 `need_1` and distinct
   equipment under the same parent).
7. Do not merge the same `equipment.id` across different parent needs.

Internal pipeline output (`results_by_need`) stays expanded.

## Consequences

### Positive

- Portal quote matches commercial expectation: one equipment row, higher qty.
- FR-006 / FR-P-005 / FR-P-010 remain true on the service path.
- `needId` on a merged line correlates to Call 1 `needs_summary[].need_id`.

### Negative / accepted

- Quote `items[]` length can be smaller than `results_by_need` length.
- If ranking selected the same physical asset N times, the quote still shows
  `quantity: N` of that id but `available` is false (ranking uniqueness is
  out of scope).
- Distinct assets for the same parent need still appear as separate lines.

### Rejected alternatives

| Alternative | Why not |
|-------------|---------|
| Collapse all unit-needs of a parent regardless of equipment id | Drops a second distinct asset from the quote |
| Collapse globally by `equipment.id` | Mixes unrelated needs (e.g. access + earthwork) |
| Put `quantity` on `RecommendationItem` | Violates FR-006 / FR-P-005 |
| `needId.split("_")` parent detection | Breaks ids such as `need_access__u1` |
