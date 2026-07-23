# Phase 0.12 restart-safe atomic checkpoints

## Purpose

The Phase 0.12 real campaign contains sixty-four locked multi-sector targets and exactly sixty-four gap-aware surrogate trials per target. A complete run is therefore expensive enough that process or machine interruption must not force already completed targets to be recomputed.

This protocol adds restart safety without changing the scientific experiment. Checkpoints partition computation only. Candidate construction, multiple-testing correction, and final validation remain global and may occur only after all sixty-four target checkpoints and all four batch receipts validate.

## Target checkpoint boundary

A target counts as complete only after its checkpoint has been written atomically and immediately read back through the validator. Each checkpoint binds:

- exact search source commit;
- selection-lock, selection-campaign-lock, private-manifest, and locked-input-set hashes;
- immutable batch and ordinal identity;
- target, query, role, stratum, sector, and locked CSV identity;
- exact campaign-input array hash;
- complete machine-event rows;
- complete target calibration, including all frozen surrogate trials;
- surrogate summary;
- elapsed execution time;
- a canonical SHA-256 over the complete checkpoint body.

A valid checkpoint may be reused after interruption only when its own hash and every expected identity field are revalidated. A syntactically valid checkpoint belonging to another target, batch, input file, or source commit is rejected.

## Atomic persistence

The writer serializes to a process-specific temporary file, flushes and fsyncs the file, atomically replaces the destination, and fsyncs the containing directory. A partial JSON document or orphaned temporary file never counts as completed evidence.

## Batch receipts

Each deterministic batch requires exactly sixteen distinct target-checkpoint hashes in frozen order. The batch receipt is itself canonically hashed. Missing, duplicate, reordered after signing, foreign, or altered checkpoint sets are rejected.

## Global scientific boundary

Checkpoint files are not candidate tables. No batch may perform a separate Benjamini-Hochberg correction or disclose a batch winner. The final aggregator must:

1. validate the original frozen selection bytes;
2. validate all sixty-four target checkpoints against their original locked inputs;
3. validate all four batch receipts;
4. reject missing, duplicate, extra, or foreign checkpoints;
5. combine the complete machine-event stream;
6. freeze exactly one global candidate table;
7. apply exactly one global multiple-testing correction;
8. run the candidate-table, complete-event, and campaign-evidence validators;
9. keep every row unopened and unclassified until the entire package is accepted.

## Privacy boundary

The public repository contains only the checkpoint method and synthetic attack tests. Real target identities, machine events, calibrations, summaries, and candidate rows remain private. Persistent real checkpoint snapshots must be encrypted before leaving the private execution environment.

## Claim boundary

Passing this protocol proves restart-safe integrity and identity binding. It does not validate a candidate and makes no astronomical discovery claim.
