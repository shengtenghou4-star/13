from __future__ import annotations

import json

import numpy as np
import pytest

from houearth.candidate_campaign import (
    PHASE09_FLATTEN_WINDOW_DAYS,
    PHASE09_MINIMUM_SEARCH_SNR,
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    PHASE09_SURROGATE_SEEDS,
)
from houearth.candidate_freeze import BlindCandidateInput
from houearth.core import LightCurve
from houearth.phase14_power_restore import (
    PHASE14_EXTENSION_SEEDS,
    PHASE14_TOTAL_SURROGATES,
    Phase14PowerError,
    assemble_phase14_target_calibration,
    audit_phase14_power_restoration,
    build_phase14_chunk_receipt,
    build_phase14_plan_lock,
    phase14_seed_chunks,
    recalibrate_phase14_machine_rows,
    run_phase14_dimming_surrogate_trial,
    validate_phase14_chunk_receipt,
)
from houearth.provenance import canonical_json_sha256, lightcurve_array_hashes
from houearth.surrogates import (
    GAP_AWARE_METHOD,
    SurrogateTrial,
    run_surrogate_null_campaign,
)


def _lc() -> LightCurve:
    time = np.arange(0.0, 8.0, 0.02)
    flux = 1.0 + 0.0002 * np.sin(2 * np.pi * time / 1.7)
    error = np.full_like(time, 0.0002)
    hashes = lightcurve_array_hashes(time, flux, error)
    return LightCurve(
        time,
        flux,
        error,
        target="fixture",
        metadata={
            "sectors": [1, 2],
            "campaign_input_array_hashes": hashes,
        },
    )


def _old_trials() -> tuple[SurrogateTrial, ...]:
    return tuple(
        SurrogateTrial(
            target="fixture",
            sector_label="1;2",
            seed=seed,
            method=GAP_AWARE_METHOD,
            block_days=0.5,
            contiguous_segments=1,
            gap_factor=3.5,
            neutralized_events=0,
            neutralized_points=0,
            dimming_events=0,
            brightening_events=0,
            maximum_dimming_snr=4.0,
            maximum_brightening_snr=4.0,
            exceeded_dimming_threshold=False,
            exceeded_brightening_threshold=False,
        )
        for seed in PHASE09_SURROGATE_SEEDS
    )


def _fake_extension_trial(seed: int, maximum: float = 4.0) -> dict[str, object]:
    lightcurve = _lc()
    digest = lightcurve.metadata["campaign_input_array_hashes"]["combined_sha256"]
    trial = run_phase14_dimming_surrogate_trial(
        lightcurve,
        target_id="t-1",
        campaign_input_combined_sha256=digest,
        seed=seed,
    )
    body = trial.to_dict()
    body["maximum_dimming_snr"] = maximum
    body["exceeded_dimming_threshold"] = maximum >= PHASE09_MINIMUM_SEARCH_SNR
    body.pop("trial_sha256")
    return {**body, "trial_sha256": canonical_json_sha256(body)}


def test_dimming_only_extension_matches_full_surrogate_maximum() -> None:
    lightcurve = _lc()
    seed = PHASE14_EXTENSION_SEEDS[0]
    full, _ = run_surrogate_null_campaign(
        lightcurve,
        seeds=[seed],
        block_days=0.5,
        durations=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        min_snr=PHASE09_MINIMUM_SEARCH_SNR,
        flatten_window_days=PHASE09_FLATTEN_WINDOW_DAYS,
        excluded_events=(),
    )
    extension = run_phase14_dimming_surrogate_trial(
        lightcurve,
        target_id="t-1",
        campaign_input_combined_sha256=lightcurve.metadata[
            "campaign_input_array_hashes"
        ]["combined_sha256"],
        seed=seed,
    )
    assert extension.maximum_dimming_snr == full[0].maximum_dimming_snr


def test_seed_chunks_cover_extension_exactly_once() -> None:
    chunks = phase14_seed_chunks()
    flattened = tuple(seed for chunk in chunks for seed in chunk)
    assert flattened == PHASE14_EXTENSION_SEEDS
    assert len(flattened) == len(set(flattened)) == 959
    assert len(chunks) == 120
    assert len(chunks[-1]) == 7


def test_chunk_rejects_resealed_missing_trial() -> None:
    lightcurve = _lc()
    digest = lightcurve.metadata["campaign_input_array_hashes"]["combined_sha256"]
    seeds = phase14_seed_chunks()[0]
    trials = [_fake_extension_trial(seed) for seed in seeds]
    receipt = build_phase14_chunk_receipt(
        trials,
        target_id="t-1",
        target_name="fixture",
        sector_label="1;2",
        campaign_input_combined_sha256=digest,
        expected_seeds=seeds,
    )
    validate_phase14_chunk_receipt(
        receipt,
        target_id="t-1",
        target_name="fixture",
        sector_label="1;2",
        campaign_input_combined_sha256=digest,
    )

    tampered = json.loads(json.dumps(receipt))
    tampered["trials"].pop()
    tampered["seeds"].pop()
    tampered["seed_count"] -= 1
    tampered["last_seed"] -= 1
    tampered["trial_sha256s"].pop()
    body = {key: value for key, value in tampered.items() if key != "chunk_sha256"}
    tampered["chunk_sha256"] = canonical_json_sha256(body)
    with pytest.raises(Phase14PowerError):
        validate_phase14_chunk_receipt(
            tampered,
            target_id="t-1",
            target_name="fixture",
            sector_label="1;2",
            campaign_input_combined_sha256=digest,
        )


def test_target_assembly_requires_all_1023_maxima() -> None:
    lightcurve = _lc()
    digest = lightcurve.metadata["campaign_input_array_hashes"]["combined_sha256"]
    chunks = []
    for seeds in phase14_seed_chunks():
        chunks.append(
            build_phase14_chunk_receipt(
                [_fake_extension_trial(seed) for seed in seeds],
                target_id="t-1",
                target_name="fixture",
                sector_label="1;2",
                campaign_input_combined_sha256=digest,
                expected_seeds=seeds,
            )
        )
    calibration = assemble_phase14_target_calibration(
        target_id="t-1",
        target_name="fixture",
        sector_label="1;2",
        campaign_input_combined_sha256=digest,
        phase09_trials=_old_trials(),
        extension_chunks=chunks,
    )
    assert calibration["total_surrogate_trials"] == PHASE14_TOTAL_SURROGATES
    assert calibration["minimum_resolvable_familywise_p"] == 1 / 1024
    with pytest.raises(Phase14PowerError, match="every frozen extension chunk"):
        assemble_phase14_target_calibration(
            target_id="t-1",
            target_name="fixture",
            sector_label="1;2",
            campaign_input_combined_sha256=digest,
            phase09_trials=_old_trials(),
            extension_chunks=chunks[:-1],
        )


def test_rank_one_power_is_restored_and_rows_use_1024_denominator() -> None:
    audit = audit_phase14_power_restoration(candidate_family_size=63)
    assert audit["power_restored"] is True
    assert audit["minimum_surrogates_for_rank_one_resolution"] == 629
    assert audit["rank_one_bh_q"] == pytest.approx(63 / 1024)

    lightcurve = _lc()
    digest = lightcurve.metadata["campaign_input_array_hashes"]["combined_sha256"]
    body = {
        "schema": "houearth-phase14-target-calibration-v0.14.0",
        "target_id": "t-1",
        "target_name": "fixture",
        "sector_label": "1;2",
        "campaign_input_combined_sha256": digest,
        "reused_phase09_trials": 64,
        "extension_trials": 959,
        "total_surrogate_trials": 1023,
        "minimum_resolvable_familywise_p": 1 / 1024,
        "phase09_trial_sha256": "a" * 64,
        "extension_chunk_sha256s": ["b" * 64],
        "maximum_dimming_snr": [4.0] * 1023,
    }
    calibration = {
        **body,
        "target_calibration_sha256": canonical_json_sha256(body),
    }
    row = BlindCandidateInput(
        target_id="t-1",
        target_name="fixture",
        sector_label="1;2",
        center_time_days=2.0,
        duration_days=0.16,
        depth=0.001,
        snr=10.0,
        empirical_familywise_p=1 / 65,
        matched_brightening_snr=5.0,
        snr_above_matched_control=5.0,
        campaign_input_combined_sha256=digest,
        search_duration_family_days=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        source_event_index=0,
    )
    recalibrated = recalibrate_phase14_machine_rows([row], calibration)
    assert recalibrated[0].empirical_familywise_p == 1 / 1024


def test_plan_lock_freezes_cost_and_forbids_partial_candidate_freeze() -> None:
    lock = build_phase14_plan_lock(
        source_commit="a" * 40,
        frozen_at_utc="2026-07-24T00:00:00Z",
        locked_input_set_sha256="b" * 64,
        phase12_candidate_table_sha256="c" * 64,
        phase12_campaign_evidence_sha256="d" * 64,
    )
    assert lock["total_extension_trials"] == 61376
    assert lock["chunk_count_per_target"] == 120
    assert lock["candidate_table_freeze_before_complete"] is False
    assert lock["power_audit"]["power_restored"] is True
