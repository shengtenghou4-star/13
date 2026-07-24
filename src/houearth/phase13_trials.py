from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .candidate_campaign import (
    PHASE09_FLATTEN_WINDOW_DAYS,
    PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
    PHASE09_MINIMUM_SEARCH_SNR,
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    build_blind_candidate_inputs,
)
from .candidate_freeze import TARGET_FAMILYWISE_ALPHA, BlindCandidateInput, freeze_candidate_table
from .core import LightCurve
from .phase12_locked_inputs import Phase12LockedInput
from .physical import inject_physical_single_transit
from .provenance import canonical_json_sha256
from .real_evaluation import _valid_injection_windows
from .search import search_single_transits
from .phase13_protocol import (
    PHASE13_DEPTHS,
    PHASE13_DURATIONS_DAYS,
    PHASE13_GAP_FACTOR,
    PHASE13_IMPACT_PARAMETER,
    PHASE13_LIMB_U1,
    PHASE13_LIMB_U2,
    PHASE13_MINIMUM_COVERAGE,
    PHASE13_PHASE_SEEDS,
    PHASE13_SUPERSAMPLE,
    PHASE13_TARGET_CHECKPOINT_SCHEMA,
    PHASE13_TRIALS_PER_TARGET,
    Phase13InjectionTrial,
    Phase13SensitivityError,
    Phase13TargetBaseline,
    _trial_id,
    _valid_plan_hash,
    phase13_slot_available,
)


def run_phase13_injection_trial(
    item: Phase12LockedInput,
    baseline: Phase13TargetBaseline,
    *,
    depth: float,
    duration_days: float,
    phase_seed: int,
    plan_lock: Mapping[str, object],
    baseline_machine_rows: Sequence[BlindCandidateInput],
) -> Phase13InjectionTrial:
    plan_hash = _valid_plan_hash(plan_lock)
    if item.target_id != baseline.target_id:
        raise Phase13SensitivityError("target and baseline identity differ")
    planned_available = phase13_slot_available(
        plan_lock, target_id=baseline.target_id, duration_days=duration_days
    )
    normalized = item.lightcurve.normalized()
    excluded = [*baseline.dimming_events, *baseline.brightening_control_events]
    windows = _valid_injection_windows(
        normalized,
        duration_days=duration_days,
        excluded_events=excluded,
        gap_factor=PHASE13_GAP_FACTOR,
        minimum_coverage=PHASE13_MINIMUM_COVERAGE,
    )
    if bool(windows) != planned_available:
        raise Phase13SensitivityError("real injection availability differs from plan lock")
    if not windows:
        baseline_table = freeze_candidate_table(
            baseline_machine_rows,
            source_commit=str(plan_lock["source_commit"]),
            frozen_at_utc=str(plan_lock["frozen_at_utc"]),
        )
        return Phase13InjectionTrial(
            trial_id=_trial_id(
                plan_hash=plan_hash,
                baseline=baseline,
                depth=depth,
                duration_days=duration_days,
                phase_seed=phase_seed,
            ),
            target_id=baseline.target_id,
            target_name=baseline.target_name,
            sector_label=baseline.sector_label,
            batch_id=baseline.batch_id,
            intended_role=baseline.intended_role,
            campaign_input_combined_sha256=baseline.campaign_input_combined_sha256,
            locked_csv_sha256=baseline.locked_csv_sha256,
            depth=depth,
            duration_days=duration_days,
            phase_seed=phase_seed,
            injection_available=False,
            unavailable_reason="no-valid-window-under-frozen-coverage-gap-and-event-exclusion-rules",
            injected_center_days=None,
            local_coverage_fraction=None,
            impact_parameter=PHASE13_IMPACT_PARAMETER,
            radius_ratio=None,
            exposure_days=normalized.cadence,
            locator_recovered=False,
            target_selected=False,
            target_gate_recovered=False,
            campaign_screened_recovered=False,
            recovered_center_days=None,
            recovered_duration_days=None,
            recovered_snr=None,
            empirical_familywise_p=None,
            benjamini_hochberg_q=None,
            matched_brightening_snr=None,
            snr_above_matched_control=None,
            timing_error_days=None,
            injected_target_machine_events=0,
            global_machine_events=len(baseline_machine_rows),
            global_candidate_rows=len(baseline_table.candidates),
        )
    rng = np.random.default_rng(phase_seed)
    center, coverage = windows[int(rng.integers(0, len(windows)))]
    flux, radius_ratio = inject_physical_single_transit(
        normalized.time,
        normalized.flux,
        center=center,
        duration=duration_days,
        depth=depth,
        impact_parameter=PHASE13_IMPACT_PARAMETER,
        u1=PHASE13_LIMB_U1,
        u2=PHASE13_LIMB_U2,
        exposure_days=normalized.cadence,
        supersample=PHASE13_SUPERSAMPLE,
    )
    injected = LightCurve(
        normalized.time,
        flux,
        normalized.flux_err,
        target=baseline.target_name,
        metadata=normalized.metadata,
    )
    events = search_single_transits(
        injected,
        durations=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        flatten_window_days=PHASE09_FLATTEN_WINDOW_DAYS,
        min_snr=PHASE09_MINIMUM_SEARCH_SNR,
        max_events=PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
        direction="dimming",
    )
    tolerance = max(2.0 * injected.cadence, 0.65 * duration_days)
    nearby = [event for event in events if abs(event.center_time_days - center) <= tolerance]
    best = max(nearby, key=lambda event: event.snr) if nearby else None
    injected_rows, _ = build_blind_candidate_inputs(
        target_id=baseline.target_id,
        target_name=baseline.target_name,
        sector_label=baseline.sector_label,
        campaign_input_sha256=baseline.campaign_input_combined_sha256,
        search_duration_family_days=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        dimming_events=events,
        brightening_control_events=baseline.brightening_control_events,
        surrogate_trials=baseline.surrogate_trials,
    )
    global_rows = [
        row for row in baseline_machine_rows if row.target_id != baseline.target_id
    ]
    global_rows.extend(injected_rows)
    table = freeze_candidate_table(
        global_rows,
        source_commit=str(plan_lock["source_commit"]),
        frozen_at_utc=str(plan_lock["frozen_at_utc"]),
    )
    selected = next(
        (row for row in table.candidates if row.target_id == baseline.target_id),
        None,
    )
    target_selected = bool(
        selected is not None
        and abs(selected.center_time_days - center) <= tolerance
    )
    target_gate = bool(
        target_selected
        and selected is not None
        and selected.empirical_familywise_p <= TARGET_FAMILYWISE_ALPHA
        and selected.snr_above_matched_control is not None
        and selected.snr_above_matched_control > 0
    )
    campaign_screened = bool(
        target_selected and selected is not None and selected.blind_status == "screened-in"
    )
    if campaign_screened and not target_gate:
        raise Phase13SensitivityError("campaign recovery does not imply target recovery")
    return Phase13InjectionTrial(
        trial_id=_trial_id(
            plan_hash=plan_hash,
            baseline=baseline,
            depth=depth,
            duration_days=duration_days,
            phase_seed=phase_seed,
        ),
        target_id=baseline.target_id,
        target_name=baseline.target_name,
        sector_label=baseline.sector_label,
        batch_id=baseline.batch_id,
        intended_role=baseline.intended_role,
        campaign_input_combined_sha256=baseline.campaign_input_combined_sha256,
        locked_csv_sha256=baseline.locked_csv_sha256,
        depth=depth,
        duration_days=duration_days,
        phase_seed=phase_seed,
        injection_available=True,
        unavailable_reason=None,
        injected_center_days=center,
        local_coverage_fraction=coverage,
        impact_parameter=PHASE13_IMPACT_PARAMETER,
        radius_ratio=radius_ratio,
        exposure_days=normalized.cadence,
        locator_recovered=best is not None,
        target_selected=target_selected,
        target_gate_recovered=target_gate,
        campaign_screened_recovered=campaign_screened,
        recovered_center_days=None if best is None else float(best.center_time_days),
        recovered_duration_days=None if best is None else float(best.duration_days),
        recovered_snr=None if best is None else float(best.snr),
        empirical_familywise_p=(
            None if not target_selected or selected is None else selected.empirical_familywise_p
        ),
        benjamini_hochberg_q=(
            None if not target_selected or selected is None else selected.benjamini_hochberg_q
        ),
        matched_brightening_snr=(
            None if not target_selected or selected is None else selected.matched_brightening_snr
        ),
        snr_above_matched_control=(
            None if not target_selected or selected is None else selected.snr_above_matched_control
        ),
        timing_error_days=(
            None if best is None else abs(float(best.center_time_days) - center)
        ),
        injected_target_machine_events=len(injected_rows),
        global_machine_events=len(global_rows),
        global_candidate_rows=len(table.candidates),
    )


def run_phase13_target(
    item: Phase12LockedInput,
    baseline: Phase13TargetBaseline,
    *,
    plan_lock: Mapping[str, object],
    baseline_machine_rows: Sequence[BlindCandidateInput],
) -> dict[str, object]:
    trials = [
        run_phase13_injection_trial(
            item,
            baseline,
            depth=depth,
            duration_days=duration,
            phase_seed=seed,
            plan_lock=plan_lock,
            baseline_machine_rows=baseline_machine_rows,
        )
        for duration in PHASE13_DURATIONS_DAYS
        for seed in PHASE13_PHASE_SEEDS
        for depth in PHASE13_DEPTHS
    ]
    payload = {
        "schema": PHASE13_TARGET_CHECKPOINT_SCHEMA,
        "plan_lock_sha256": _valid_plan_hash(plan_lock),
        "source_commit": plan_lock["source_commit"],
        "target_id": baseline.target_id,
        "target_name": baseline.target_name,
        "sector_label": baseline.sector_label,
        "batch_id": baseline.batch_id,
        "intended_role": baseline.intended_role,
        "campaign_input_combined_sha256": baseline.campaign_input_combined_sha256,
        "locked_csv_sha256": baseline.locked_csv_sha256,
        "calibration_sha256": baseline.calibration_sha256,
        "trial_count": len(trials),
        "trials": [trial.to_dict() for trial in trials],
    }
    return {**payload, "checkpoint_sha256": canonical_json_sha256(payload)}


def validate_phase13_target_checkpoint(
    payload: Mapping[str, object],
    *,
    plan_lock: Mapping[str, object],
    baseline: Phase13TargetBaseline,
) -> None:
    expected_hash = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "checkpoint_sha256"}
    )
    if payload.get("checkpoint_sha256") != expected_hash:
        raise Phase13SensitivityError("target checkpoint hash does not match")
    if payload.get("plan_lock_sha256") != _valid_plan_hash(plan_lock):
        raise Phase13SensitivityError("target checkpoint belongs to another plan")
    identity = {
        "target_id": baseline.target_id,
        "target_name": baseline.target_name,
        "sector_label": baseline.sector_label,
        "batch_id": baseline.batch_id,
        "intended_role": baseline.intended_role,
        "campaign_input_combined_sha256": baseline.campaign_input_combined_sha256,
        "locked_csv_sha256": baseline.locked_csv_sha256,
        "calibration_sha256": baseline.calibration_sha256,
    }
    for key, value in identity.items():
        if payload.get(key) != value:
            raise Phase13SensitivityError(f"target checkpoint {key} differs")
    raw_trials = payload.get("trials")
    if not isinstance(raw_trials, Sequence) or isinstance(raw_trials, (str, bytes)):
        raise Phase13SensitivityError("target checkpoint trials are malformed")
    if len(raw_trials) != PHASE13_TRIALS_PER_TARGET:
        raise Phase13SensitivityError("target checkpoint trial count differs")
    observed: set[tuple[float, float, int]] = set()
    ids: set[str] = set()
    for raw in raw_trials:
        if not isinstance(raw, Mapping):
            raise Phase13SensitivityError("target checkpoint contains a malformed trial")
        key = (float(raw["depth"]), float(raw["duration_days"]), int(raw["phase_seed"]))
        observed.add(key)
        trial_id = str(raw["trial_id"])
        if trial_id in ids:
            raise Phase13SensitivityError("target checkpoint contains duplicate trial IDs")
        ids.add(trial_id)
        available = bool(raw.get("injection_available"))
        planned_available = phase13_slot_available(
            plan_lock,
            target_id=baseline.target_id,
            duration_days=float(raw["duration_days"]),
        )
        if available != planned_available:
            raise Phase13SensitivityError("trial availability differs from plan lock")
        if bool(raw["campaign_screened_recovered"]) and not bool(
            raw["target_gate_recovered"]
        ):
            raise Phase13SensitivityError("campaign recovery lacks target recovery")
        if bool(raw["target_gate_recovered"]) and not bool(raw["locator_recovered"]):
            raise Phase13SensitivityError("target recovery lacks locator recovery")
        if not available:
            if any(
                bool(raw[field])
                for field in (
                    "locator_recovered",
                    "target_selected",
                    "target_gate_recovered",
                    "campaign_screened_recovered",
                )
            ):
                raise Phase13SensitivityError("unavailable trial cannot be recovered")
            if raw.get("injected_center_days") is not None or raw.get(
                "local_coverage_fraction"
            ) is not None:
                raise Phase13SensitivityError("unavailable trial contains an injection")
        else:
            coverage = raw.get("local_coverage_fraction")
            if coverage is None or float(coverage) < PHASE13_MINIMUM_COVERAGE:
                raise Phase13SensitivityError("trial local coverage is below the frozen gate")
    expected = {
        (depth, duration, seed)
        for depth in PHASE13_DEPTHS
        for duration in PHASE13_DURATIONS_DAYS
        for seed in PHASE13_PHASE_SEEDS
    }
    if observed != expected:
        raise Phase13SensitivityError("target checkpoint grid differs from the plan")


def atomic_write_phase13_checkpoint(payload: Mapping[str, object], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    os.replace(temporary, destination)
