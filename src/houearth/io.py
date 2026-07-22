from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .core import LightCurve


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "value"):
        raw = value.value
        if isinstance(raw, np.generic):
            return raw.item()
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            return raw
    return str(value)


def download_tess_lightcurve(
    target: str,
    *,
    author: str | None = "SPOC",
    sector: int | list[int] | None = None,
    max_products: int | None = None,
) -> LightCurve:
    """Download and stitch public TESS light curves through Lightkurve/MAST."""
    try:
        import lightkurve as lk
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Real TESS downloads require the optional dependencies: "
            "python -m pip install -e '.[tess]'"
        ) from exc

    if max_products is not None and max_products < 1:
        raise ValueError("max_products must be positive when provided")

    kwargs: dict[str, object] = {"mission": "TESS"}
    if author:
        kwargs["author"] = author
    if sector is not None:
        kwargs["sector"] = sector

    result = lk.search_lightcurve(target, **kwargs)
    author_used = author
    if len(result) == 0 and author is not None:
        # A fallback across supported community products is better than silently failing.
        kwargs.pop("author", None)
        result = lk.search_lightcurve(target, **kwargs)
        author_used = None
    if len(result) == 0:
        raise RuntimeError(f"No TESS light-curve products found for {target!r}")
    if max_products is not None and len(result) > max_products:
        result = result[:max_products]

    collection = result.download_all(quality_bitmask="default")
    if collection is None or len(collection) == 0:
        raise RuntimeError(f"MAST returned no downloadable light curves for {target!r}")

    stitched = collection.stitch(
        corrector_func=lambda curve: curve.remove_nans().normalize()
    )
    time = np.asarray(stitched.time.value, dtype=float)
    flux = np.asarray(stitched.flux.value, dtype=float)
    flux_err = None
    if getattr(stitched, "flux_err", None) is not None:
        flux_err = np.asarray(stitched.flux_err.value, dtype=float)

    sectors = sorted(
        {
            int(getattr(curve, "sector"))
            for curve in collection
            if getattr(curve, "sector", None) is not None
        }
    )
    provenance_keys = (
        "MISSION",
        "SECTOR",
        "AUTHOR",
        "OBJECT",
        "TICID",
        "CAMERA",
        "CCD",
        "RA_OBJ",
        "DEC_OBJ",
        "TESSMAG",
        "CROWDSAP",
        "FLFRCSAP",
        "FILENAME",
        "EXPOSURE",
    )
    products: list[dict[str, Any]] = []
    for curve in collection:
        meta = dict(getattr(curve, "meta", {}) or {})
        product = {
            key.lower(): _json_scalar(meta[key])
            for key in provenance_keys
            if key in meta and meta[key] is not None
        }
        if getattr(curve, "sector", None) is not None:
            product.setdefault("sector", int(getattr(curve, "sector")))
        products.append(product)

    return LightCurve(
        time,
        flux,
        flux_err,
        target=target,
        metadata={
            "source": "MAST/TESS via Lightkurve",
            "author_filter_requested": author,
            "author_filter_used": author_used,
            "sectors": sectors,
            "products": len(collection),
            "product_provenance": products,
            "max_products": max_products,
        },
    )


def save_lightcurve_csv(lc: LightCurve, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    err = lc.flux_err if lc.flux_err is not None else np.full(len(lc.time), np.nan)
    data = np.column_stack([lc.time, lc.flux, err])
    np.savetxt(path, data, delimiter=",", header="time_days,flux,flux_err", comments="")
