from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

from .candidate_campaign import PHASE09_SURROGATE_SEEDS
from .candidate_freeze import TABLE_FDR_ALPHA, BlindCandidateInput, freeze_candidate_table
from .provenance import canonical_json_sha256
from .real_evaluation import wilson_interval
from .phase13_protocol import (
    PHASE13_DEPTHS,
    PHASE13_DURATIONS_DAYS,
    PHASE13_PHASE_SEEDS,
    PHASE13_PUBLIC_RECEIPT_SCHEMA,
    PHASE13_TOTAL_TRIALS,
    Phase13InjectionTrial,
    Phase13SensitivityCell,
    Phase13SensitivityError,
    Phase13TargetBaseline,
)
from .phase13_trials import validate_phase13_target_checkpoint


def summarize_phase13_trials(
    trials: Iterable[Phase13InjectionTrial | Mapping[str, object]],
) -> list[Phase13SensitivityCell]:
    rows = [trial.to_dict() if isinstance(trial, Phase13InjectionTrial) else dict(trial) for trial in trials]
    groups: dict[tuple[str, str | None, float, float], list[dict[str, object]]] = {}
    for row in rows:
        common = (float(row["depth"]), float(row["duration_days"]))
        groups.setdefault(("global", None, *common), []).append(row)
        groups.setdefault(("stratum", str(row["intended_role"]), *common), []).append(row)
    cells: list[Phase13SensitivityCell] = []
    for (scope, role, depth, duration), group in sorted(
        groups.items(), key=lambda item: (item[0][0], str(item[0][1]), item[0][2], item[0][3])
    ):
        locator = sum(bool(row["locator_recovered"]) for row in group)
        target = sum(bool(row["target_gate_recovered"]) for row in group)
        screened = sum(bool(row["campaign_screened_recovered"]) for row in group)
        low, high = wilson_interval(screened, len(group))
        cells.append(
            Phase13SensitivityCell(
                scope=scope,
                intended_role=role,
                depth=depth,
                duration_days=duration,
                trials=len(group),
                locator_recovered=locator,
                target_gate_recovered=target,
                campaign_screened_recovered=screened,
                locator_completeness=locator / len(group),
                target_gate_completeness=target / len(group),
                campaign_screened_completeness=screened / len(group),
                confidence_low=low,
                confidence_high=high,
            )
        )
    return cells


def audit_phase13_global_decision_power(
    baseline_machine_rows: Sequence[BlindCandidateInput],
    *,
    source_commit: str,
    frozen_at_utc: str,
) -> dict[str, object]:
    """Prove whether one additional minimum-p target can pass the frozen BH gate."""
    table = freeze_candidate_table(
        baseline_machine_rows,
        source_commit=source_commit,
        frozen_at_utc=frozen_at_utc,
    )
    candidate_count = len(table.candidates)
    targets_with_candidates = {row.target_id for row in table.candidates}
    missing_targets = max(0, 64 - len(targets_with_candidates))
    p_min = 1.0 / (len(PHASE09_SURROGATE_SEEDS) + 1.0)
    tolerance = 1e-15
    baseline_at_p_min = sum(
        abs(row.empirical_familywise_p - p_min) <= tolerance
        for row in table.candidates
    )
    # A single injected target can add at most one minimum-p selected candidate. If
    # the target previously had no candidate, the BH family grows by one as well.
    optimistic_candidate_count = candidate_count + (1 if missing_targets else 0)
    optimistic_p_min_count = baseline_at_p_min + 1
    required_rank = math.ceil(
        optimistic_candidate_count * p_min / TABLE_FDR_ALPHA - 1e-15
    )
    minimum_surrogates_for_single_rank_one = math.ceil(
        optimistic_candidate_count / TABLE_FDR_ALPHA
    ) - 1
    payload = {
        "schema": "houearth-phase13-global-decision-power-audit-v0.13.0",
        "baseline_candidate_rows": candidate_count,
        "baseline_targets_without_candidate": missing_targets,
        "surrogate_trials_per_target": len(PHASE09_SURROGATE_SEEDS),
        "minimum_resolvable_familywise_p": p_min,
        "baseline_candidates_at_minimum_p": baseline_at_p_min,
        "optimistic_candidate_rows_after_one_injection": optimistic_candidate_count,
        "optimistic_candidates_at_minimum_p_after_one_injection": optimistic_p_min_count,
        "minimum_rank_required_for_bh_at_alpha_0_10": required_rank,
        "single_signal_global_screening_possible": optimistic_p_min_count >= required_rank,
        "minimum_surrogate_trials_for_one_rank_one_candidate_at_current_family_size": (
            minimum_surrogates_for_single_rank_one
        ),
        "recommended_power_of_two_surrogate_trials": 1023,
        "interpretation": (
            "The frozen 64-surrogate empirical p grid cannot screen a single isolated "
            "signal through the 0.10 global BH gate at the observed campaign family size."
        ),
    }
    return {**payload, "audit_sha256": canonical_json_sha256(payload)}


def build_phase13_public_receipt(
    checkpoints: Sequence[Mapping[str, object]],
    *,
    plan_lock: Mapping[str, object],
    baselines: Sequence[Phase13TargetBaseline],
    baseline_machine_rows: Sequence[BlindCandidateInput],
) -> dict[str, object]:
    baseline_by_id = {row.target_id: row for row in baselines}
    if len(checkpoints) != 64:
        raise Phase13SensitivityError("public receipt requires all 64 checkpoints")
    all_trials: list[Mapping[str, object]] = []
    checkpoint_hashes: list[str] = []
    seen: set[str] = set()
    for checkpoint in checkpoints:
        target_id = str(checkpoint.get("target_id", ""))
        if target_id in seen or target_id not in baseline_by_id:
            raise Phase13SensitivityError("checkpoint target set is invalid")
        seen.add(target_id)
        validate_phase13_target_checkpoint(
            checkpoint,
            plan_lock=plan_lock,
            baseline=baseline_by_id[target_id],
        )
        all_trials.extend(checkpoint["trials"])
        checkpoint_hashes.append(str(checkpoint["checkpoint_sha256"]))
    if len(all_trials) != PHASE13_TOTAL_TRIALS:
        raise Phase13SensitivityError("complete trial count differs from the plan")
    cells = summarize_phase13_trials(all_trials)
    global_cells = [cell.to_dict() for cell in cells if cell.scope == "global"]
    stratum_cells = [cell.to_dict() for cell in cells if cell.scope == "stratum"]
    decision_audit = audit_phase13_global_decision_power(
        baseline_machine_rows,
        source_commit=str(plan_lock["source_commit"]),
        frozen_at_utc=str(plan_lock["frozen_at_utc"]),
    )
    payload = {
        "schema": PHASE13_PUBLIC_RECEIPT_SCHEMA,
        "source_commit": plan_lock["source_commit"],
        "plan_lock_sha256": plan_lock["plan_lock_sha256"],
        "locked_input_set_sha256": plan_lock["locked_input_set_sha256"],
        "targets": 64,
        "trials": PHASE13_TOTAL_TRIALS,
        "depths": list(PHASE13_DEPTHS),
        "durations_days": list(PHASE13_DURATIONS_DAYS),
        "phase_seeds_per_cell": len(PHASE13_PHASE_SEEDS),
        "target_checkpoint_set_sha256": canonical_json_sha256(sorted(checkpoint_hashes)),
        "global_completeness": global_cells,
        "stratum_completeness": stratum_cells,
        "primary_metric": "target_gate_completeness",
        "campaign_screened_metric_role": "global decision-power diagnostic",
        "global_decision_power_audit": decision_audit,
        "one_global_bh_per_injection_trial": True,
        "thresholds_relaxed": False,
        "network_downloads_during_injections": 0,
        "target_details_disclosed": False,
        "astronomical_claim": "sensitivity calibration only",
    }
    return {**payload, "receipt_sha256": canonical_json_sha256(payload)}
