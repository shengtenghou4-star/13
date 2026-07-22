from __future__ import annotations

import hashlib
import json
import math
import struct
from typing import Any, Mapping, Sequence

import numpy as np


HASH_SCHEMA = "houearth-canonical-float64-le-v1"


def _canonical_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "+Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, np.generic):
        return _canonical_json_value(value.item())
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, set):
        normalized = [_canonical_json_value(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    if hasattr(value, "value"):
        return _canonical_json_value(value.value)
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    normalized = _canonical_json_value(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_float64_bytes(values: np.ndarray | Sequence[float]) -> bytes:
    """Return platform-independent little-endian float64 bytes with canonical NaNs."""
    array = np.asarray(values, dtype=np.float64)
    canonical = np.ascontiguousarray(array.astype("<f8", copy=True))
    if np.any(np.isnan(canonical)):
        canonical[np.isnan(canonical)] = np.float64(np.nan)

    header = bytearray(HASH_SCHEMA.encode("ascii"))
    header.extend(b"\0")
    header.extend(struct.pack("<Q", canonical.ndim))
    for dimension in canonical.shape:
        header.extend(struct.pack("<Q", int(dimension)))
    return bytes(header) + canonical.tobytes(order="C")


def canonical_array_sha256(values: np.ndarray | Sequence[float]) -> str:
    return hashlib.sha256(canonical_float64_bytes(values)).hexdigest()


def lightcurve_array_hashes(
    time: np.ndarray,
    flux: np.ndarray,
    flux_err: np.ndarray | None,
) -> dict[str, str | None]:
    """Hash the exact analyzed arrays under an explicit canonical byte schema."""
    time_hash = canonical_array_sha256(time)
    flux_hash = canonical_array_sha256(flux)
    flux_err_hash = None if flux_err is None else canonical_array_sha256(flux_err)

    combined = hashlib.sha256()
    combined.update(HASH_SCHEMA.encode("ascii"))
    combined.update(b"\0time\0")
    combined.update(bytes.fromhex(time_hash))
    combined.update(b"\0flux\0")
    combined.update(bytes.fromhex(flux_hash))
    combined.update(b"\0flux_err\0")
    if flux_err_hash is None:
        combined.update(b"NONE")
    else:
        combined.update(bytes.fromhex(flux_err_hash))
    return {
        "schema": HASH_SCHEMA,
        "time_sha256": time_hash,
        "flux_sha256": flux_hash,
        "flux_err_sha256": flux_err_hash,
        "combined_sha256": combined.hexdigest(),
    }
