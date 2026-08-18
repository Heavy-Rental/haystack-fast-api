# Proposal: Phase 2e calibrated-model promotion

## Why

Phase 2d-iii proved that `model_v2.pkl` materially reduces production-guardrail
clamping and passes the common-holdout accuracy gate. The serving loader still
reads the Phase 1 `model.pkl`/`current.json`, so the validated improvement is not
yet available to recommendation or internal-pricing callers.

## Scope

- Preserve the current serving artifacts as immutable v1 rollback copies.
- Promote the validated v2 model and metadata to the literal serving filenames.
- Reload the in-process singleton and verify the real `predict_price()` path.
- Record artifact identities and the post-promotion residual excavator risk.

## Out of scope

- Retraining, recalibrating, or changing model features.
- Changing guardrail semantics or pricing API contracts.
- Phase 3 scheduled retraining and automatic promotion/rollback orchestration.

## Compatibility

The feature schema and API are unchanged. Only the model bytes and metadata
behind the existing serving filenames change. The v1 copies provide a direct
file-level rollback path.
