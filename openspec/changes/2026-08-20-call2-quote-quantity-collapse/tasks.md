# Tasks: Collapse duplicate Call 2 equipment quotes

- [x] Replace WIP `needId.split("_")` / `pop()` with `collapse_duplicate_equipment_quotes`.
- [x] Wire collapse into `map_recommend_to_quote` after items are built, before confidence.
- [x] Add `tests/test_quote_duplicate_collapse.py` (merge, 3-duplicate quantity, non-merge, mixed, mapper, underscore parent).
- [x] Record OpenSpec FR-P-013 (change delta + live recommendation-pipeline spec).
- [x] Record OpenSPDD REASONS (`design.md` in this change + live pipeline design).
- [x] Record ADR (`adr.md`).
- [x] Update Call 2 contract, TRACEABILITY, and quote field notes.
- [x] Run focused pytest (`test_quote_duplicate_collapse` + Call 2 / hydration / confidence).
