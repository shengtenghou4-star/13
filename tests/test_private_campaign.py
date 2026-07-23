from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from houearth.core import LightCurve, SingleTransitEvent
from houearth.private_campaign import run_phase10_private_campaign
from houearth.private_campaign_protocol import (
    PHASE10_REQUIRED_TARGET_IDS,
    PrivateCampaignError,
    load_phase10_manifest,
    require_private_evidence_sink,
)
from houearth.surrogates import GAP_AWARE_METHOD, SurrogateSummary, SurrogateTrial


SOURCE_COMMIT = "a" * 40
FROZEN_AT = "2026-07-23T08:00:00Z"
DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)


def write_manifest(path: Path) -> None:
    path.write_text(
        "target_id,query,author,sectors,max_products,intended_role,surrogate_policy,notes\n"
        'hd-10700,HD 10700,SPOC,,1,bright-low-scatter,unmasked-null,"reference"\n'
        'hd-20794,HD 20794,SPOC,,1,bright-reference,unmasked-null,"reference"\n'
        'hd-69830,HD 69830,SPOC,,1,bright-harder-background,unmasked-null,"reference"\n'
        'au-mic,AU Mic,SPOC,,1,bright-active,skip-known-transits,"known transit"\n'
        'toi-700,TOI 700,SPOC,,1,mid-magnitude,skip-known-transits,"known transit"\n'
        'lhs-3844,LHS 3844,SPOC,,1,faint,skip-known-transits,"known transit"\n',
        encoding="utf-8",
    )


def lightcurve(query: str, index: int) -> LightCurve:
    time = np.linspace(0.0, 3.0, 240)
    flux = np.ones_like(time)
    return LightCurve(
        time,
        flux,
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


def downloader(query: str, **_: object) -> LightCurve:
    names = ["HD 10700", "HD 20794", "HD 69830"]
    return lightcurve(query, names.index(query))


def searcher(lc: LightCurve, *, direction: str, **_: object) -> list[SingleTransitEvent]:
    if direction == "dimming":
        return [
            SingleTransitEvent(
                target=lc.target,
                center_time_days=1.0,
                duration_days=0.08,
                depth=0.0001,
                snr=10.0,
                local_points=6,
                direction="dimming",
            )
        ]
    return [
        SingleTransitEvent(
            target=lc.target,
            center_time_days=2.0,
            duration_days=0.08,
            depth=0.00008,
            snr=7.0,
            local_points=6,
            direction="brightening",
        )
    ]


def surrogate_runner(lc: LightCurve, *, seeds, **_: object):
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


def test_manifest_selects_exact_three_null_targets(tmp_path: Path) -> None:
    manifest = tmp_path / "targets.csv"
    write_manifest(manifest)
    targets, excluded, digest = load_phase10_manifest(manifest)
    assert tuple(target.target_id for target in targets) == PHASE10_REQUIRED_TARGET_IDS
    assert len(excluded) == 3
    assert len(digest) == 64


def test_private_sink_rejects_missing_or_public_authorization(tmp_path: Path) -> None:
    sink = tmp_path / "evidence"
    with pytest.raises(PrivateCampaignError, match="HOU_PRIVATE_EVIDENCE_SINK"):
        require_private_evidence_sink(sink, environ={})
    with pytest.raises(
        PrivateCampaignError, match="HOU_PRIVATE_REPOSITORY_VISIBILITY"
    ):
        require_private_evidence_sink(
            sink,
            environ={
                "HOU_PRIVATE_EVIDENCE_SINK": "1",
                "GITHUB_ACTIONS": "true",
                "HOU_PRIVATE_REPOSITORY_VISIBILITY": "public",
            },
        )
    assert require_private_evidence_sink(
        sink,
        environ={
            "HOU_PRIVATE_EVIDENCE_SINK": "1",
            "GITHUB_ACTIONS": "true",
            "HOU_PRIVATE_REPOSITORY_VISIBILITY": "private",
        },
    ) == sink.resolve()


def test_failed_acquisition_writes_nothing_and_never_searches(tmp_path: Path) -> None:
    manifest = tmp_path / "targets.csv"
    sink = tmp_path / "private"
    write_manifest(manifest)
    searched = False

    def failing_downloader(query: str, **kwargs: object) -> LightCurve:
        if query == "HD 20794":
            raise RuntimeError("simulated MAST failure")
        return downloader(query, **kwargs)

    def forbidden_searcher(*args: object, **kwargs: object):
        nonlocal searched
        searched = True
        raise AssertionError("search must not start after partial acquisition")

    with pytest.raises(PrivateCampaignError, match="all-or-nothing acquisition failed"):
        run_phase10_private_campaign(
            manifest_path=manifest,
            output_directory=sink,
            source_commit=SOURCE_COMMIT,
            frozen_at_utc=FROZEN_AT,
            environ={"HOU_PRIVATE_EVIDENCE_SINK": "1"},
            downloader=failing_downloader,
            searcher=forbidden_searcher,
            surrogate_runner=surrogate_runner,
        )
    assert searched is False
    assert sink.exists() is False


def test_private_campaign_freezes_complete_synthetic_evidence(tmp_path: Path) -> None:
    manifest = tmp_path / "targets.csv"
    sink = tmp_path / "private"
    write_manifest(manifest)
    result = run_phase10_private_campaign(
        manifest_path=manifest,
        output_directory=sink,
        source_commit=SOURCE_COMMIT,
        frozen_at_utc=FROZEN_AT,
        environ={"HOU_PRIVATE_EVIDENCE_SINK": "1"},
        downloader=downloader,
        searcher=searcher,
        surrogate_runner=surrogate_runner,
    )
    receipt = result.public_receipt
    assert receipt["targets"] == 3
    assert receipt["surrogate_trials"] == 192
    assert receipt["machine_events"] == 3
    assert receipt["candidate_rows"] == 3
    assert receipt["screened_in"] == 3
    assert receipt["all_unopened"] is True
    assert receipt["all_unclassified"] is True
    assert receipt["all_validations_accepted"] is True
    assert receipt["candidate_details_disclosed"] is False
    assert len(result.private_manifest_sha256) == 64
    assert (sink / "campaign_lock.json").is_file()
    assert (sink / "candidate_evidence" / "candidate_table.json").is_file()
    assert (sink / "candidate_campaign_evidence.json").is_file()
    assert (sink / "PRIVATE_EVIDENCE_MANIFEST.json").is_file()
    assert len(list((sink / "campaign_inputs").glob("*.csv"))) == 3
