from __future__ import annotations

import csv
import json
from pathlib import Path

from houearth.io import download_tess_lightcurve
from houearth.real_evaluation import run_real_lightcurve_campaign, write_real_campaign_outputs

MANIFEST = Path("data/real_calibration_targets.csv")
OUTPUT_ROOT = Path("outputs/real-calibration-batch")
DEPTHS = (0.004, 0.008)
DURATIONS_DAYS = (0.08, 0.16)
SEEDS = range(4)


def parse_sectors(value: str) -> int | list[int] | None:
    values = [int(item.strip()) for item in value.split(";") if item.strip()]
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values


rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
status: list[dict[str, object]] = []

for row in rows:
    target_id = row["target_id"]
    output = OUTPUT_ROOT / target_id
    try:
        lc = download_tess_lightcurve(
            row["query"],
            author=row["author"] or None,
            sector=parse_sectors(row["sectors"]),
            max_products=int(row["max_products"]),
        )
        null_screen, background, trials, cells = run_real_lightcurve_campaign(
            lc,
            depths=DEPTHS,
            durations_days=DURATIONS_DAYS,
            seeds=SEEDS,
        )
        write_real_campaign_outputs(
            lc,
            null_screen,
            background,
            trials,
            cells,
            output,
        )
        status.append(
            {
                "target_id": target_id,
                "query": row["query"],
                "status": "completed",
                "sectors": lc.metadata.get("sectors", []),
                "products": lc.metadata.get("products"),
                "cadences": len(lc.time),
                "background_events": null_screen.event_count,
                "cells": [cell.to_dict() for cell in cells],
            }
        )
    except Exception as exc:  # Batch provenance must retain failed targets too.
        output.mkdir(parents=True, exist_ok=True)
        failure = {
            "target_id": target_id,
            "query": row["query"],
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        (output / "failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        status.append(failure)

summary = {
    "experiment": "HOU-EARTH first real TESS injection batch",
    "status": "calibration; not a discovery search",
    "depths": DEPTHS,
    "durations_days": DURATIONS_DAYS,
    "seeds": list(SEEDS),
    "targets": status,
}
(OUTPUT_ROOT / "batch_summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
print(json.dumps(summary, indent=2))

completed = sum(item["status"] == "completed" for item in status)
if completed == 0:
    raise SystemExit("No real TESS calibration target completed")
