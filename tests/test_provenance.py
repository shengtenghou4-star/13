import struct

import numpy as np

from houearth.io import _fingerprinted_lightcurve
from houearth.provenance import (
    HASH_SCHEMA,
    canonical_array_sha256,
    canonical_json_sha256,
    lightcurve_array_hashes,
)


def test_array_hash_is_independent_of_native_endianness() -> None:
    little = np.array([1.0, 2.5, -3.0], dtype="<f8")
    big = np.array([1.0, 2.5, -3.0], dtype=">f8")
    assert canonical_array_sha256(little) == canonical_array_sha256(big)


def test_array_hash_canonicalizes_nan_payloads() -> None:
    standard = np.array([1.0, np.nan, 2.0], dtype=np.float64)
    payload_bits = np.array(
        [
            struct.unpack("<Q", struct.pack("<d", 1.0))[0],
            0x7FF8000000000001,
            struct.unpack("<Q", struct.pack("<d", 2.0))[0],
        ],
        dtype="<u8",
    )
    custom_payload = payload_bits.view("<f8")
    assert np.isnan(custom_payload[1])
    assert canonical_array_sha256(standard) == canonical_array_sha256(custom_payload)


def test_array_hash_commits_to_shape_and_values() -> None:
    vector = np.array([1.0, 2.0, 3.0, 4.0])
    matrix = vector.reshape(2, 2)
    changed = vector.copy()
    changed[-1] = 4.0000001
    assert canonical_array_sha256(vector) != canonical_array_sha256(matrix)
    assert canonical_array_sha256(vector) != canonical_array_sha256(changed)


def test_json_hash_is_key_order_independent_and_nonfinite_explicit() -> None:
    left = {"b": [1, float("nan")], "a": float("inf")}
    right = {"a": float("inf"), "b": [1, np.float64(np.nan)]}
    assert canonical_json_sha256(left) == canonical_json_sha256(right)
    assert canonical_json_sha256({"x": float("inf")}) != canonical_json_sha256(
        {"x": float("-inf")}
    )


def test_lightcurve_hashes_record_components_and_missing_uncertainty() -> None:
    time = np.array([1.0, 2.0, 3.0])
    flux = np.array([1.0, 0.999, 1.001])
    err = np.array([0.001, 0.001, 0.001])
    with_err = lightcurve_array_hashes(time, flux, err)
    without_err = lightcurve_array_hashes(time, flux, None)
    assert with_err["schema"] == HASH_SCHEMA
    assert len(str(with_err["combined_sha256"])) == 64
    assert with_err["flux_err_sha256"] is not None
    assert without_err["flux_err_sha256"] is None
    assert with_err["combined_sha256"] != without_err["combined_sha256"]


def test_fingerprint_commits_to_constructed_analyzed_arrays() -> None:
    time = np.arange(24.0)[::-1]
    flux = 1.0 + 0.0001 * np.arange(24.0)
    err = np.full(24, 0.001)
    flux[5] = np.nan
    err[11] = 0.0

    preconstruction_hash = lightcurve_array_hashes(time, flux, err)["combined_sha256"]
    lc = _fingerprinted_lightcurve(
        time,
        flux,
        err,
        target="fingerprint-fixture",
        metadata={"source": "fixture"},
    )
    expected = lightcurve_array_hashes(lc.time, lc.flux, lc.flux_err)
    stored = lc.metadata["analyzed_array_hashes"]

    assert len(lc.time) == 22
    assert np.all(np.diff(lc.time) > 0)
    assert stored == expected
    assert stored["combined_sha256"] != preconstruction_hash
