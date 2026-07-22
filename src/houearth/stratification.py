from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

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
    cadence_minutes: float
    cadence_bin: str
    sectors: str
    cameras: str
    ccds: str

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
    return [product[key] for product in products if isinstance(product, dict) and key in product]


def _first_numeric(lc: LightCurve, key: str) -> float | None:
    for value in _product_values(lc, key):
        parsed = _finite_float(value)
        if parsed is not None:
            return parsed
    return None


def _joined_unique(values: list[Any]) -> str:
    cleaned = sorted({str(value) for value in values if value is not None and str(value)})
    return ";".join(cleaned) if cleaned else "unknown"


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
    if scatter_ppm < 300:
        return "low"
    if scatter_ppm < 1000:
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
    normalized = lc.normalized().flux
    median = float(np.nanmedian(normalized))
    mad = float(np.nanmedian(np.abs(normalized - median)))
    return 1e6 * 1.4826 * mad


def classify_lightcurve(lc: LightCurve) -> LightCurveStratum:
    """Assign engineering strata from observed product metadata and scatter.

    These bins are calibration descriptors, not astrophysical classifications.
    """
    tmag = _first_numeric(lc, "tessmag")
    crowding = _first_numeric(lc, "crowdsap")
    cadence_minutes = lc.cadence * 24.0 * 60.0
    scatter = robust_scatter_ppm(lc)
    sectors = lc.metadata.get("sectors", [])
    sector_label = _joined_unique(list(sectors) if isinstance(sectors, (list, tuple)) else [])
    return LightCurveStratum(
        target=lc.target,
        tess_magnitude=tmag,
        magnitude_bin=magnitude_bin(tmag),
        crowding=crowding,
        crowding_bin=crowding_bin(crowding),
        robust_scatter_ppm=scatter,
        scatter_bin=scatter_bin(scatter),
        cadence_minutes=cadence_minutes,
        cadence_bin=cadence_bin(cadence_minutes),
        sectors=sector_label,
        cameras=_joined_unique(_product_values(lc, "camera")),
        ccds=_joined_unique(_product_values(lc, "ccd")),
    )
