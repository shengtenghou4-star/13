# Phase 0.9 blind real-campaign protocol

**Status:** implementation and synthetic validation  
**Real candidate state:** prohibited from public artifacts  
**Discovery claim:** none

## 1. Scope

Phase 0.9 connects the Phase 0.7 real-TESS calibration engine to the Phase 0.8
complete-event freeze. It is a three-target blind dry run, not a survey-wide search.

The predeclared null-eligible targets are:

- HD 10700;
- HD 20794;
- HD 69830.

AU Mic, TOI-700, and LHS 3844 remain injection-calibration targets only because they
are known transiting systems. They cannot supply an unmasked no-event null distribution.

## 2. Two-stage lock

The real campaign must run in two stages.

### Stage 1: campaign-input lock

Every eligible light curve is downloaded, cleaned, and fingerprinted before any event
search. The campaign lock freezes:

- the complete target manifest and its SHA-256;
- source commit and UTC freeze time;
- exact cleaned-array SHA-256 for every target;
- query and product-provenance SHA-256 values;
- the common search-duration family;
- flattening window and machine threshold;
- the 64 exact surrogate seeds;
- block length, gap factor, and surrogate method;
- every target excluded under the predeclared eligibility rule.

If any predeclared target fails to download or fingerprint, the entire lock aborts. A
partial target set must never proceed to search.

### Stage 2: machine-only search

Only after the complete campaign lock is written may the pipeline:

1. search dimming events and symmetric brightening controls;
2. generate 64 gap-aware, unmasked full-search surrogates per target;
3. derive a target-familywise empirical p-value for every machine dimming event;
4. retain the complete machine event stream;
5. reduce to one winner per campaign input;
6. apply the Phase 0.8 BH and matched-control gates;
7. freeze the candidate table and complete evidence package;
8. bind the campaign lock, raw search events, all surrogate trials, calibration receipts,
   and Phase 0.8 evidence into a Phase 0.9 campaign package;
9. independently recompute every event p-value, matched control, source index, and
   machine row from the raw package.

No plot, catalogue lookup, target familiarity, manual score, or astrophysical label may
enter either stage.

## 3. Closed evidence schemas

The campaign package, campaign lock, lock targets, excluded-target records, target
calibrations, machine events, surrogate trials, and calibration receipts are closed
schemas. Missing fields, undeclared fields, non-string keys, malformed hashes, invalid
UTC timestamps, repeated identities, or noncanonical ordering reject the package even
when an attacker recomputes every outer SHA-256.

Surrogate event counts, full-search maxima, and threshold-exceeded flags must be
algebraically consistent with the frozen 5-sigma machine threshold. Boolean values are
never accepted as integer counts. The independent validator derives machine rows from
the raw event and surrogate layers rather than trusting self-reported receipts.

## 4. Familywise calibration

Each real event is compared with all 64 surrogate full-search dimming maxima:

`p = (1 + number(null maximum >= event SNR)) / 65`.

A surrogate trial with no dimming maximum remains in the denominator as a
non-exceedance. It is never deleted to improve apparent resolution.

The minimum resolvable p-value is therefore `1/65`.

The null trials must have:

- seeds exactly 0 through 63;
- method `gap-aware-circular-moving-block-bootstrap`;
- block length exactly 0.5 days;
- gap factor exactly 3.5;
- no neutralized events or points;
- matching target and sector;
- at least one retained contiguous observing segment.

Any mismatch rejects the target calibration.

## 5. Brightening control

For each dimming event, the control duration is the available brightening duration
nearest to the event duration; deterministic ties choose the shorter duration. The
control statistic is the maximum brightening SNR at that duration.

If no brightening control exists, the event remains in the complete stream but receives
a missing-control exclusion under Phase 0.8. Missing evidence is not silently imputed.

## 6. Deterministic event identity

Dimming events are canonically ordered by:

1. center time;
2. duration;
3. descending SNR;
4. descending depth;
5. local point count;
6. direction.

The source event index is assigned only after this ordering. Reversing input order
cannot alter any derived machine row, winner, rank, or hash.

## 7. Privacy boundary

The repository containing this protocol is public. Therefore the real Phase 0.9 command:

- requires `--private-evidence-sink`;
- refuses GitHub Actions execution unless `HOU_PRIVATE_EVIDENCE_SINK=1`;
- has no public automatic real-data workflow;
- prints only aggregate counts and cryptographic commitments;
- stores event identities, times, depths, SNRs, ranks, raw surrogate trials, and exact
  candidate rows only in an access-controlled output location.

The public CI workflow runs synthetic fixtures only. Synthetic artifacts contain no
astronomical candidates.

## 8. Required private evidence

A valid private run retains:

- exact campaign-input CSV arrays;
- `campaign_lock.json`;
- raw dimming and brightening events;
- all 64 surrogate trials and summary per target;
- target calibration receipts;
- complete Phase 0.8 machine-event evidence;
- candidate table;
- the Phase 0.8 table and evidence validation reports;
- the independent Phase 0.9 campaign derivation validation report;
- private aggregate summary;
- source commit and all SHA-256 commitments.

## 9. Prohibited claims

Phase 0.9 does not establish:

- a new planet or transit discovery;
- astrophysical validation;
- survey-wide completeness or occurrence rates;
- a clean null for known transiting systems;
- independence among stars or systematics;
- permission to inspect or publish real candidate rows before the private freeze is
  complete and independently verified.
