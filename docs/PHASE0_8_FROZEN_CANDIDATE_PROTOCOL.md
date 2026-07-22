# Phase 0.8 frozen blind-candidate protocol

**Status:** development protocol; no real candidate table has been produced  
**Scientific claim level:** candidate-selection methodology only  
**Discovery claim:** none

## 1. Purpose

Phase 0.8 prevents post-selection bias between machine detection and human vetting.
The central rule is:

> The complete machine-ranked candidate table, its thresholds, source commit, input
> fingerprints, and SHA-256 commitment must be frozen before any candidate image,
> target identity context, catalogue cross-match, or astrophysical interpretation is
> inspected by a human reviewer.

A frozen row is an event requiring vetting. It is not a planet candidate in the
astrophysical-confirmation sense and is never a discovery claim by itself.

## 2. Permitted pre-freeze information

Only machine-produced fields declared in `BlindCandidateInput` may enter selection:

- target and campaign identifiers required for reproducibility;
- sector label and event time;
- winning duration, depth, and search SNR;
- target-level empirical familywise p-value;
- duration-matched brightening-control SNR and margin;
- campaign-input array SHA-256;
- the single frozen search-duration family;
- source event index.

The table builder does not accept human notes, plot classifications, catalogue labels,
known-planet status, target fame, spectral type, habitability language, or a manual
priority score.

## 3. Target-level reduction

The input event stream may contain multiple dimming events from one campaign-input light
curve. Before table-wide multiplicity correction, each `(target_id,
campaign_input_sha256)` pair is reduced to exactly one event under this fixed order:

1. lower target-familywise empirical p-value;
2. larger SNR margin over the duration-matched brightening control;
3. larger detection SNR;
4. larger measured depth;
5. earlier event time;
6. lower source event index.

This reduction prevents a noisy target with many reported local peaks from receiving
more table-wide opportunities than a quiet target.

## 4. Multiplicity and blind screen

The retained target-level p-values are adjusted with the Benjamini-Hochberg procedure.
The default frozen gates are:

- target-level familywise p-value `<= 0.05`;
- table-level Benjamini-Hochberg q-value `<= 0.10`;
- strictly positive SNR margin above the matched brightening control.

A row failing any gate remains in the frozen table as `screened-out`, with explicit
machine-generated exclusion reasons. Rows are never silently deleted.

The BH layer is a project-level screening device, not proof of independence among
stars, sectors, or instrumental systematics. Dependence sensitivity remains a later
analysis gate.

## 5. Frozen order

Rows are ordered without human input:

1. screened-in rows before screened-out rows;
2. lower BH q-value;
3. lower familywise p-value;
4. larger matched-control margin;
5. larger SNR;
6. deterministic target and event-time tie breaks.

The resulting `blind_priority_rank` is the only permitted order for the first human
inspection pass.

## 6. Freeze evidence

Every table records:

- schema version;
- immutable source Git commit;
- explicit UTC freeze timestamp;
- both statistical thresholds;
- human-readable selection and ranking rules;
- deterministic candidate IDs;
- the complete screened-in and screened-out row set;
- `manual_review_status = unopened`;
- `astrophysical_status = unclassified`;
- canonical table SHA-256.

The canonical hash covers every field except the hash field itself. List/tuple
serialization differences are normalized by the repository's canonical JSON encoder.

## 7. Independent validation

`validate_frozen_candidate_table` independently recomputes:

- deterministic candidate IDs;
- one-row-per-campaign uniqueness;
- sequential blind ranks;
- the common search-duration family;
- BH q-values;
- machine exclusion reasons and blind status;
- frozen row ordering;
- unopened/unclassified human-state fields;
- the full table SHA-256.

A rehashed but methodologically altered table is rejected. This matters because a valid
checksum alone only proves internal consistency, not compliance with the frozen method.

## 8. Human review sequence

Only after the table and validation report are frozen may reviewers:

1. inspect light-curve plots in blind rank order;
2. examine neighboring pixels and centroid diagnostics;
3. query known planets, eclipsing binaries, variable stars, and contamination catalogues;
4. assign structured vetoes or follow-up priorities;
5. append a separate post-freeze review layer.

The original table is immutable. Manual annotations must be stored separately and keyed
by `candidate_id`.

## 9. Corrections and amendments

A software or evidence error discovered after freeze must not be edited in place.
Instead:

1. retain the original table and validation report;
2. document the defect and affected rows;
3. increment the schema or protocol version;
4. rerun the complete machine pipeline from frozen inputs;
5. issue a new table hash and explicit supersession record;
6. restart blind review for any newly introduced or reordered rows.

## 10. Prohibited interpretations

Phase 0.8 does not establish:

- a new exoplanet discovery;
- astrophysical validation of a transit-like event;
- universal control of false discovery under arbitrary dependence;
- survey-wide TESS occurrence rates or completeness;
- immunity from catalogue, aperture, centroid, binary, or stellar-variability false
  positives.

It creates an auditable boundary between machine selection and human interpretation.
