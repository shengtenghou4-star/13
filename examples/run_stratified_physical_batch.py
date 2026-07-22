from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from houearth.io import download_tess_lightcurve
from houearth.physical_evaluation import (
    PhysicalInjectionTrial,
    run_physical_campaign,
    write_physical_outputs,
)
from houearth.real_evaluation import wilson_interval
from houearth.stratification import LightCurveStratum, classify_lightcurve
from houearth.surrogates import run_surrogate_null_campaign, write_surrogate_outputs


MANIFEST = Path("data/stratified_targets_v0.7.csv")
OUTPUT_ROOT = Path("outputs/stratified-physical-v0.7")
DEPTHS = (0.0001, 0.0002)
DURATIONS_DAYS = (0.08, 0.16)
IMPACT_PARAMETERS = (0.0, 0.6)
INJECTION_SEEDS = range(4)
SURROGATE_SEEDS = range(32)


def parse_sectors(value: str) -> int | list[int] | None:
    values = [int(item.strip()) for item in value.split(";") if item.strip()]
    if not values:
        return None
    return values[0] if len(values) == 1 else values


def pooled_rows(
    trials_with_strata: list[tuple[PhysicalInjectionTrial, LightCurveStratum]],
) -> list[dict[str, object]]:
    grouped: dict[
        tuple[str, str, str, float, float, float],
        list[PhysicalInjectionTrial],
    ] = defaultdict(list)
    for trial, stratum in trials_with_strata:
        key = (
            stratum.magnitude_bin,
            stratum.scatter_bin,
            stratum.crowding_bin,
            trial.depth,
            trial.duration_days,
            trial.impact_parameter,
        )
        grouped[key].append(trial)

    rows: list[dict[str, object]] = []
    for key, group in sorted(grouped.items()):
        magnitude, scatter, crowding, depth, duration, impact = key
        recovered = [trial for trial in group if trial.recovered]
        low, high = wilson_interval(len(recovered), len(group))
        snrs = [
            trial.recovered_snr
            for trial in recovered
            if trial.recovered_snr is not None
        ]
        margins = [
            trial.snr_above_matched_control
            for trial in recovered
            if trial.snr_above_matched_control is not None
        ]
        rows.append(
            {
                "magnitude_bin": magnitude,
                "scatter_bin": scatter,
                "crowding_bin": crowding,
                "depth": depth,
                "duration_days": duration,
                "impact_parameter": impact,
                "targets": len({trial.target for trial in group}),
                "trials": len(group),
                "recovered": len(recovered),
                "completeness": len(recovered) / len(group),
                "confidence_low": low,
                "confidence_high": high,
                "median_recovered_snr": (
                    None if not snrs else float(np.median(snrs))
                ),
                "median_snr_above_matched_control": (
                    None if not margins else float(np.median(margins))
                ),
            }
        )
    return rows


rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
status: list[dict[str, object]] = []
all_trials: list[tuple[PhysicalInjectionTrial, LightCurveStratum]] = []

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
        stage = "stratify"
        stratum = classify_lightcurve(lc)
        output.mkdir(parents=True, exist_ok=True)
        (output / "stratum.json").write_text(
            json.dumps(stratum.to_dict(), indent=2), encoding="utf-8"
        )

        stage = "physical-injection"
        null_screen, background, brightening, trials, cells = run_physical_campaign(
            lc,
            depths=DEPTHS,
            durations_days=DURATIONS_DAYS,
            impact_parameters=IMPACT_PARAMETERS,
            seeds=INJECTION_SEEDS,
        )
        write_physical_outputs(trials, cells, output)
        (output / "null_screen.json").write_text(
            json.dumps(null_screen.to_dict(), indent=2), encoding="utf-8"
        )
        (output / "background_dimming_events.json").write_text(
            json.dumps([event.to_dict() for event in background], indent=2),
            encoding="utf-8",
        )
        (output / "background_brightening_events.json").write_text(
            json.dumps([event.to_dict() for event in brightening], indent=2),
            encoding="utf-8",
        )

        stage = "red-noise-surrogates"
        surrogate_trials, surrogate_summary = run_surrogate_null_campaign(
            lc,
            seeds=SURROGATE_SEEDS,
            block_days=0.5,
            durations=(0.04, 0.08, 0.16),
            excluded_events=(*background, *brightening),
        )
        write_surrogate_outputs(surrogate_trials, surrogate_summary, output)
        all_trials.extend((trial, stratum) for trial in trials)
        status.append(
            {
                "target_id": target_id,
                "query": row["query"],
                "status": "completed",
                "intended_role": row["intended_role"],
                "stratum": stratum.to_dict(),
                "physical_trials": len(trials),
                "physical_recovered": sum(trial.recovered for trial in trials),
                "surrogate_trials": len(surrogate_trials),
                "surrogate_summary": surrogate_summary.to_dict(),
            }
        )
    except Exception as exc:
        output.mkdir(parents=True, exist_ok=True)
        failure = {
            "target_id": target_id,
            "query": row["query"],
            "status": "failed",
            "stage": stage,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        (output / "failure.json").write_text(
            json.dumps(failure, indent=2), encoding="utf-8"
        )
        status.append(failure)

pooled = pooled_rows(all_trials)
summary = {
    "experiment": "HOU-EARTH stratified physical-transit and red-noise pilot",
    "status": "calibration; not a discovery search or survey completeness claim",
    "injection_model": "quadratic-limb-darkened small-planet approximation",
    "surrogate_model": "event-neutralized circular moving-block bootstrap",
    "depths": DEPTHS,
    "durations_days": DURATIONS_DAYS,
    "impact_parameters": IMPACT_PARAMETERS,
    "injection_seeds": list(INJECTION_SEEDS),
    "surrogate_seeds": list(SURROGATE_SEEDS),
    "completed_targets": sum(item["status"] == "completed" for item in status),
    "failed_targets": sum(item["status"] == "failed" for item in status),
    "total_physical_trials": len(all_trials),
    "total_surrogate_trials": sum(
        int(item.get("surrogate_trials", 0))
        for item in status
        if item["status"] == "completed"
    ),
    "pooled_stratum_cells": pooled,
    "targets": status,
}
(OUTPUT_ROOT / "batch_summary.json").write_text(
    json.dumps(summary, indent=2), encoding="utf-8"
)
if pooled:
    with (OUTPUT_ROOT / "pooled_stratum_completeness.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pooled[0]))
        writer.writeheader()
        writer.writerows(pooled)
print(json.dumps(summary, indent=2))

if summary["completed_targets"] < 4:
    raise SystemExit("Fewer than four stratified targets completed")
