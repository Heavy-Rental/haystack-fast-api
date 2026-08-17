# REASONS Canvas: Phase 2e calibrated-model promotion

## Requirements

Promote only the candidate that passed Phase 2d-iii, retain a byte-exact v1
rollback, hot-reload the production singleton, and verify through the actual
`predict_price()` entrypoint.

## Entities

- **v1 rollback:** pre-promotion `model.pkl` and `current.json`.
- **v2 candidate:** reviewed `model_v2.pkl` and `current_v2.json`.
- **serving artifacts:** literal `model.pkl` and `current.json` consumed by
  `app.services.pricing.model`.
- **serving singleton:** module-level `_model` and `_model_version` refreshed by
  `reload_model()`.

## Approach

1. Record SHA-256 identities for the four pre-promotion artifacts.
2. Copy the serving pair to the v1 filenames; retain the v2 source pair.
3. Copy the v2 pair onto the serving filenames.
4. Assert source/destination and rollback/source byte identities.
5. Reload and exercise `predict_price()` rather than a direct pickle call.

Keeping both versioned pairs makes rollback explicit and avoids relying on Git
object recovery during an operational incident.

## Structure

No runtime module or API shape changes. The artifact directory gains
`model_v1.pkl` and `current_v1.json`; tests lock the four-generation identity
relationships and serving metadata version.

## Operations

Promotion is a reviewed one-time repository change. A running process must call
`reload_model()` or restart after deployment. Rollback reverses the copy:
v1 files become the serving pair, followed by the same reload and smoke checks.

## Norms

- Candidate and rollback versioned artifacts remain immutable.
- Serving filenames are the only filenames the runtime loader consumes.
- Model evaluation and artifact promotion stay separate actions.

## Safeguards

- Do not retrain during promotion.
- Do not modify the v2 candidate before or during the swap.
- Fail verification on any artifact hash mismatch, schema mismatch, non-finite
  prediction, guardrail breach, or unexpected model version.
- Keep excavator visible as the post-promotion residual clamp watch item.
