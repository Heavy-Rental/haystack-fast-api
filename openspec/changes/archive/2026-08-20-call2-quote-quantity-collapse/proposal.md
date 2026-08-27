# Proposal: Collapse duplicate Call 2 equipment quotes

## Why

Quantity expansion turns a decomposed need with `quantity: N` into N unit-needs
(`{base}__u{i}`). Each unit-need is ranked independently (FR-006 / FR-P-005 /
FR-P-010) and mapped to its own Call 2 quote line with `quantity=1`.

When those siblings resolve to the **same** catalog `equipment.id`, the portal
quote shows duplicate equipment rows instead of one commercial line whose
`quantity` equals the duplicate count (3 copies → `quantity: 3`). The quote
DTO already has `quantity`; the internal `RecommendationItem` must stay
quantity-free.

## Scope

- Collapse Call 2 `items[]` **after** `results_by_need` is mapped to the quote
  envelope (`map_recommend_to_quote`).
- Merge key: parent need id from `{base}__u{i}` **and** `equipment.id`.
- Set merged `quantity` to the number of grouped duplicates and sum
  `lineTotal`; keep the first item's equipment and daily rate; rewrite
  `needId` to the parent `{base}`; re-number `rankOrder`.
- Record the decision as OpenSpec FR-P-013, OpenSPDD REASONS, and an ADR.

## Out of scope

- Changing quantity expansion or `RecommendationItem` (FR-006 stays).
- Merging distinct assets that share a type but not an id.
- Merging the same `equipment.id` across **different** parent needs.
- Changing ranking so the same physical asset is not selected twice.

## Compatibility

Quote `items[]` for quantity-1 needs is unchanged. Golden Call 2 fixtures use
distinct qty-1 needs (`need_access`, `need_earthwork`) and stay valid.
`estimatedTotal` remains the sum of per-unit line totals.
