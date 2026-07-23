from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from houearth.core import LightCurve, SingleTransitEvent
from houearth.phase11_campaign import run_phase11_private_campaign
from houearth.surrogates import GAP_AWARE_METHOD, SurrogateSummary, SurrogateTrial

SOURCE_COMMIT = "c" * 40
FROZEN_AT = "2026-07-23T10:45:00Z"
POOL_PATH = Path(__file__).parents[1] / "data" / "phase11_expanded_target_pool.csv"
SNAPSHOT = "hostname,hd_name,hip_name,tic_id,pl_name,tran_flag,default_flag,rowupdate\n".encode()


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def downloader(query: str, **_: object) -> LightCurve:
    time = np.linspace(0.0, 20.0, 1200)
    return LightCurve(
        time,
        np.ones_like(time),
        np.full_like(time, 0.0002),
        target=query,
        metadata={
            "sectors": [1],
            "campaign_input_array_hashes": {
                "time_sha256": _digest(query + "-time"),
                "flux_sha256": _digest(query + "-flux"),
                "flux_err_sha256": _digest(query + "-err"),
                "combined_sha256": _digest(query + "-combined"),
            },
            "query_provenance_sha256": _digest(query + "-query"),
            "product_provenance_sha256": _digest(query + "-product"),
        },
    )


def searcher(lc: LightCurve, *, direction: str, **_: object) -> list[SingleTransitEvent]:
    if direction == "dimming":
        return [SingleTransitEvent(
            target=lc.target,
            center_time_days=5.0,
            duration_days=0.08,
            depth=0.0003,
            snr=10.0,
            local_points=6,
            direction="dimming",
        )]
    return [SingleTransitEvent(
        target=lc.target,
        center_time_days=8.0,
        duration_days=0.08,
        depth=0.0001,
        snr=6.0,
        local_points=6,
        direction="brightening",
    )]


def surrogate_runner(lc: LightCurve, *, seeds, **_: object):
    trials = [SurrogateTrial(
        target=lc.target,
        sector_label="1",
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
    ) for seed in seeds]
    summary = SurrogateSummary(
        target=lc.target,
        sector_label="1",
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


def test_phase11_campaign_freezes_twelve_target_private_evidence(tmp_path: Path) -> None:
    sink = tmp_path / "private"
    result = run_phase11_private_campaign(
        pool_path=POOL_PATH,
        output_directory=sink,
        source_commit=SOURCE_COMMIT,
        frozen_at_utc=FROZEN_AT,
        environ={"HOU_PRIVATE_EVIDENCE_SINK": "1"},
        snapshot_fetcher=lambda: SNAPSHOT,
        downloader=downloader,
        searcher=searcher,
        surrogate_runner=surrogate_runner,
    )
    receipt = result.public_receipt
    assert receipt["pool_rows"] == 18
    assert receipt["selected_targets"] == 12
    assert receipt["surrogate_trials"] == 768
    assert receipt["machine_events"] == 12
    assert receipt["candidate_rows"] == 12
    assert receipt["screened_in"] == 12
    assert receipt["all_unopened"] is True
    assert receipt["all_unclassified"] is True
    assert receipt["all_validations_accepted"] is True
    assert receipt["candidate_details_disclosed"] is False
    assert len(result.private_manifest_sha256) == 64
    assert (sink / "phase11_selection_lock.json").is_file()
    assert (sink / "catalog_audit" / "nasa_ps_snapshot.csv").is_file()
    assert len(list((sink / "campaign_inputs").glob("*.csv"))) == 12
