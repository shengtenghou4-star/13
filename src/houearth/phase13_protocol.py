from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from .candidate_campaign import (
    PHASE09_FLATTEN_WINDOW_DAYS,
    PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
    PHASE09_MINIMUM_SEARCH_SNR,
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    PHASE09_SURROGATE_SEEDS,
    build_blind_candidate_inputs,
)
from .candidate_freeze import (
    TABLE_FDR_ALPHA,
    TARGET_FAMILYWISE_ALPHA,
    BlindCandidateInput,
    freeze_candidate_table,
)
from .core import LightCurve, SingleTransitEvent
from .phase12_locked_inputs import Phase12LockedInput, Phase12LockedSelection
from .physical import inject_physical_single_transit
from .provenance import canonical_json_sha256
from .real_evaluation import _valid_injection_windows, wilson_interval
from .search import search_single_transits
from .surrogates import SurrogateTrial

PHASE13_PLAN_SCHEMA = "houearth-phase13-real-input-sensitivity-plan-v0.13.0"
PHASE13_TARGET_CHECKPOINT_SCHEMA = (
    "houearth-phase13-target-sensitivity-checkpoint-v0.13.0"
)
PHASE13_PUBLIC_RECEIPT_SCHEMA = (
    "houearth-phase13-real-input-sensitivity-public-receipt-v0.13.0"
)
PHASE13_DEPTHS = (0.0002, 0.0005, 0.001, 0.002)
PHASE13_DURATIONS_DAYS = (0.052, 0.08, 0.16, 0.232)
PHASE13_PHASE_SEEDS = (13001, 13002)
PHASE13_IMPACT_PARAMETER = 0.5
PHASE13_LIMB_U1 = 0.35
PHASE13_LIMB_U2 = 0.25
PHASE13_SUPERSAMPLE = 7
PHASE13_MINIMUM_COVERAGE = 0.70
PHASE13_GAP_FACTOR = 3.5
PHASE13_TRIALS_PER_TARGET = (
    len(PHASE13_DEPTHS) * len(PHASE13_DURATIONS_DAYS) * len(PHASE13_PHASE_SEEDS)
)
PHASE13_TOTAL_TRIALS = 64 * PHASE13_TRIALS_PER_TARGET
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Phase13SensitivityError(RuntimeError):
    """Raised when the sensitivity campaign violates a frozen boundary."""


@dataclass(frozen=True)
class Phase13TargetBaseline:
    target_id: str
    target_name: str
    sector_label: str
    batch_id: int
    intended_role: str
    campaign_input_combined_sha256: str
    locked_csv_sha256: str
    dimming_events: tuple[SingleTransitEvent, ...]
    brightening_control_events: tuple[SingleTransitEvent, ...]
    surrogate_trials: tuple[SurrogateTrial, ...]
    machine_rows: tuple[BlindCandidateInput, ...]
    calibration_sha256: str


@dataclass(frozen=True)
class Phase13InjectionTrial:
    trial_id: str
    target_id: str
    target_name: str
    sector_label: str
    batch_id: int
    intended_role: str
    campaign_input_combined_sha256: str
    locked_csv_sha256: str
    depth: float
    duration_days: float
    phase_seed: int
    injection_available: bool
    unavailable_reason: str | None
    injected_center_days: float | None
    local_coverage_fraction: float | None
    impact_parameter: float
    radius_ratio: float | None
    exposure_days: float
    locator_recovered: bool
    target_selected: bool
    target_gate_recovered: bool
    campaign_screened_recovered: bool
    recovered_center_days: float | None
    recovered_duration_days: float | None
    recovered_snr: float | None
    empirical_familywise_p: float | None
    benjamini_hochberg_q: float | None
    matched_brightening_snr: float | None
    snr_above_matched_control: float | None
    timing_error_days: float | None
    injected_target_machine_events: int
    global_machine_events: int
    global_candidate_rows: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Phase13SensitivityCell:
    scope: str
    intended_role: str | None
    depth: float
    duration_days: float
    trials: int
    eligible_trials: int
    unavailable_trials: int
    locator_recovered: int
    target_gate_recovered: int
    campaign_screened_recovered: int
    locator_completeness: float
    target_gate_completeness: float
    campaign_screened_completeness: float
    confidence_low: float
    confidence_high: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _event_from_row(row: Mapping[str, object]) -> SingleTransitEvent:
    return SingleTransitEvent(
        target=str(row["target"]),
        center_time_days=float(row["center_time_days"]),
        duration_days=float(row["duration_days"]),
        depth=float(row["depth"]),
        snr=float(row["snr"]),
        local_points=int(row["local_points"]),
        direction=str(row["direction"]),
    )


def _surrogate_from_row(row: Mapping[str, object]) -> SurrogateTrial:
    return SurrogateTrial(
        target=str(row["target"]),
        sector_label=str(row["sector_label"]),
        seed=int(row["seed"]),
        method=str(row["method"]),
        block_days=float(row["block_days"]),
        contiguous_segments=int(row["contiguous_segments"]),
        gap_factor=float(row["gap_factor"]),
        neutralized_events=int(row["neutralized_events"]),
        neutralized_points=int(row["neutralized_points"]),
        dimming_events=int(row["dimming_events"]),
        brightening_events=int(row["brightening_events"]),
        maximum_dimming_snr=(
            None
            if row["maximum_dimming_snr"] is None
            else float(row["maximum_dimming_snr"])
        ),
        maximum_brightening_snr=(
            None
            if row["maximum_brightening_snr"] is None
            else float(row["maximum_brightening_snr"])
        ),
        exceeded_dimming_threshold=bool(row["exceeded_dimming_threshold"]),
        exceeded_brightening_threshold=bool(row["exceeded_brightening_threshold"]),
    )


def _blind_row_from_mapping(row: Mapping[str, object]) -> BlindCandidateInput:
    return BlindCandidateInput(
        target_id=str(row["target_id"]),
        target_name=str(row["target_name"]),
        sector_label=str(row["sector_label"]),
        center_time_days=float(row["center_time_days"]),
        duration_days=float(row["duration_days"]),
        depth=float(row["depth"]),
        snr=float(row["snr"]),
        empirical_familywise_p=float(row["empirical_familywise_p"]),
        matched_brightening_snr=(
            None
            if row["matched_brightening_snr"] is None
            else float(row["matched_brightening_snr"])
        ),
        snr_above_matched_control=(
            None
            if row["snr_above_matched_control"] is None
            else float(row["snr_above_matched_control"])
        ),
        campaign_input_combined_sha256=str(
            row["campaign_input_combined_sha256"]
        ),
        search_duration_family_days=tuple(
            float(value) for value in row["search_duration_family_days"]
        ),
        source_event_index=int(row["source_event_index"]),
        event_direction=str(row["event_direction"]),
    )


def _blind_sort_key(row: BlindCandidateInput) -> tuple[object, ...]:
    return (
        row.target_id,
        row.campaign_input_combined_sha256,
        row.source_event_index,
        row.center_time_days,
        row.duration_days,
        row.depth,
        row.snr,
        row.empirical_familywise_p,
    )


def load_phase13_baselines(
    locked: Phase12LockedSelection,
    *,
    target_calibration_inputs: Sequence[Mapping[str, object]],
    baseline_machine_events: Sequence[Mapping[str, object]],
) -> tuple[Phase13TargetBaseline, ...]:
    """Validate and bind the exact Phase 0.12 calibration evidence to 64 inputs."""
    inputs = {item.target_id: item for item in locked.inputs}
    if len(inputs) != 64 or len(target_calibration_inputs) != 64:
        raise Phase13SensitivityError("Phase 0.13 requires exactly 64 frozen targets")
    machine_rows = tuple(_blind_row_from_mapping(row) for row in baseline_machine_events)
    machine_by_target: dict[str, list[BlindCandidateInput]] = {}
    for row in machine_rows:
        machine_by_target.setdefault(row.target_id, []).append(row)
    baselines: list[Phase13TargetBaseline] = []
    seen: set[str] = set()
    for raw in target_calibration_inputs:
        target_id = str(raw.get("target_id", ""))
        if target_id in seen or target_id not in inputs:
            raise Phase13SensitivityError("baseline target identity is missing or duplicated")
        seen.add(target_id)
        item = inputs[target_id]
        if int(raw.get("phase12_batch_id", -1)) != item.batch_id:
            raise Phase13SensitivityError("baseline batch identity differs from selection")
        if str(raw.get("phase12_intended_role", "")) != item.intended_role:
            raise Phase13SensitivityError("baseline stratum differs from selection")
        if str(raw.get("phase12_locked_csv_sha256", "")) != item.csv_sha256:
            raise Phase13SensitivityError("baseline CSV hash differs from selection")
        combined = str(raw.get("campaign_input_combined_sha256", ""))
        observed_combined = str(
            item.lightcurve.metadata["campaign_input_array_hashes"]["combined_sha256"]
        )
        if combined != observed_combined:
            raise Phase13SensitivityError("baseline array hash differs from selection")
        if tuple(float(v) for v in raw.get("search_duration_family_days", ())) != (
            PHASE09_SEARCH_DURATION_FAMILY_DAYS
        ):
            raise Phase13SensitivityError("baseline search durations are not frozen")
        dimming = tuple(_event_from_row(row) for row in raw["dimming_events"])
        brightening = tuple(
            _event_from_row(row) for row in raw["brightening_control_events"]
        )
        surrogates = tuple(_surrogate_from_row(row) for row in raw["surrogate_trials"])
        derived, _ = build_blind_candidate_inputs(
            target_id=target_id,
            target_name=str(raw["target_name"]),
            sector_label=str(raw["sector_label"]),
            campaign_input_sha256=combined,
            search_duration_family_days=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
            dimming_events=dimming,
            brightening_control_events=brightening,
            surrogate_trials=surrogates,
        )
        expected = tuple(sorted(derived, key=_blind_sort_key))
        observed = tuple(sorted(machine_by_target.get(target_id, ()), key=_blind_sort_key))
        if [row.to_dict() for row in expected] != [row.to_dict() for row in observed]:
            raise Phase13SensitivityError(
                "baseline machine rows do not reproduce from calibration evidence"
            )
        calibration_payload = {
            key: value
            for key, value in dict(raw).items()
            if key not in {"phase12_batch_id", "phase12_intended_role"}
        }
        baselines.append(
            Phase13TargetBaseline(
                target_id=target_id,
                target_name=str(raw["target_name"]),
                sector_label=str(raw["sector_label"]),
                batch_id=item.batch_id,
                intended_role=item.intended_role,
                campaign_input_combined_sha256=combined,
                locked_csv_sha256=item.csv_sha256,
                dimming_events=dimming,
                brightening_control_events=brightening,
                surrogate_trials=surrogates,
                machine_rows=expected,
                calibration_sha256=canonical_json_sha256(calibration_payload),
            )
        )
    if seen != set(inputs):
        raise Phase13SensitivityError("baseline target set differs from frozen selection")
    baselines.sort(key=lambda row: (row.batch_id, row.intended_role, row.target_id))
    return tuple(baselines)


def _phase13_availability_rows(
    locked: Phase12LockedSelection,
    baselines: Sequence[Phase13TargetBaseline],
) -> list[dict[str, object]]:
    items = {item.target_id: item for item in locked.inputs}
    if len(items) != 64 or {row.target_id for row in baselines} != set(items):
        raise ValueError("Phase 0.13 baseline and locked target sets must match exactly")
    rows: list[dict[str, object]] = []
    for baseline in baselines:
        normalized = items[baseline.target_id].lightcurve.normalized()
        excluded = [*baseline.dimming_events, *baseline.brightening_control_events]
        for duration in PHASE13_DURATIONS_DAYS:
            windows = _valid_injection_windows(
                normalized,
                duration_days=duration,
                excluded_events=excluded,
                gap_factor=PHASE13_GAP_FACTOR,
                minimum_coverage=PHASE13_MINIMUM_COVERAGE,
            )
            rows.append(
                {
                    "target_id": baseline.target_id,
                    "batch_id": baseline.batch_id,
                    "intended_role": baseline.intended_role,
                    "duration_days": duration,
                    "valid_window_count": len(windows),
                    "available": bool(windows),
                }
            )
    return rows


def phase13_slot_available(
    plan_lock: Mapping[str, object], *, target_id: str, duration_days: float
) -> bool:
    rows = plan_lock.get("availability_rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise Phase13SensitivityError("plan lock availability rows are malformed")
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and str(row.get("target_id", "")) == target_id
        and float(row.get("duration_days", -1.0)) == float(duration_days)
    ]
    if len(matches) != 1:
        raise Phase13SensitivityError("plan lock availability identity is missing or duplicated")
    return bool(matches[0].get("available"))


def build_phase13_plan_lock(
    locked: Phase12LockedSelection,
    baselines: Sequence[Phase13TargetBaseline],
    *,
    source_commit: str,
    frozen_at_utc: str,
) -> dict[str, object]:
    if _SHA40.fullmatch(source_commit) is None:
        raise ValueError("source_commit must be a lowercase 40-character Git SHA")
    if len(baselines) != 64:
        raise ValueError("Phase 0.13 requires 64 baselines")
    availability_rows = _phase13_availability_rows(locked, baselines)
    available_duration_cells = sum(bool(row["available"]) for row in availability_rows)
    available_trial_slots = (
        available_duration_cells * len(PHASE13_DEPTHS) * len(PHASE13_PHASE_SEEDS)
    )
    payload = {
        "schema": PHASE13_PLAN_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc,
        "selection_source_commit": locked.selection_lock["source_commit"],
        "selection_lock_sha256": locked.selection_lock["selection_lock_sha256"],
        "selection_campaign_lock_sha256": locked.selection_campaign_lock[
            "campaign_lock_sha256"
        ],
        "locked_input_set_sha256": locked.locked_input_set_sha256,
        "baseline_target_set_sha256": canonical_json_sha256(
            [
                {
                    "target_id": row.target_id,
                    "campaign_input_combined_sha256": row.campaign_input_combined_sha256,
                    "locked_csv_sha256": row.locked_csv_sha256,
                    "calibration_sha256": row.calibration_sha256,
                    "batch_id": row.batch_id,
                    "intended_role": row.intended_role,
                }
                for row in baselines
            ]
        ),
        "depths": list(PHASE13_DEPTHS),
        "durations_days": list(PHASE13_DURATIONS_DAYS),
        "phase_seeds": list(PHASE13_PHASE_SEEDS),
        "trials_per_target": PHASE13_TRIALS_PER_TARGET,
        "total_trials": PHASE13_TOTAL_TRIALS,
        "scheduled_trial_slots": PHASE13_TOTAL_TRIALS,
        "available_trial_slots": available_trial_slots,
        "unavailable_trial_slots": PHASE13_TOTAL_TRIALS - available_trial_slots,
        "available_target_duration_cells": available_duration_cells,
        "availability_rows": availability_rows,
        "availability_rows_sha256": canonical_json_sha256(availability_rows),
        "unavailable_slot_policy": (
            "record as geometrically unavailable; do not inject, do not count as a "
            "recovery failure, and do not choose an alternate unregistered center"
        ),
        "injection_model": "quadratic-limb-darkened-small-planet-exposure-averaged",
        "impact_parameter": PHASE13_IMPACT_PARAMETER,
        "limb_u1": PHASE13_LIMB_U1,
        "limb_u2": PHASE13_LIMB_U2,
        "supersample": PHASE13_SUPERSAMPLE,
        "minimum_local_coverage": PHASE13_MINIMUM_COVERAGE,
        "gap_factor": PHASE13_GAP_FACTOR,
        "search_duration_family_days": list(PHASE09_SEARCH_DURATION_FAMILY_DAYS),
        "flatten_window_days": PHASE09_FLATTEN_WINDOW_DAYS,
        "minimum_search_snr": PHASE09_MINIMUM_SEARCH_SNR,
        "surrogate_trials_per_target": len(PHASE09_SURROGATE_SEEDS),
        "target_familywise_alpha": TARGET_FAMILYWISE_ALPHA,
        "table_fdr_alpha": TABLE_FDR_ALPHA,
        "primary_recovery": (
            "injected event is localized, wins the target selection, passes the "
            "target-familywise p gate, and exceeds its matched brightening control"
        ),
        "global_bh_recovery_role": (
            "diagnostic decision-power audit; not the primary physical-completeness "
            "metric when empirical p resolution makes a single-signal discovery impossible"
        ),
        "network_downloads_permitted": False,
        "threshold_relaxation_permitted": False,
    }
    return {**payload, "plan_lock_sha256": canonical_json_sha256(payload)}


def _valid_plan_hash(plan_lock: Mapping[str, object]) -> str:
    value = plan_lock.get("plan_lock_sha256")
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise Phase13SensitivityError("plan lock is missing a valid hash")
    expected = canonical_json_sha256(
        {key: val for key, val in plan_lock.items() if key != "plan_lock_sha256"}
    )
    if value != expected:
        raise Phase13SensitivityError("plan lock hash does not match")
    return value


def _trial_id(
    *,
    plan_hash: str,
    baseline: Phase13TargetBaseline,
    depth: float,
    duration_days: float,
    phase_seed: int,
) -> str:
    digest = canonical_json_sha256(
        {
            "schema": PHASE13_TARGET_CHECKPOINT_SCHEMA,
            "plan_lock_sha256": plan_hash,
            "target_id": baseline.target_id,
            "campaign_input_combined_sha256": baseline.campaign_input_combined_sha256,
            "depth": depth,
            "duration_days": duration_days,
            "phase_seed": phase_seed,
        }
    )
    return f"p13-{digest[:24]}"
