"""Productionized dynamic-pricing service (Phase 2a).

Ports `ml-experiments/`'s validated Phase 1b/1d model + feature schema into a
real package, adds real per-asset guardrail clamping (`Asset.minDailyRate`/
`maxDailyRate`, not the ml-experiments static per-category stand-in), and
fixes the `AssetCategory.name` <-> `feature_schema.CATEGORIES` naming
mismatch found 2026-08-11. See openspec/specs/dynamic-pricing/{spec,design}.md.
"""
