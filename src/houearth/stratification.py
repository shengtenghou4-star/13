from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import numpy as np

from .core import LightCurve


@dataclass(frozen=True)
class LightCurveStratum:
    target: str
    tess_magnitude: float | None
    magnitude_bin: str
    crowding: float | None
    crowding_bin: str
    robust_scatter_ppm: float
    scatter_bin: str
    point_to_point_scatter_ppm: float
    point_to_point_bin: str
    six_hour_scatter_ppm: float
    lag1_autocorrelation: float
    correlation_bin: str
    variability_to_point_ratio: float
    cadence_minutes: float
    cadence_bin: str
    sectors: str
    cameras: str
    ccds: str
    array_hash_schema: str | None
    analyzed_combined_sha256: str | None
    product_provenance_sha256: str | None
    query_provenance_sha256: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _product_values(lc: LightCurve, key: str) -> list[Any]:
    products = lc.metadata.get("product_provenance", [])
    if not isinstance(products, list):
        return []
    return [
        product[key]
        for product in products
        if isinstance(product, dict) and key in product
    ]


def _first_numeric(lc: LightCurve, key: str) -> float | None:
    for value in _product_values(lc, key):
        parsed = _finite_float(value)
        if parsed is not None:
            return parsed
    return None


def _joined_unique(values: list[Any]) -> str:
    cleaned = sorted({str(value) for value in values if value is not None and str(value)})
    return ";".join(cleaned) if cleaned else "unknown"


def _metadata_string(lc: LightCurve, key: str) -> str | None:
    value = lc.metadata.get(key)
    return value if isinstance(value, str) and value else None


def _array_hash_value(lc: LightCurve, key: str) -> str | None:
    hashes = lc.metadata.get("analyzed_array_hashes")
    if not isinstance(hashes, Mapping):
        return None
    value = hashes.get(key)
    return value if isinstance(value, str) and value else None


def _robust_sigma(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return 0.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    sigma = 1.4826 * mad
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = float(np.std(values))
    return max(0.0, sigma)


def magnitude_bin(tess_magnitude: float | None) -> str:
    if tess_magnitude is None:
        return "unknown"
    if tess_magnitude < 8:
        return "lt8"
    if tess_magnitude < 10:
        return "8to10"
    if tess_magnitude < 12:
        return "10to12"
    if tess_magnitude < 14:
        return "12to14"
    return "ge14"


def crowding_bin(crowding: float | None) -> str:
    if crowding is None:
        return "unknown"
    if crowding >= 0.95:
        return "clean"
    if crowding >= 0.80:
        return "mixed"
    return "crowded"


def scatter_bin(scatter_ppm: float) -> str:
    """Bin whole-light-curve variability amplitude, not pure measurement noise."""
    if scatter_ppm < 300:
        return "low"
    if scatter_ppm < 1000:
        return "moderate"
    return "high"


def point_to_point_bin(scatter_ppm: float) -> str:
    if scatter_ppm < 200:
        return "low"
    if scatter_ppm < 600:
        return "moderate"
    return "high"


def correlation_bin(lag1: float) -> str:
    magnitude = abs(lag1)
    if magnitude < 0.25:
        return "low"
    if magnitude < 0.65:
        return "moderate"
    return "high"


def cadence_bin(cadence_minutes: float) -> str:
    if cadence_minutes <= 3:
        return "2min"
    if cadence_minutes <= 12:
        return "10min"
    if cadence_minutes <= 25:
        return "20min"
    return "30min-plus"


def robust_scatter_ppm(lc: LightCurve) -> float:
    """Whole-light-curve robust amplitude, including astrophysical variability."""
    normalized = lc.normalized().flux
    return 1e6 * _robust_sigma(normalized)


def point_to_point_scatter_ppm(lc: LightCurve, gap_factor: float = 3.5) -> float:
    """Robust adjacent-cadence scatter proxy with large gaps excluded."""
    normalized = lc.normalized()
    time_delta = np.diff(normalized.time)
    valid = time_delta <= gap_factor * normalized.cadence
    differences = np.diff(normalized.flux)[valid]
    if len(differences) == 0:
        return 0.0
    return 1e6 * _robust_sigma(differences) / np.sqrt(2.0)


def six_hour_scatter_ppm(lc: LightCurve, bin_hours: float = 6.0) -> float:
    """Robust scatter of time-bin medians; a red-noise/variability descriptor.

    This is deliberately called a scatter proxy rather than CDPP: no transit whitening
    or mission-specific noise model is implied.
    """
    if bin_hours <= 0:
        raise ValueError("bin_hours must be positive")
    normalized = lc.normalized()
    bin_days = bin_hours / 24.0
    labels = np.floor((normalized.time - normalized.time[0]) / bin_days).astype(int)
    medians = np.array(
        [np.median(normalized.flux[labels == label]) for label in np.unique(labels)],
        dtype=float,
    )
    return 1e6 * _robust_sigma(medians)


def lag1_autocorrelation(lc: LightCurve, gap_factor: float = 3.5) -> float:
    normalized = lc.normalized()
    residual = normalized.flux - np.median(normalized.flux)
    valid = np.diff(normalized.time) <= gap_factor * normalized.cadence
    left = residual[:-1][valid]
    right = residual[1:][valid]
    if len(left) < 3 or np.std(left) <= 0 or np.std(right) <= 0:
        return 0.0
    value = float(np.corrcoef(left, right)[0, 1])
    return value if np.isfinite(value) else 0.0


def classify_lightcurve(lc: LightCurve) -> LightCurveStratum:
    """Assign transparent engineering strata and immutable evidence fingerprints."""
    tmag = _first_numeric(lc, "tessmag")
    crowding = _first_numeric(lc, "crowdsap")
    cadence_minutes = lc.cadence * 24.0 * 60.0
    raw_scatter = robust_scatter_ppm(lc)
    adjacent_scatter = point_to_point_scatter_ppm(lc)
    six_hour = six_hour_scatter_ppm(lc)
    lag1 = lag1_autocorrelation(lc)
    ratio = raw_scatter / max(adjacent_scatter, 1e-12)
    sectors = lc.metadata.get("sectors", [])
    sector_label = _joined_unique(
        list(sectors) if isinstance(sectors, (list, tuple)) else []
    )
    return LightCurveStratum(
        target=lc.target,
        tess_magnitude=tmag,
        magnitude_bin=magnitude_bin(tmag),
        crowding=crowding,
        crowding_bin=crowding_bin(crowding),
        robust_scatter_ppm=raw_scatter,
        scatter_bin=scatter_bin(raw_scatter),
        point_to_point_scatter_ppm=adjacent_scatter,
        point_to_point_bin=point_to_point_bin(adjacent_scatter),
        six_hour_scatter_ppm=six_hour,
        lag1_autocorrelation=lag1,
        correlation_bin=correlation_bin(lag1),
        variability_to_point_ratio=ratio,
        cadence_minutes=cadence_minutes,
        cadence_bin=cadence_bin(cadence_minutes),
        sectors=sector_label,
        cameras=_joined_unique(_product_values(lc, "camera")),
        ccds=_joined_unique(_product_values(lc, "ccd")),
        array_hash_schema=_array_hash_value(lc, "schema"),
        analyzed_combined_sha256=_array_hash_value(lc, "combined_sha256"),
        product_provenance_sha256=_metadata_string(lc, "product_provenance_sha256"),
        query_provenance_sha256=_metadata_string(lc, "query_provenance_sha256"),
    )
