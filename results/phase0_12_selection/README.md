# Phase 0.12 real multi-sector selection lock

## Status

The real Phase 0.12 selection and acquisition stage completed successfully on the exact validated HOU-EARTH source commit:

`9bd607924d65270922cb9a053f1cfa116eb1b858`

This stage performed catalog auditing, ranked target selection, multi-sector TESS acquisition, input fingerprinting, deterministic batch assignment, encryption, and independent private verification.

It deliberately performed **no transit search and no surrogate trial**. It therefore makes no astronomical discovery claim.

## Candidate-safe aggregate result

- 96 predeclared pool rows;
- 64 selected real multi-sector inputs;
- four strata with exactly 16 selected targets each;
- four deterministic batches with exactly 16 targets each;
- 238 downloaded TESS products;
- 201 distinct sector appearances;
- at least two products and two distinct sectors for every selected target;
- 64 frozen campaign-input CSV files;
- 70 files covered by the private evidence manifest;
- zero searches and zero surrogate trials;
- zero candidate-level disclosure.

The 32 nonselected pool rows consisted of 13 hard exclusions and 19 unused fallbacks after their stratum quota had already been filled. The hard exclusions included confirmed transiting hosts and inputs that failed the frozen multi-product or multi-sector requirements.

## Cloud and cryptographic identity

- temporary public harness commit: `c9f9c4710887e4760e296e2a89b12a9b4d446524`;
- workflow run: `30010659771`;
- job: `89217589613`;
- encrypted artifact: `8565277714`;
- artifact ZIP SHA-256: `b6a7f0294e38aec283c34cf73df26ef293327eb8dff89ca11819e41a465c52d5`;
- ciphertext SHA-256: `e6dbef6269a138c22ccdb1dc717fde05a8ca9e961f98c49a2436ebfca2bd4b81`;
- authenticated plaintext archive SHA-256: `e743d44cf2ad485f9d686157ea86b7113812cbedda003fbd98bceda333a33daa`;
- private manifest SHA-256: `18c3b351fa24600ef8b8f68a2633fe4869c582a1f5f33649b913b953a4aee096`;
- selection lock SHA-256: `fa33ec95129e77e1b6a50bb1d58ebd094b7e465a86a74f50bae2bd3bf5a8658f`;
- campaign lock SHA-256: `6681a7f1890d124d12f78b00028978dc2084ef55eb70c34d9bd6bad6e7fe351c`.

The matching RSA-4096 private key and authenticated-decryption ledger remain only on the isolated private evidence branch in repository #22. The private ledger is frozen at commit:

`68af286d5b8f20d5fb4e500b98a56e9028c897cb`

## Next gate

The subsequent search must consume these exact 64 frozen CSV byte streams and reproduce their committed campaign-input hashes. Re-downloading TESS data is not an acceptable substitute. All four batches must still feed one global candidate table and one global multiple-testing correction.
