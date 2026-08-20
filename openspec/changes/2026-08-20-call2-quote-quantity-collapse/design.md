# REASONS Canvas: Collapse duplicate Call 2 equipment quotes

## R — Requirements

See delta [`specs/recommendation-pipeline/spec.md`](./specs/recommendation-pipeline/spec.md)
(**FR-P-013**) and ADR
[`adr.md`](./adr.md).

Call 2 quote MUST fold unit-need siblings that share parent need + catalog
`equipment.id` into one line whose `quantity` is the number of grouped
duplicates (3 copies → `quantity: 3`). Internal `results_by_need` MUST remain
expanded.

## E — Entities

| Concept | Role |
|---------|------|
| DecomposedNeed | Internal need with optional `quantity` |
| UnitNeed | Ranking unit after expansion (`{base}` or `{base}__u{i}`) |
| NeedResult | `{ need_id, item, warnings }` — one per unit-need |
| RecommendQuoteItem | Portal quote line (`quantity`, `needId`, `equipment`) |
| Parent need id | `{base}` extracted from `{base}__u{i}` |

## A — Approach

Keep FR-010 steps 1–8 unchanged. After mapping each `NeedResult` to a
`RecommendQuoteItem`, group quote lines by `(parent_need_id, equipment.id)`
where `parent_need_id` is the `{base}` of a `{base}__u{i}` id.

- Group size 1 → keep original `needId` and `quantity`.
- Group size N > 1 → one line: parent `needId`, `quantity` = N (duplicate
  count; 3 copies → `quantity: 3`), summed `lineTotal`, first item's
  equipment / daily rate / reason / matchScore.
- Items that are not unit-needs, or have no `equipment.id`, never merge.
- Same `equipment.id` on different parent needs never merge.
- Re-number `rankOrder` 1..n in first-seen group order.
- `confidenceScore` uses the collapsed list; `estimatedTotal` is already the
  pre-collapse sum of per-unit totals (unchanged).

## S — Structure

No new HTTP route or schema fields. Helper
`collapse_duplicate_equipment_quotes` lives in `app/services/session_recommend.py`
and is invoked from `map_recommend_to_quote`. Unit-need id convention stays in
`app/pipelines/expand_quantity.py`.

| Path | Role |
|------|------|
| `app/services/session_recommend.py` | Collapse helper + quote map |
| `app/schemas/recommend_quote.py` | Existing `quantity` / `needId` |
| `tests/test_quote_duplicate_collapse.py` | FR-P-013 scenarios |

## O — Operations

```bash
cd haystack-fast-api
uv run pytest tests/test_quote_duplicate_collapse.py tests/test_quote_asset_hydration.py tests/test_confidence_score.py tests/test_recommend_http_call2.py -q
```

## N — Norms

- RFC 2119 MUST/SHALL in FR-P-013.
- Quote-layer collapse MUST NOT put `quantity` on `RecommendationItem`.
- Parent extraction MUST use `{base}__u{i}`, not `split("_")`.
- Do not invent `equipment.id` or rates while collapsing (copy the first line).

## S — Safeguards

- Do not merge across parent needs.
- Do not drop a distinct `equipment.id` under the same parent.
- Do not change `estimatedTotal` arithmetic (still sum of unit line totals).
- Do not collapse on empty/missing `equipment.id`.
