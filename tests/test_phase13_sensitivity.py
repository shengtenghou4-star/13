from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from houearth.candidate_campaign import (
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    PHASE09_SURROGATE_SEEDS,
)
from houearth.core import LightCurve, SingleTransitEvent
from houearth.phase12_locked_inputs import Phase12LockedInput, Phase12LockedSelection
from houearth.phase13_sensitivity import (
    PHASE13_DEPTHS,
    PHASE13_DURATIONS_DAYS,
    PHASE13_TRIALS_PER_TARGET,
    Phase13SensitivityError,
    Phase13TargetBaseline,
    build_phase13_plan_lock,
    run_phase13_injection_trial,
    run_phase13_target,
    summarize_phase13_trials,
    validate_phase13_target_checkpoint,
)
from houearth.provenance import canonical_json_sha256, lightcurve_array_hashes
from houearth.surrogates import GAP_AWARE_METHOD, SurrogateTrial


def _lightcurve(target: str = "fixture") -> LightCurve:
    time = np.arange(0.0, 30.0, 0.02)
    flux = 1.0 + 0.00015 * np.sin(2 * np.pi * time / 5.3)
    err = np.full_like(time, 0.0002)
    hashes = lightcurve_array_hashes(time, flux, err)
    return LightCurve(
        time,
        flux,
        err,
        target=target,
        metadata={
            "sectors": [1, 2],
            "products": 2,
            "campaign_input_array_hashes": hashes,
        },
    )


def _surrogates(target: str, sector: str) -> tuple[SurrogateTrial, ...]:
    return tuple(
        SurrogateTrial(
            target=target,
            sector_label=sector,
            seed=seed,
            method=GAP_AWARE_METHOD,
            block_days=0.5,
            contiguous_segments=2,
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


def _fixture():
    controls = (
        SingleTransitEvent(
            target="fixture",
            center_time_days=1.0,
            duration_days=0.16,
            depth=0.0001,
            snr=5.1,
            local_points=8,
            direction="brightening",
        ),
    )
    items = []
    baselines = []
    for index in range(64):
        target_id = "fixture" if index == 0 else f"fixture-{index}"
        lc = _lightcurve(target_id)
        csv_sha = f"{index + 1:064x}"[-64:]
        item = Phase12LockedInput(
            target_id=target_id,
            query=target_id,
            intended_role="solar-analog",
            sector_label="1;2",
            batch_id=index // 16 + 1,
            stratum_position=index % 16 + 1,
            products=2,
            distinct_sectors=2,
            csv_relative_path=(
                f"campaign_inputs/batch-{index // 16 + 1:02d}/{target_id}.csv"
            ),
            csv_sha256=csv_sha,
            lightcurve=lc,
        )
        baseline = Phase13TargetBaseline(
            target_id=target_id,
            target_name=target_id,
            sector_label="1;2",
            batch_id=item.batch_id,
            intended_role="solar-analog",
            campaign_input_combined_sha256=lc.metadata[
                "campaign_input_array_hashes"
            ]["combined_sha256"],
            locked_csv_sha256=csv_sha,
            dimming_events=(),
            brightening_control_events=controls,
            surrogate_trials=_surrogates(target_id, "1;2"),
            machine_rows=(),
            calibration_sha256=f"{index + 1000:064x}"[-64:],
        )
        items.append(item)
        baselines.append(baseline)
    locked = Phase12LockedSelection(
        root="/private",
        inputs=tuple(items),
        selection_lock={"source_commit": "a" * 40, "selection_lock_sha256": "c" * 64},
        selection_campaign_lock={"campaign_lock_sha256": "d" * 64},
        public_selection_receipt={},
        private_manifest={},
        locked_input_set_sha256="e" * 64,
    )
    plan = build_phase13_plan_lock(
        locked,
        baselines,
        source_commit="f" * 40,
        frozen_at_utc="2026-07-24T00:00:00Z",
    )
    return items[0], baselines[0], plan


def test_strong_injection_passes_all_three_recovery_layers() -> None:
    item, baseline, plan = _fixture()
    trial = run_phase13_injection_trial(
        item,
        baseline,
        depth=0.01,
        duration_days=0.16,
        phase_seed=13001,
        plan_lock=plan,
        baseline_machine_rows=(),
    )
    assert trial.locator_recovered
    assert trial.target_selected
    assert trial.target_gate_recovered
    assert trial.campaign_screened_recovered


def test_geometrically_unavailable_slot_is_not_a_recovery_failure() -> None:
    item, baseline, _ = _fixture()
    blocking = SingleTransitEvent(
        target=baseline.target_name,
        center_time_days=15.0,
        duration_days=100.0,
        depth=0.001,
        snr=20.0,
        local_points=100,
        direction="dimming",
    )
    blocked = replace(baseline, dimming_events=(blocking,))
    items = []
    baselines = []
    for index in range(64):
        target_id = blocked.target_id if index == 0 else f"blocked-{index}"
        lc = _lightcurve(target_id)
        csv_sha = f"{index + 200:064x}"[-64:]
        items.append(
            replace(
                item,
                target_id=target_id,
                query=target_id,
                batch_id=index // 16 + 1,
                stratum_position=index % 16 + 1,
                csv_relative_path=(
                    f"campaign_inputs/batch-{index // 16 + 1:02d}/{target_id}.csv"
                ),
                csv_sha256=csv_sha,
                lightcurve=lc,
            )
        )
        baselines.append(
            replace(
                blocked if index == 0 else baseline,
                target_id=target_id,
                target_name=target_id,
                batch_id=index // 16 + 1,
                campaign_input_combined_sha256=lc.metadata[
                    "campaign_input_array_hashes"
                ]["combined_sha256"],
                locked_csv_sha256=csv_sha,
                surrogate_trials=_surrogates(target_id, "1;2"),
                calibration_sha256=f"{index + 300:064x}"[-64:],
                dimming_events=(blocking,) if index == 0 else (),
            )
        )
    locked = Phase12LockedSelection(
        root="/private",
        inputs=tuple(items),
        selection_lock={"source_commit": "a" * 40, "selection_lock_sha256": "c" * 64},
        selection_campaign_lock={"campaign_lock_sha256": "d" * 64},
        public_selection_receipt={},
        private_manifest={},
        locked_input_set_sha256="e" * 64,
    )
    plan = build_phase13_plan_lock(
        locked,
        baselines,
        source_commit="f" * 40,
        frozen_at_utc="2026-07-24T00:00:00Z",
    )
    trial = run_phase13_injection_trial(
        items[0],
        baselines[0],
        depth=PHASE13_DEPTHS[0],
        duration_days=PHASE13_DURATIONS_DAYS[0],
        phase_seed=13001,
        plan_lock=plan,
        baseline_machine_rows=(),
    )
    assert trial.injection_available is False
    assert trial.locator_recovered is False
    assert trial.target_gate_recovered is False
    assert trial.campaign_screened_recovered is False
    assert trial.injected_center_days is None


def test_checkpoint_requires_exact_grid(monkeypatch) -> None:
    item, baseline, plan = _fixture()

    def fake_trial(*args, depth, duration_days, phase_seed, **kwargs):
        trial = run_phase13_injection_trial(
            item,
            baseline,
            depth=0.01,
            duration_days=0.16,
            phase_seed=13001,
            plan_lock=plan,
            baseline_machine_rows=(),
        )
        return replace(
            trial,
            trial_id=f"trial-{depth}-{duration_days}-{phase_seed}",
            depth=depth,
            duration_days=duration_days,
            phase_seed=phase_seed,
        )

    monkeypatch.setattr("houearth.phase13_trials.run_phase13_injection_trial", fake_trial)
    checkpoint = run_phase13_target(
        item,
        baseline,
        plan_lock=plan,
        baseline_machine_rows=(),
    )
    assert checkpoint["trial_count"] == PHASE13_TRIALS_PER_TARGET
    validate_phase13_target_checkpoint(checkpoint, plan_lock=plan, baseline=baseline)
    tampered = json.loads(json.dumps(checkpoint))
    tampered["trials"].pop()
    body = {k: v for k, v in tampered.items() if k != "checkpoint_sha256"}
    tampered["checkpoint_sha256"] = canonical_json_sha256(body)
    with pytest.raises(Phase13SensitivityError, match="trial count"):
        validate_phase13_target_checkpoint(tampered, plan_lock=plan, baseline=baseline)


def test_checkpoint_rejects_resealed_foreign_identity(monkeypatch) -> None:
    item, baseline, plan = _fixture()

    def fake_trial(*args, depth, duration_days, phase_seed, **kwargs):
        trial = run_phase13_injection_trial(
            item,
            baseline,
            depth=0.01,
            duration_days=0.16,
            phase_seed=13001,
            plan_lock=plan,
            baseline_machine_rows=(),
        )
        return replace(
            trial,
            trial_id=f"trial-{depth}-{duration_days}-{phase_seed}",
            depth=depth,
            duration_days=duration_days,
            phase_seed=phase_seed,
        )

    monkeypatch.setattr("houearth.phase13_trials.run_phase13_injection_trial", fake_trial)
    checkpoint = run_phase13_target(
        item, baseline, plan_lock=plan, baseline_machine_rows=()
    )
    tampered = json.loads(json.dumps(checkpoint))
    tampered["locked_csv_sha256"] = "9" * 64
    body = {k: v for k, v in tampered.items() if k != "checkpoint_sha256"}
    tampered["checkpoint_sha256"] = canonical_json_sha256(body)
    with pytest.raises(Phase13SensitivityError, match="locked_csv_sha256"):
        validate_phase13_target_checkpoint(tampered, plan_lock=plan, baseline=baseline)


def test_summary_keeps_three_recovery_layers_distinct() -> None:
    rows = []
    for index in range(4):
        rows.append(
            {
                "depth": PHASE13_DEPTHS[0],
                "duration_days": PHASE13_DURATIONS_DAYS[0],
                "intended_role": "solar-analog",
                "injection_available": True,
                "locator_recovered": index < 4,
                "target_gate_recovered": index < 3,
                "campaign_screened_recovered": index < 2,
            }
        )
    cells = summarize_phase13_trials(rows)
    global_cell = next(cell for cell in cells if cell.scope == "global")
    assert global_cell.locator_completeness == 1.0
    assert global_cell.target_gate_completeness == 0.75
    assert global_cell.campaign_screened_completeness == 0.5
    assert global_cell.eligible_trials == 4
    assert global_cell.unavailable_trials == 0
    assert global_cell.confidence_low < 0.75 < global_cell.confidence_high


def test_global_decision_power_audit_detects_resolution_floor() -> None:
    rows = []
    for index in range(62):
        p_value = 1.0 / 65.0 if index < 8 else 1.0
        rows.append(
            __import__(
                "houearth.candidate_freeze", fromlist=["BlindCandidateInput"]
            ).BlindCandidateInput(
                target_id=f"t-{index:02d}",
                target_name=f"T {index}",
                sector_label="1;2",
                center_time_days=2.0 + index,
                duration_days=0.16,
                depth=0.001,
                snr=10.0,
                empirical_familywise_p=p_value,
                matched_brightening_snr=5.0,
                snr_above_matched_control=5.0,
                campaign_input_combined_sha256=f"{index + 1:064x}"[-64:],
                search_duration_family_days=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
                source_event_index=0,
            )
        )
    from houearth.phase13_sensitivity import audit_phase13_global_decision_power

    audit = audit_phase13_global_decision_power(
        rows,
        source_commit="f" * 40,
        frozen_at_utc="2026-07-24T00:00:00Z",
    )
    assert audit["baseline_candidates_at_minimum_p"] == 8
    assert audit["optimistic_candidates_at_minimum_p_after_one_injection"] == 9
    assert audit["minimum_rank_required_for_bh_at_alpha_0_10"] == 10
    assert audit["single_signal_global_screening_possible"] is False
    assert (
        audit[
            "minimum_surrogate_trials_for_one_rank_one_candidate_at_current_family_size"
        ]
        == 629
    )
