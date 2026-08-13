## ADDED Requirements

### Requirement: Phase 2d-iii candidate validation is a read-only, common-input comparison

The system SHALL provide a standalone validation command that directly loads
the current and v2 candidate pricing artifacts, evaluates both over the same
live-asset feature rows at 1/7/14/30 days, and scores both over the same
deterministic v2 holdout. It SHALL reuse the production feature schema and
production clamp formula. It MUST NOT replace or reload the serving artifacts.

#### Scenario: Candidate materially reduces realistic-duration clamping


- **GIVEN** all 27 live pricing assets and compatible current/candidate artifacts
- **WHEN** both models are evaluated over identical rows
- **THEN** at both 7 and 14 days the candidate clamp rate is at least 20
  percentage points below current
- **AND** the candidate clamp rate at each duration is no more than 50%

#### Scenario: Candidate accuracy is compared fairly


- **GIVEN** the Phase 2d-ii v2 dataset
- **WHEN** the deterministic trainer holdout (`seed=42`, `test_size=0.2`) is
  rebuilt
- **THEN** both models are scored on the exact same holdout rows
- **AND** the candidate MAE is no more than 5% worse than current
- **AND** the candidate R² is no more than 0.01 below current

#### Scenario: Formal gate inputs cannot be tuned

- **WHEN** the Phase 2d-iii formal comparison runs
- **THEN** it requires exactly 27 assets and durations 1/7/14/30
- **AND** it fixes `distance_km=20.0`, category-utilization fallbacks, and `lead_time_days=0.0`
- **AND** the CLI exposes no current/candidate artifact, data-path, asset-count, distance, or output override for the formal gate

#### Scenario: Candidate data provenance is verified

- **GIVEN** the ignored Phase 2d-ii v2 CSV
- **WHEN** candidate accuracy is evaluated
- **THEN** its SHA-256 is `3b2b79d28f42fe62e2971f48b055af0cabecadc3b5fb0b7463a58929766e2d05`
- **AND** its total/test row counts match `current_v2.json`
- **AND** the recomputed candidate MAE/RMSE/R² match `current_v2.json`
- **AND** a missing CSV reports the exact seed-42 regeneration command

#### Scenario: Validation does not promote the candidate


- **WHEN** Phase 2d-iii completes, whether the gate passes or fails
- **THEN** `model.pkl` and `current.json` are byte-for-byte untouched
- **AND** the command does not invoke `reload_model()`
- **AND** promotion remains a separate Phase 2e action
