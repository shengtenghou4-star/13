# Phase 0.8 permanent synthetic evidence receipt

This directory permanently archives the compact synthetic evidence produced by the final cloud validation of HOU-EARTH Phase 0.8.

- Validated source head: `3cfa022cfdbc596b5f9ac0f77bde766e7371bf92`
- Squash-merged main commit: `794734dd0617914a8912764d92dd6776e185c4a5`
- GitHub Actions run: `29987070104`
- Artifact ID: `8555447551`
- Artifact ZIP SHA-256: `da3d9ab108f4a8fd7ce79122d5b783b74a30d91428bb515ead4bed5429261b93`
- Machine-event SHA-256: `a06b94ea6b5195678154cde7316b57a53bbee2ae90cbfcec170d20ffdd163409`
- Candidate-table SHA-256: `09ac4d9e07713188d4851e8ab987980976d61d853be9be238fd610893d1818e8`
- Evidence-package SHA-256: `0530bf5a139141d05b117af2a8a1f12051e606a003e3937637ee5d43b32ed6fe`

The fixture contains four synthetic machine events reduced to three campaign rows. Two rows are screened in and one is screened out. Every row remains `manual_review_status = unopened` and `astrophysical_status = unclassified`. Both the in-memory and serialized independent validators accepted the package with zero errors.

This is methodology evidence only. It contains no real astronomical candidate and supports no discovery claim. The archival commit stores evidence generated from the validated source head; it does not claim that the later archival commit itself was the source under test.
