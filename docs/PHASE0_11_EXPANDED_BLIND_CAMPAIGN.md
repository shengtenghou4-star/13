# Phase 0.11 ranked-pool blind expansion

**Status:** protocol implementation and synthetic validation  
**Real candidate disclosure:** forbidden outside the encrypted/private evidence route  
**Discovery claim:** none

## Purpose

Phase 0.11 expands the successful three-target Phase 0.10 dry run to twelve new TESS targets without allowing manual replacement after any search result is seen.

The input is an 18-object ranked pool frozen before execution. It contains three strata with six ordered targets each:

- solar analogs;
- known radial-velocity hosts with no confirmed transiting planet;
- active, debris-disk, or otherwise harder controls.

Exactly the first four eligible targets in each stratum are selected. Later-ranked objects are used only when an earlier object is blocked by the catalog audit, has no downloadable TESS product, or fails the fixed minimum data-availability gates.

## Pre-search ordering

1. Hash and validate the exact 18-row ranked pool.
2. Download a complete default-row snapshot of the NASA Exoplanet Archive Planetary Systems table.
3. Match every pool object against its frozen aliases.
4. Exclude any object associated with a confirmed planet whose transit flag is one.
5. Within each stratum, inspect candidates strictly by frozen rank.
6. Accept the first four objects satisfying all fixed data-availability gates:
   - at least 500 cleaned cadences;
   - at least 10 days of baseline;
   - median cadence no longer than 0.1 day.
7. Abort before creating output or running any search unless all three four-object quotas are filled.
8. Freeze the pool hash, NASA snapshot hash, catalog audit, every selection/rejection decision, and all selected light-curve fingerprints.
9. Only then run the unchanged Phase 0.9 search, brightening control, 64-surrogate calibration, complete event freeze, BH screen, and three independent validators.

No target may be replaced because its light curve looks uninteresting or because another target appears more promising.

## Frozen statistical method

Phase 0.11 does not change the scientific thresholds:

- the same six duration windows;
- minimum machine-search SNR 5;
- 64 gap-aware unmasked surrogates per target;
- empirical target-familywise p-values with denominator 65;
- the same duration-matched brightening control;
- the same blind candidate-table and BH rules;
- complete machine-event preservation;
- all rows unopened and unclassified until the campaign package validates.

For twelve selected targets, the campaign must contain exactly 768 surrogate trials.

## Real command

```bash
HOU_PRIVATE_EVIDENCE_SINK=1 \
python examples/run_phase11_private_real_campaign.py \
  --pool data/phase11_expanded_target_pool.csv \
  --private-evidence-sink /private/path/hou-earth-phase11 \
  --source-commit <40-character-public-source-commit>
```

Public compute may be used only through the encrypted-envelope route established in Phase 0.10. Candidate-level plaintext must be deleted before artifact upload. The public receipt may expose counts and cryptographic commitments only.

## Required evidence

A complete private run retains:

- the frozen 18-row pool;
- raw NASA Planetary Systems snapshot and audit;
- Phase 0.11 selection lock;
- Phase 0.9-compatible campaign lock;
- twelve exact campaign-input CSV files;
- all dimming and brightening event streams;
- all 768 surrogate trials;
- complete candidate evidence and campaign evidence;
- three independent validation reports;
- candidate-safe aggregate receipt;
- file-level private evidence manifest.
