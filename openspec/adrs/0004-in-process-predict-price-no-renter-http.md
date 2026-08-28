# In-process `predict_price`; no public renter pricing HTTP

| Field | Value |
|-------|--------|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Deciders** | haystack-fast-api + pricing |
| **Trace** | dynamic-pricing US-1 / US-3 / US-4 / US-5 |

## Context and Problem Statement

How should recommendation and Spring checkout obtain a guardrail-clamped daily rate without exposing ML pricing to renters or duplicating model loaders?

## Considered Options

* Public `/predict-price` renter route
* Separate HTTP pricing microservice
* In-process `predict_price(...)` plus an internal-only quote route for Spring

## Decision Outcome

Chosen option: **in-process `app.services.pricing.model.predict_price`**.

- Pipeline / Call 2: `pricing_client.predict_price_for_asset`
- Agent tool `predict_asset_price` (US-5): same client
- Spring checkout: `POST /internal/v1/pricing/quote` (US-4) — not under public `/api/v1`, never renter-facing
- Haystack does **not** persist `mlPredictedPrice` (Spring owns that column)

### Consequences

* Good: one model loader; no renter auth surface for ML prices.
* Bad / accepted: recommend-time vs checkout-time prices can drift (`period_utilization` / `lead_time_days` are live).
