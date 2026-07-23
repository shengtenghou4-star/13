# Phase 0.12 real locked-input search result

## Status

The pre-registered Phase 0.12 real campaign completed against the exact sixty-four frozen multi-sector TESS inputs.

The result is a valid null campaign: no row passed the complete global screening rule. Thresholds were not relaxed, batches were not screened separately, and no candidate-level manual inspection occurred.

## Candidate-safe aggregate result

- real frozen targets: **64**
- deterministic execution batches: **4 × 16**
- frozen input CSV files: **64**
- network downloads during search: **0**
- gap-aware surrogate trials: **4,096**
- complete machine-event rows: **2,856**
- rows in the one global frozen candidate table: **62**
- globally screened in: **0**
- all rows unopened: **true**
- all rows astrophysically unclassified: **true**
- batchwise candidate tables: **false**
- one global Benjamini–Hochberg correction: **true**
- candidate details disclosed: **false**
- astronomical claim: **none**

## Integrity and validation

Every target completed under the restart-safe atomic checkpoint protocol. All sixty-four checkpoints and all four batch receipts were revalidated before aggregation. The complete event stream was then frozen once, globally.

Three independent serialized-evidence validators accepted the resulting package:

- frozen candidate-table validator;
- complete machine-event evidence validator;
- campaign-calibration evidence validator.

The private evidence package was encrypted with AES-256-GCM, using an RSA-4096 wrapped data key. The accepted envelope was independently decrypted; its authenticated archive hash, private manifest, every listed private file, and all three evidence validators were rechecked.

The machine-readable public archive is `results/phase0_12_real_search_public_archive.json`.

## Scientific interpretation

Zero globally screened-in rows is not a pipeline failure. It is the pre-registered result for this sixty-four-target cohort under the frozen search family, brightening controls, sixty-four gap-aware surrogate trials per target, and one global multiple-testing correction.

This result does not support weakening the thresholds or selecting a favorable batch after the fact. The next scientific step is to expand or redesign the target cohort and sensitivity study while preserving this null result as part of the project evidence chain.

## Privacy and claim boundary

This public archive contains only aggregate counts and cryptographic commitments. It does not disclose target identities, event times, depths, signal-to-noise values, calibrations, or candidate-level rows. No astronomical discovery claim is made.
