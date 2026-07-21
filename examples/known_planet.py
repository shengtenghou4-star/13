"""Calibration example: recover a published planet from public TESS data.

Requires: python -m pip install -e '.[tess]'
"""

from houearth.io import download_tess_lightcurve
from houearth.search import search_periodic_transits

lc = download_tess_lightcurve("TOI 700")
candidate = search_periodic_transits(lc, min_period=1.0, max_period=50.0)
print(candidate)
