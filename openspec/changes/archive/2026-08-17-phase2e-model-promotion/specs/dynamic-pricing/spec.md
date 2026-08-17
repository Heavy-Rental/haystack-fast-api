## ADDED Requirements

### Requirement: Phase 2e promotion is recoverable and identity-verifiable

The system SHALL preserve the pre-promotion serving model and metadata as v1
rollback artifacts before the validated Phase 2d candidate becomes the serving
artifact. After promotion, the serving model and metadata SHALL be byte-for-byte
identical to the validated v2 candidate artifacts.

#### Scenario: Promotion preserves both generations

- **GIVEN** the Phase 2d-iii gate passed for `model_v2.pkl` and `current_v2.json`
- **WHEN** Phase 2e promotes the candidate
- **THEN** the former `model.pkl` and `current.json` bytes are preserved as `model_v1.pkl` and `current_v1.json`
- **AND** `model.pkl` and `current.json` match `model_v2.pkl` and `current_v2.json` byte-for-byte
- **AND** the versioned v1 and v2 artifacts remain available for audit and rollback

### Requirement: Phase 2e verifies the production prediction path

The system SHALL reload the promoted serving artifacts through the production
model loader and SHALL verify predictions through `predict_price()`, including
all supported categories and the documented excavator watch case. Verification
SHALL confirm finite positive predictions, per-asset guardrail enforcement, and
the promoted metadata version.

#### Scenario: Hot reload activates the promoted model

- **WHEN** `reload_model()` runs after promotion
- **THEN** a new model object is loaded from the serving filenames
- **AND** returned predictions report the promoted `trained_at` date as their model version

#### Scenario: Serving smoke uses real prediction behavior

- **WHEN** the promoted model is exercised through `predict_price()` for supported categories and representative 1/7/14/30-day windows
- **THEN** every raw prediction is finite and positive
- **AND** every returned daily rate remains within its supplied per-asset guardrail bounds
- **AND** the excavator result is explicitly included in the verification report
