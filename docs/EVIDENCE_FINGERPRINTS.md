# HOU-EARTH evidence fingerprints

## Purpose

A target name, TESS sector, or archive filename does not uniquely identify the exact numeric arrays analyzed by a pipeline. Archive products can be reprocessed, download order can change, and software versions can alter stitching or normalization. HOU-EARTH therefore records cryptographic fingerprints for every campaign-input light curve used by the Phase 0.7 workflow.

A fingerprint proves identity of the stated bytes under the documented canonicalization. It does **not** prove that the data are scientifically correct, free of systematics, or astrophysically interpretable.

## Campaign-input semantics

The fingerprint is computed only after `LightCurve` construction has:

1. converted arrays to floating point;
2. removed non-finite time or flux values;
3. removed non-finite or non-positive uncertainties;
4. sorted all retained cadences by time.

The resulting arrays are the exact inputs entering target classification and the injection/recovery campaign.

The metadata key is deliberately named `campaign_input_array_hashes`. Derived curves produced by normalization, flattening, clipping, injection, or surrogate generation inherit this field as source provenance. It must not be interpreted as a hash of each derived array.

## Canonical array schema

Schema identifier:

```text
houearth-canonical-float64-le-v1
```

For each array, HOU-EARTH:

- converts values to contiguous little-endian IEEE-754 float64;
- canonicalizes every NaN payload to NumPy's standard NaN value;
- prefixes the byte stream with the schema identifier, rank, and every dimension;
- hashes the resulting bytes with SHA-256.

Separate hashes are retained for:

- `time`;
- `flux`;
- `flux_err`, or an explicit `NONE` sentinel;
- the combined ordered tuple of all three components.

The schema commits to shape as well as values. A vector and a matrix containing the same flattened numbers do not share a hash.

## Metadata fingerprints

HOU-EARTH also canonicalizes JSON-like metadata and hashes:

- the selected product provenance records;
- the full query and processing provenance.

The query provenance includes:

- target string;
- requested and used author filter;
- requested and downloaded sectors;
- product limit;
- product provenance;
- Python, NumPy, and Lightkurve versions;
- TESS quality bitmask;
- stitching corrector description.

JSON object key order does not affect the hash. Non-finite floating values are represented explicitly as `NaN`, `+Infinity`, or `-Infinity` strings before hashing.

## Evidence gate

A completed Phase 0.7 target is accepted only when its `stratum` contains:

- the exact supported hash schema;
- a valid 64-character lowercase campaign-input combined SHA-256;
- a valid product-provenance SHA-256;
- a valid query-provenance SHA-256.

Missing, malformed, or differently versioned fingerprints make the evidence package fail protocol validation. Failed targets may still retain diagnostic files, but they do not count toward the accepted-target threshold.

## Reproduction procedure

To reproduce a target fingerprint:

1. use the recorded query and software provenance;
2. download the selected products with the recorded quality bitmask;
3. apply the recorded per-product cleaning and normalization before stitching;
4. construct the HOU-EARTH `LightCurve`;
5. call `lightcurve_array_hashes` on the constructed arrays;
6. compare every component and combined SHA-256 with the evidence package.

A mismatch is not silently tolerated. It indicates different data, different preprocessing, different software behavior, or damaged evidence and must be investigated before comparing scientific results.

## Limitations

- SHA-256 establishes byte identity under this schema, not scientific validity.
- The schema intentionally distinguishes `+0.0` and `-0.0` because it preserves exact float64 bytes.
- Future canonicalization changes require a new schema identifier.
- Archive-side reproducibility can still be affected by unavailable historical products or software dependencies; the frozen evidence artifact remains the primary record.
