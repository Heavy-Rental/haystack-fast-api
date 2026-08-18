# Proposal: In-process agent tool `predict_asset_price` (S6 / Phase 6)

| Field | Value |
|-------|--------|
| **Status** | **Archived / as-built** (S6) |
| **Date** | 2026-08-12 |
| **Trace** | Dynamic pricing US-5; FR-020/022 (equipment-recommendation) |
| **Plan** | [`Feasibility_Study/implementation-plan.md`](../../../../Feasibility_Study/implementation-plan.md) Phase 6 / stage **S6** |
| **Study** | [`Feasibility_Study/ml-pricing-multi-agent.md`](../../../../Feasibility_Study/ml-pricing-multi-agent.md) P4 |
| **Tasks** | [`./tasks.md`](./tasks.md) |
| **Standards** | OpenSpec · Spec-kit · OpenSPDD · TDD/BDD |

## Why

Multi-agent recommend (Phase 7 Pricing Workers **[7]**) needs an allowlisted **in-process** pricing tool that shares the production model + per-asset clamp path with Call 2 MVP and the internal quote API — no invent rates, no silent zeros, no public price HTTP, no second loader.

Phase 1e / 2a / 2b / 2c were already production before this change; S6 only adds the agent-facing tool surface.

## What shipped

| Item | Behaviour |
|------|-----------|
| Tool name `predict_asset_price` | Stable contract for traces / future Workers |
| Function `predict_asset_price(...)` | Wraps `pricing_client.predict_price_for_asset` |
| Return shape | `daily_rate`, `total_price`, `currency`, `deposit_rate`, `was_clamped`, `model_version`, `explanation` (+ optional `asset_id` echo) |
| Silent zero guard | `daily_rate <= 0` → `ValueError` |
| Single SoT | Same entrypoint as `PredictPriceAdapter` / service recommend |
| Phase 7 graph | **Not wired** (tool only) |

## Spec / design

- `openspec/specs/dynamic-pricing/spec.md` — US-5 + scenarios + change control **2.9.0**
- `openspec/specs/dynamic-pricing/design.md` — consumers diagram
- `openspec/specs/equipment-recommendation/spec.md` — FR-020–022 as-built notes
- `openspec/specs/recommendation-pipeline/spec.md` — pricing source key decision
- `openspec/TRACEABILITY.md` — US-5 / S6 map
- Feasibility_Study implementation-plan **3.5.6** · ml-pricing study **1.2.2**

## Code

- `app/agents/tools.py` — `TOOL_PREDICT_ASSET_PRICE`, `predict_asset_price`
- `app/agents/__init__.py` — exports
- `tests/test_predict_asset_price_tool.py` — S6 pack

## Out of scope (follow-up)

- Phase 7 Pricing Workers [7]×N / recommend LangGraph fan-out
- Phase 2d model recalibration / promotion
- Manual retrain HTTP endpoint
- Changing `/internal/v1/pricing/quote` contract
