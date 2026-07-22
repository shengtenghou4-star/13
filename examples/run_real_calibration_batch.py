from __future__ import annotations

import csv
import json
from pathlib import Path

from houearth.io import download_tess_lightcurve
from houearth.real_evaluation import (
    RealInjectionTrial,
    run_real_lightcurve_campaign,
    write_real_campaign_outputs,
)
from houearth.real_reporting import pool_real_trials

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
all_trials: list[RealInjectionTrial] = []

for row in rows:
    target_id = row["target_id"]
    output = OUTPUT_ROOT / target_id
    stage = "download"
    try:
        lc = download_tess_lightcurve(
            row["query"],
            author=row["author"] or None,
            sector=parse_sectors(row["sectors"]),
            max_products=int(row["max_products"]),
        )
        stage = "screen-and-inject"
        null_screen, background, trials, cells = run_real_lightcurve_campaign(
            lc,
            depths=DEPTHS,
            durations_days=DURATIONS_DAYS,
            seeds=SEEDS,
        )
        stage = "write-evidence"
        write_real_campaign_outputs(
            lc,
            null_screen,
            background,
            trials,
            cells,
            output,
        )
        all_trials.extend(trials)
        status.append(
            {
                "target_id": target_id,
                "query": row["query"],
                "status": "completed",
                "role": row["role"],
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
            "stage": stage,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        (output / "failure.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        status.append(failure)

pooled = pool_real_trials(all_trials) if all_trials else []
summary = {
    "experiment": "HOU-EARTH first real TESS injection batch",
    "status": "calibration; not a discovery search",
    "depths": DEPTHS,
    "durations_days": DURATIONS_DAYS,
    "seeds": list(SEEDS),
    "completed_targets": sum(item["status"] == "completed" for item in status),
    "failed_targets": sum(item["status"] == "failed" for item in status),
    "pooled_cells": [cell.to_dict() for cell in pooled],
    "targets": status,
}
(OUTPUT_ROOT / "batch_summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
if pooled:
    with (OUTPUT_ROOT / "pooled_completeness.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pooled[0].to_dict()))
        writer.writeheader()
        writer.writerows(cell.to_dict() for cell in pooled)
print(json.dumps(summary, indent=2))

if not all_trials:
    raise SystemExit("No real TESS calibration target completed")
