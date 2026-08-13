# REASONS Canvas: Phase 2d-iii candidate validation

## R — Requirements

- Read every current live asset through the pricing schema resolver.
- Evaluate current and candidate models over identical 1/7/14/30-day rows.
- Reuse production `feature_schema.build_features()` and production clamp math.
- Evaluate accuracy on the same v2 holdout (`seed=42`, `test_size=0.2`).
- Report a deterministic pass/fail gate without promoting the candidate.
- Lock the formal artifact/data identities and comparison inputs to 27 assets, 20 km, production category-utilization fallbacks, zero lead time, and the ignored chart path.
- Verify the ignored v2 CSV by SHA-256, row counts, and recomputed candidate metrics.

## E — Entities

- Live asset pricing attributes: category, condition, capacity,
  platform-height, minimum and maximum daily rates.
- Model artifacts: current `model.pkl`/`current.json`; candidate
  `model_v2.pkl`/`current_v2.json`.
- Candidate data: `synthetic_pricing_data_v2.csv`.
- Results: per-asset raw/clamped predictions, duration summaries, common
  holdout metrics, gate decision, comparison chart.

## A — Approach

Build one raw validation dataframe and one production feature matrix, then pass
that same matrix to both directly loaded models. Clamp each raw prediction with
`min(max(raw_price, min_daily_rate), max_daily_rate)`, exactly as
`app/services/pricing/model.py` does.

For accuracy, recreate the production trainer's deterministic v2 holdout and
score both models on those exact rows. Comparing the metadata MAEs directly is
not a fair gate because the v1 and v2 metadata were measured against differently
scaled targets; metadata remains provenance, while the common holdout is the
decision input.

## S — Structure

```text
ml-experiments/candidate_validation_check.py
tests/test_candidate_validation_check.py
ml-experiments/outputs/phase2d/candidate_validation_check.png  # ignored
```

## O — Operations

```bash
uv run python ml-experiments/generate_synthetic_data.py \
  --output ml-experiments/data/phase2d/synthetic_pricing_data_v2.csv \
  --plots-dir ml-experiments/outputs/phase2d --strict
uv run pytest tests/test_candidate_validation_check.py -q
uv run python ml-experiments/candidate_validation_check.py
```

The live command needs the same read-only database access as Phase 2d-i. The regeneration command is deterministic (`seed=42` by default); validation accepts only the expected candidate CSV SHA-256 and metadata-consistent row counts and metrics.

## N — Norms

- Current and candidate models receive identical feature rows.
- Production feature encoding is the single source of truth.
- The live asset count and observed current clamp rate are printed explicitly.
- A non-passing gate is a valid validation result, not a script failure.

## S — Safeguards

- Fail validation on artifact-schema mismatch, missing or provenance-mismatched candidate data, empty assets, or invalid guardrails; an asset count other than the expected Phase 2d fleet size (27) fails the formal gate.
- Never import/call the serving model loader for candidate selection.
- Never write to artifact paths or the database.
- Phase 2e remains a deliberate follow-up even when the gate passes.

## Gate thresholds

For each realistic duration (7 and 14 days):

- candidate clamp rate is at least 20 percentage points below current; and
- candidate clamp rate is no more than 50%.

On the common v2 holdout:

- candidate MAE is no more than 5% worse than current; and
- candidate R² is no more than 0.01 below current.

All six metric checks and the 27-asset completeness check must pass.
