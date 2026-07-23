# Phase 0.11 real ranked-pool campaign receipt

This directory contains candidate-safe public commitments for the completed Phase 0.11 real campaign.

The real run used the frozen 18-object ranked pool and selected exactly four eligible targets in each of three strata before any search. All twelve first-ranked quota positions were usable, so no fallback target was required.

Validated aggregate result:

- 12 selected targets;
- 768 gap-aware surrogate trials;
- 127 complete dimming machine events;
- 12 frozen target-level candidate rows;
- 0 rows passed the blind screen;
- all rows remained unopened and astrophysically unclassified;
- table, complete-event, and raw-to-machine campaign validators all accepted with zero errors.

The complete candidate-level evidence is not stored in this public repository. It was encrypted on the compute runner with AES-256-GCM, with the content key wrapped by a Phase 0.11 RSA-4096 public key. Public-compute checks proved that plaintext evidence was deleted before artifact upload. Authenticated decryption and all 28 private-manifest file hashes were independently verified using the matching private key stored only in the isolated private evidence branch.

This is a valid null campaign result and makes no astronomical discovery claim. The thresholds were not changed after seeing the outcome.
