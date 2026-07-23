from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from houearth.core import LightCurve, SingleTransitEvent
from houearth.private_campaign import run_phase10_private_campaign
from houearth.surrogates import GAP_AWARE_METHOD, SurrogateSummary, SurrogateTrial


FROZEN_AT = "2026-07-23T08:00:00Z"


def _manifest(path: Path) -> None:
    path.write_text(
        "target_id,query,author,sectors,max_products,intended_role,surrogate_policy,notes\n"
        "hd-10700,HD 10700,SPOC,,1,bright-low-scatter,unmasked-null,synthetic\n"
        "hd-20794,HD 20794,SPOC,,1,bright-reference,unmasked-null,synthetic\n"
        "hd-69830,HD 69830,SPOC,,1,bright-hard,unmasked-null,synthetic\n"
        "au-mic,AU Mic,SPOC,,1,active,skip-known-transits,known transit\n"
        "toi-700,TOI 700,SPOC,,1,mid,skip-known-transits,known transit\n"
        "lhs-3844,LHS 3844,SPOC,,1,faint,skip-known-transits,known transit\n",
        encoding="utf-8",
    )


def _lightcurve(query: str, index: int) -> LightCurve:
    time = np.linspace(0.0, 3.0, 240)
    return LightCurve(
        time,
        np.ones_like(time),
        np.full_like(time, 0.0001),
        target=query,
        metadata={
            "sectors": [index + 1],
            "campaign_input_array_hashes": {
                "time_sha256": str(index + 1) * 64,
                "flux_sha256": str(index + 2) * 64,
                "flux_err_sha256": str(index + 3) * 64,
                "combined_sha256": str(index + 4) * 64,
            },
            "query_provenance_sha256": str(index + 5) * 64,
            "product_provenance_sha256": str(index + 6) * 64,
        },
    )


def _download(query: str, **_: object) -> LightCurve:
    names = ["HD 10700", "HD 20794", "HD 69830"]
    return _lightcurve(query, names.index(query))


def _search(lc: LightCurve, *, direction: str, **_: object):
    snr = 10.0 if direction == "dimming" else 7.0
    return [
        SingleTransitEvent(
            target=lc.target,
            center_time_days=1.0 if direction == "dimming" else 2.0,
            duration_days=0.08,
            depth=0.0001,
            snr=snr,
            local_points=6,
            direction=direction,
        )
    ]


def _surrogates(lc: LightCurve, *, seeds, **_: object):
    sector = str(lc.metadata["sectors"][0])
    trials = [
        SurrogateTrial(
            target=lc.target,
            sector_label=sector,
            seed=int(seed),
            method=GAP_AWARE_METHOD,
            block_days=0.5,
            contiguous_segments=1,
            gap_factor=3.5,
            neutralized_events=0,
            neutralized_points=0,
            dimming_events=1,
            brightening_events=0,
            maximum_dimming_snr=5.0,
            maximum_brightening_snr=4.0,
            exceeded_dimming_threshold=True,
            exceeded_brightening_threshold=False,
        )
        for seed in seeds
    ]
    summary = SurrogateSummary(
        target=lc.target,
        sector_label=sector,
        trials=len(trials),
        detection_threshold=5.0,
        minimum_segments=1,
        maximum_segments=1,
        gap_factor=3.5,
        neutralized_events=0,
        neutralized_points=0,
        trials_with_dimming_events=len(trials),
        trials_with_brightening_events=0,
        dimming_false_alarm_rate=1.0,
        brightening_false_alarm_rate=0.0,
        median_maximum_dimming_snr=5.0,
        p90_maximum_dimming_snr=5.0,
        p95_maximum_dimming_snr=5.0,
        maximum_dimming_snr=5.0,
        median_maximum_brightening_snr=4.0,
        p95_maximum_brightening_snr=4.0,
    )
    return trials, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    work = args.output.parent / "phase10-fixture-input"
    work.mkdir(parents=True, exist_ok=True)
    manifest = work / "targets.csv"
    _manifest(manifest)
    result = run_phase10_private_campaign(
        manifest_path=manifest,
        output_directory=args.output,
        source_commit=args.source_commit,
        frozen_at_utc=FROZEN_AT,
        environ={"HOU_PRIVATE_EVIDENCE_SINK": "1"},
        downloader=_download,
        searcher=_search,
        surrogate_runner=_surrogates,
    )
    print(json.dumps(result.public_receipt, indent=2, sort_keys=True))
    print(json.dumps({"private_manifest_sha256": result.private_manifest_sha256}))


if __name__ == "__main__":
    main()
