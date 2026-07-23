# Phase 0.10 private three-target blind run

**Status:** executor implementation and synthetic validation  
**Real candidate disclosure:** forbidden outside the private evidence sink  
**Discovery claim:** none

## Purpose

Phase 0.10 executes the first real blind search on the three predeclared null-eligible TESS targets:

- HD 10700;
- HD 20794;
- HD 69830.

AU Mic, TOI-700, and LHS 3844 remain explicit exclusions because they are known transiting systems. They continue to serve injection-calibration purposes only.

## Mandatory ordering

1. Read the exact six-target manifest and verify its columns and SHA-256.
2. Select exactly the three `unmasked-null` targets and freeze the three exclusions.
3. Download, clean, fingerprint, and provenance-check all three eligible light curves.
4. Abort the entire run if any target fails. No search and no partial output are permitted.
5. Write the campaign lock and exact input CSV files to the private sink.
6. Search dimming and symmetric brightening events with the Phase 0.9 frozen grid.
7. Run 64 gap-aware unmasked full-search surrogates per target.
8. Derive target-familywise p-values, freeze the complete machine-event stream, select one winner per campaign input, and apply BH and matched-control gates.
9. Independently validate the table, complete event evidence, and raw-to-machine campaign package.
10. Write a file-level SHA-256 manifest over all private evidence.

## Privacy guard

A real execution requires:

```text
HOU_PRIVATE_EVIDENCE_SINK=1
```

Inside GitHub Actions it additionally requires:

```text
HOU_PRIVATE_REPOSITORY_VISIBILITY=private
```

The executor rejects the repository root and any non-empty output directory. It creates no output directory before every target has been acquired and fingerprinted successfully.

The command prints only a candidate-safe aggregate receipt:

- number of targets;
- number of surrogate trials;
- number of machine events and frozen rows;
- number passing the blind screen;
- unopened/unclassified state;
- campaign, table, evidence, and package SHA-256 commitments;
- validation acceptance flags.

It never prints target-level event times, durations, depths, SNRs, ranks, candidate IDs, or raw surrogate trials.

## Command

```bash
python examples/run_phase10_private_real_campaign.py \
  --manifest data/stratified_targets_v0.7.csv \
  --private-evidence-sink /private/path/hou-earth-phase10 \
  --source-commit <40-character-public-source-commit>
```

Install the real-data dependencies first:

```bash
python -m pip install -e '.[dev,tess]'
```

## Required private files

A complete run retains:

- `campaign_lock.json`;
- three exact campaign-input CSV files;
- raw dimming and brightening event streams;
- all 192 surrogate trials and summaries;
- target calibration receipts;
- complete Phase 0.8 candidate evidence;
- the Phase 0.9 campaign evidence package;
- three independent validation reports;
- `PUBLIC_AGGREGATE_RECEIPT.json`;
- `PRIVATE_EVIDENCE_MANIFEST.json` with file-level hashes.

## Public boundary

The public repository may later receive only the aggregate receipt and cryptographic commitments. Candidate-level evidence stays private until an explicit, versioned unblinding decision is made after independent validation.
