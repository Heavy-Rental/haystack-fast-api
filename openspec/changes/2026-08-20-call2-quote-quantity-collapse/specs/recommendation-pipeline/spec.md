## ADDED Requirements

### Requirement: Collapse duplicate Call 2 equipment quotes (FR-P-013)

Call 2 quote `items[]` SHALL fold unit-need siblings that share parent need id
and catalog `equipment.id` into one commercial line. Parent need id is the
`{base}` of a `{base}__u{i}` unit-need id (quantity expansion). Internal
`results_by_need` and `RecommendationItem` MUST remain expanded and MUST NOT
gain a `quantity` field.

A merged line SHALL:

- set `needId` to the parent `{base}`
- set `quantity` to the number of grouped duplicates (the sum of grouped
  line quantities; Call 2 emits `quantity=1` per unit-need, so 3 copies →
  `quantity: 3`)
- set `lineTotal` to the sum of non-null grouped line totals (`null` if all
  grouped totals are null)
- keep the first item's `equipment`, `mlPredictedPrice`, `matchScore`, and
  `reason` (daily rate is not multiplied)
- re-number `rankOrder` 1..n in first-seen group order

Lines MUST NOT merge when equipment ids differ, when parent needs differ, when
the need id is not a unit-need, or when `equipment.id` is missing/empty.
`estimatedTotal` SHALL remain the pre-collapse sum of per-unit line totals.
`confidenceScore` SHALL be computed on the collapsed item list.

#### Scenario: Same parent and same equipment collapse

- **GIVEN** quote lines `need_1__u1` and `need_1__u2` with the same `equipment.id`
- **WHEN** Call 2 maps `results_by_need` to the quote envelope
- **THEN** `items[]` contains one line
- **AND** `needId` is `need_1`
- **AND** `quantity` is 2
- **AND** `lineTotal` is the sum of the two unit line totals
- **AND** `mlPredictedPrice` remains the first line's daily rate

#### Scenario: Three duplicates collapse to quantity 3

- **GIVEN** quote lines `need_1__u1`, `need_1__u2`, and `need_1__u3` with the same `equipment.id`
- **WHEN** Call 2 maps `results_by_need` to the quote envelope
- **THEN** `items[]` contains one line
- **AND** `needId` is `need_1`
- **AND** `quantity` is 3
- **AND** `lineTotal` is the sum of the three unit line totals

#### Scenario: Distinct equipment under the same parent stay separate

- **GIVEN** quote lines `need_1__u1` and `need_1__u2` with different `equipment.id`
- **WHEN** Call 2 maps to the quote envelope
- **THEN** both lines remain
- **AND** each keeps `quantity` 1 and its original `needId`

#### Scenario: Same equipment on different parent needs does not merge

- **GIVEN** quote lines `need_access` and `need_earthwork` with the same `equipment.id`
- **WHEN** Call 2 maps to the quote envelope
- **THEN** both lines remain with `quantity` 1

#### Scenario: Quantity-one need is unchanged

- **GIVEN** a single quote line `need_1` with `quantity` 1
- **WHEN** Call 2 maps to the quote envelope
- **THEN** the line is unchanged except `rankOrder` re-numbering

#### Scenario: Parent extraction does not split on underscore

- **GIVEN** quote lines `need_soft_clay__u1` and `need_soft_clay__u2` with the same `equipment.id`
- **WHEN** Call 2 maps to the quote envelope
- **THEN** the merged `needId` is `need_soft_clay`
