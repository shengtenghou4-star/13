from __future__ import annotations

from pathlib import Path

import numpy as np

from .core import LightCurve


def download_tess_lightcurve(
    target: str,
    *,
    author: str | None = "SPOC",
    sector: int | list[int] | None = None,
) -> LightCurve:
    """Download and stitch public TESS light curves through Lightkurve/MAST."""
    try:
        import lightkurve as lk
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Real TESS downloads require the optional dependencies: "
            "python -m pip install -e '.[tess]'"
        ) from exc

    kwargs: dict[str, object] = {"mission": "TESS"}
    if author:
        kwargs["author"] = author
    if sector is not None:
        kwargs["sector"] = sector

    result = lk.search_lightcurve(target, **kwargs)
    if len(result) == 0 and author is not None:
        # A fallback across supported community products is better than silently failing.
        kwargs.pop("author", None)
        result = lk.search_lightcurve(target, **kwargs)
    if len(result) == 0:
        raise RuntimeError(f"No TESS light-curve products found for {target!r}")

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
    return LightCurve(
        time,
        flux,
        flux_err,
        target=target,
        metadata={
            "source": "MAST/TESS via Lightkurve",
            "author_filter": author,
            "sectors": sectors,
            "products": len(collection),
        },
    )


def save_lightcurve_csv(lc: LightCurve, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    err = lc.flux_err if lc.flux_err is not None else np.full(len(lc.time), np.nan)
    data = np.column_stack([lc.time, lc.flux, err])
    np.savetxt(path, data, delimiter=",", header="time_days,flux,flux_err", comments="")
