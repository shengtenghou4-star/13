"""Recover pi Mensae c from TESS Sector 1 as the first real-data benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from houearth.io import download_tess_lightcurve
from houearth.search import search_periodic_transits

EXPECTED_PERIOD_DAYS = 6.26784
MAX_RELATIVE_ERROR = 0.02

lc = download_tess_lightcurve("Pi Mensae", author="SPOC", sector=1)
candidate = search_periodic_transits(
    lc,
    min_period=5.7,
    max_period=6.8,
    period_steps=240,
    durations=(0.08, 0.12, 0.16, 0.20),
)
relative_error = abs(candidate.period_days - EXPECTED_PERIOD_DAYS) / EXPECTED_PERIOD_DAYS

result = {
    "benchmark": "pi Mensae c / TESS Sector 1",
    "expected_period_days": EXPECTED_PERIOD_DAYS,
    "recovered": candidate.to_dict(),
    "relative_period_error": relative_error,
    "passed": relative_error <= MAX_RELATIVE_ERROR,
    "lightcurve": lc.to_dict(),
}
Path("outputs/pi-men-benchmark").mkdir(parents=True, exist_ok=True)
Path("outputs/pi-men-benchmark/result.json").write_text(
    json.dumps(result, indent=2), encoding="utf-8"
)
print(json.dumps(result, indent=2))
if not result["passed"]:
    raise SystemExit("pi Mensae benchmark failed the 2% period-error gate")
