# Tasks: S4 live SQL fleet backend

## Code

- [x] TDD: `tests/test_fleet_repository.py` (name→asset_id, empty [], live-hold overlap, cancelled ignored, free-form reject, fake default)
- [x] `app/repositories/fleet_repository.py` + `Asset.name`
- [x] `LiveSqlFleetBackend` + factory `session=`
- [x] `FLEET_BACKEND` + conftest force fake
- [x] `run_recommend_graph` owns a Session when flag is sql
- [x] Regression: `uv run pytest tests/` (302 passed, 3 skipped)

## Docs

- [x] D0 `fleet-read-contract.md` + this archive
- [x] OpenSpec equipment-recommendation + TRACEABILITY + AGENTS
- [x] Feasibility_Study implementation-plan, README, dual-plane, C/W/D
- [x] CHANGELOG Unreleased

## Config T0–T2 (stamp)

- [x] Record pack `develop` T0–T2 as-built (60s, allowlist, METRICS)
- [x] Document table-name alignment follow-up (singular pack vs plural haystack ORM)

## Explicit non-goals

- [ ] Change config-repo compose/scripts from this workspace
- [ ] Flip Call 2 graph default
- [ ] S8 live Neo4j
