from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from numbers import Real
from typing import Mapping, Sequence

from .candidate_campaign import (
    PHASE09_FLATTEN_WINDOW_DAYS,
    PHASE09_MINIMUM_SEARCH_SNR,
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    PHASE09_SURROGATE_BLOCK_DAYS,
    PHASE09_SURROGATE_SEEDS,
)
from .candidate_freeze import (
    TABLE_FDR_ALPHA,
    TARGET_FAMILYWISE_ALPHA,
    BlindCandidateInput,
    benjamini_hochberg_qvalues,
)
from .core import LightCurve
from .provenance import canonical_json_sha256
from .search import search_single_transits
from .surrogates import (
    DEFAULT_GAP_FACTOR,
    GAP_AWARE_METHOD,
    SurrogateTrial,
    block_permuted_surrogate,
)

PHASE14_SCHEMA = "houearth-phase14-power-restore-v0.14.0"
PHASE14_PLAN_SCHEMA = "houearth-phase14-power-restore-plan-v0.14.0"
PHASE14_TRIAL_SCHEMA = "houearth-phase14-dimming-null-maximum-v0.14.0"
PHASE14_CHUNK_SCHEMA = "houearth-phase14-surrogate-chunk-v0.14.0"
PHASE14_TARGET_SCHEMA = "houearth-phase14-target-calibration-v0.14.0"
PHASE14_TOTAL_SURROGATES = 1023
PHASE14_EXTENSION_SEEDS = tuple(
    range(len(PHASE09_SURROGATE_SEEDS), PHASE14_TOTAL_SURROGATES)
)
PHASE14_EXTENSION_TRIALS_PER_TARGET = len(PHASE14_EXTENSION_SEEDS)
PHASE14_TARGETS = 64
PHASE14_TOTAL_EXTENSION_TRIALS = (
    PHASE14_TARGETS * PHASE14_EXTENSION_TRIALS_PER_TARGET
)
PHASE14_CHUNK_SIZE = 8
PHASE14_SEARCH_DIRECTION = "dimming"
PHASE14_PROBE_SNR = 1e-6

_SHA = re.compile(r"^[0-9a-f]{64}$")
_GIT = re.compile(r"^[0-9a-f]{40}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class Phase14PowerError(ValueError):
    pass


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise Phase14PowerError(f"{label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise Phase14PowerError(f"{label} must be finite")
    return parsed


def _valid_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise Phase14PowerError(f"{label} must be lowercase SHA-256")
    return value


@dataclass(frozen=True)
class Phase14SurrogateMaximum:
    schema: str
    target_id: str
    target_name: str
    sector_label: str
    campaign_input_combined_sha256: str
    seed: int
    method: str
    block_days: float
    gap_factor: float
    contiguous_segments: int
    maximum_dimming_snr: float | None
    exceeded_dimming_threshold: bool
    search_direction: str
    search_duration_family_days: tuple[float, ...]
    flatten_window_days: float
    minimum_search_snr: float
    trial_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def phase14_seed_chunks(
    chunk_size: int = PHASE14_CHUNK_SIZE,
) -> tuple[tuple[int, ...], ...]:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise Phase14PowerError("chunk_size must be a positive integer")
    seeds = PHASE14_EXTENSION_SEEDS
    chunks = tuple(
        tuple(seeds[index : index + chunk_size])
        for index in range(0, len(seeds), chunk_size)
    )
    flattened = tuple(seed for chunk in chunks for seed in chunk)
    if flattened != seeds or len(flattened) != len(set(flattened)):
        raise RuntimeError("internal Phase 0.14 chunk partition is invalid")
    return chunks


def run_phase14_dimming_surrogate_trial(
    lightcurve: LightCurve,
    *,
    target_id: str,
    campaign_input_combined_sha256: str,
    seed: int,
) -> Phase14SurrogateMaximum:
    if not isinstance(target_id, str) or not target_id.strip():
        raise Phase14PowerError("target_id must be non-empty")
    _valid_sha(campaign_input_combined_sha256, "campaign_input_combined_sha256")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed not in PHASE14_EXTENSION_SEEDS
    ):
        raise Phase14PowerError(
            "seed must belong to the frozen Phase 0.14 extension range"
        )
    recorded = lightcurve.metadata.get("campaign_input_array_hashes", {}).get(
        "combined_sha256"
    )
    if recorded != campaign_input_combined_sha256:
        raise Phase14PowerError(
            "light curve does not match the frozen campaign-input hash"
        )

    surrogate = block_permuted_surrogate(
        lightcurve,
        block_days=PHASE09_SURROGATE_BLOCK_DAYS,
        seed=seed,
        excluded_events=(),
        gap_factor=DEFAULT_GAP_FACTOR,
    )
    events = search_single_transits(
        surrogate,
        durations=PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        min_snr=PHASE14_PROBE_SNR,
        flatten_window_days=PHASE09_FLATTEN_WINDOW_DAYS,
        max_events=1,
        direction=PHASE14_SEARCH_DIRECTION,
    )
    maximum = max((float(event.snr) for event in events), default=None)
    body = {
        "schema": PHASE14_TRIAL_SCHEMA,
        "target_id": target_id,
        "target_name": lightcurve.target,
        "sector_label": ";".join(
            str(int(value)) for value in lightcurve.metadata.get("sectors", [])
        )
        or "unknown",
        "campaign_input_combined_sha256": campaign_input_combined_sha256,
        "seed": seed,
        "method": GAP_AWARE_METHOD,
        "block_days": PHASE09_SURROGATE_BLOCK_DAYS,
        "gap_factor": DEFAULT_GAP_FACTOR,
        "contiguous_segments": int(
            surrogate.metadata["surrogate_contiguous_segments"]
        ),
        "maximum_dimming_snr": maximum,
        "exceeded_dimming_threshold": (
            maximum is not None and maximum >= PHASE09_MINIMUM_SEARCH_SNR
        ),
        "search_direction": PHASE14_SEARCH_DIRECTION,
        "search_duration_family_days": PHASE09_SEARCH_DURATION_FAMILY_DAYS,
        "flatten_window_days": PHASE09_FLATTEN_WINDOW_DAYS,
        "minimum_search_snr": PHASE09_MINIMUM_SEARCH_SNR,
    }
    return Phase14SurrogateMaximum(
        **body, trial_sha256=canonical_json_sha256(body)
    )


def validate_phase14_surrogate_maximum(
    trial: Phase14SurrogateMaximum | Mapping[str, object],
    *,
    target_id: str,
    target_name: str,
    sector_label: str,
    campaign_input_combined_sha256: str,
) -> dict[str, object]:
    row = trial.to_dict() if isinstance(trial, Phase14SurrogateMaximum) else dict(trial)
    digest = row.pop("trial_sha256", None)
    if digest != canonical_json_sha256(row):
        raise Phase14PowerError("trial_sha256 does not match the trial body")
    if row.get("schema") != PHASE14_TRIAL_SCHEMA:
        raise Phase14PowerError("trial schema is invalid")
    expected_identity = {
        "target_id": target_id,
        "target_name": target_name,
        "sector_label": sector_label,
        "campaign_input_combined_sha256": campaign_input_combined_sha256,
    }
    for key, expected in expected_identity.items():
        if row.get(key) != expected:
            raise Phase14PowerError(
                f"trial {key} differs from the frozen identity"
            )
    seed = row.get("seed")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or seed not in PHASE14_EXTENSION_SEEDS
    ):
        raise Phase14PowerError("trial seed is outside the extension range")
    if (
        row.get("method") != GAP_AWARE_METHOD
        or row.get("search_direction") != PHASE14_SEARCH_DIRECTION
    ):
        raise Phase14PowerError("trial method or search direction is not frozen")
    if (
        tuple(row.get("search_duration_family_days", ()))
        != PHASE09_SEARCH_DURATION_FAMILY_DAYS
    ):
        raise Phase14PowerError("trial duration family is not frozen")
    if not math.isclose(
        _finite(row.get("block_days"), "block_days"),
        PHASE09_SURROGATE_BLOCK_DAYS,
        abs_tol=1e-12,
    ):
        raise Phase14PowerError("trial block_days is not frozen")
    if not math.isclose(
        _finite(row.get("gap_factor"), "gap_factor"),
        DEFAULT_GAP_FACTOR,
        abs_tol=1e-12,
    ):
        raise Phase14PowerError("trial gap_factor is not frozen")
    maximum = row.get("maximum_dimming_snr")
    if maximum is not None and _finite(maximum, "maximum_dimming_snr") < 0:
        raise Phase14PowerError("maximum_dimming_snr must be non-negative")
    expected_exceeded = (
        maximum is not None and float(maximum) >= PHASE09_MINIMUM_SEARCH_SNR
    )
    if row.get("exceeded_dimming_threshold") is not expected_exceeded:
        raise Phase14PowerError("trial threshold flag is inconsistent")
    return {**row, "trial_sha256": digest}


def build_phase14_chunk_receipt(
    trials: Sequence[Phase14SurrogateMaximum | Mapping[str, object]],
    *,
    target_id: str,
    target_name: str,
    sector_label: str,
    campaign_input_combined_sha256: str,
    expected_seeds: Sequence[int],
) -> dict[str, object]:
    seeds = tuple(int(seed) for seed in expected_seeds)
    if seeds not in phase14_seed_chunks():
        raise Phase14PowerError(
            "expected_seeds is not a frozen Phase 0.14 chunk"
        )
    rows = [
        validate_phase14_surrogate_maximum(
            trial,
            target_id=target_id,
            target_name=target_name,
            sector_label=sector_label,
            campaign_input_combined_sha256=campaign_input_combined_sha256,
        )
        for trial in trials
    ]
    if tuple(row["seed"] for row in rows) != seeds:
        raise Phase14PowerError(
            "chunk trials do not match the exact frozen seed order"
        )
    body = {
        "schema": PHASE14_CHUNK_SCHEMA,
        "target_id": target_id,
        "target_name": target_name,
        "sector_label": sector_label,
        "campaign_input_combined_sha256": campaign_input_combined_sha256,
        "first_seed": seeds[0],
        "last_seed": seeds[-1],
        "seed_count": len(seeds),
        "seeds": list(seeds),
        "trial_sha256s": [row["trial_sha256"] for row in rows],
        "trials": rows,
    }
    return {**body, "chunk_sha256": canonical_json_sha256(body)}


def validate_phase14_chunk_receipt(
    receipt: Mapping[str, object],
    *,
    target_id: str,
    target_name: str,
    sector_label: str,
    campaign_input_combined_sha256: str,
) -> dict[str, object]:
    row = dict(receipt)
    digest = row.pop("chunk_sha256", None)
    if digest != canonical_json_sha256(row):
        raise Phase14PowerError("chunk_sha256 does not match the chunk body")
    if row.get("schema") != PHASE14_CHUNK_SCHEMA:
        raise Phase14PowerError("chunk schema is invalid")
    seeds = tuple(row.get("seeds", ()))
    rebuilt = build_phase14_chunk_receipt(
        row.get("trials", ()),
        target_id=target_id,
        target_name=target_name,
        sector_label=sector_label,
        campaign_input_combined_sha256=campaign_input_combined_sha256,
        expected_seeds=seeds,
    )
    if rebuilt != {**row, "chunk_sha256": digest}:
        raise Phase14PowerError("chunk receipt is not canonical")
    return rebuilt


def assemble_phase14_target_calibration(
    *,
    target_id: str,
    target_name: str,
    sector_label: str,
    campaign_input_combined_sha256: str,
    phase09_trials: Sequence[SurrogateTrial],
    extension_chunks: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    old = tuple(sorted(phase09_trials, key=lambda trial: trial.seed))
    if tuple(trial.seed for trial in old) != PHASE09_SURROGATE_SEEDS:
        raise Phase14PowerError(
            "Phase 0.9 trials must be exact seeds 0 through 63"
        )
    for trial in old:
        if trial.target != target_name or trial.sector_label != sector_label:
            raise Phase14PowerError(
                "Phase 0.9 trial identity differs from target"
            )
        if (
            trial.method != GAP_AWARE_METHOD
            or trial.neutralized_events != 0
            or trial.neutralized_points != 0
        ):
            raise Phase14PowerError(
                "Phase 0.9 trial is not the frozen unmasked null"
            )
    validated = [
        validate_phase14_chunk_receipt(
            chunk,
            target_id=target_id,
            target_name=target_name,
            sector_label=sector_label,
            campaign_input_combined_sha256=campaign_input_combined_sha256,
        )
        for chunk in extension_chunks
    ]
    by_first = {int(chunk["first_seed"]): chunk for chunk in validated}
    expected_chunks = phase14_seed_chunks()
    expected_first = {chunk[0] for chunk in expected_chunks}
    if set(by_first) != expected_first or len(by_first) != len(expected_chunks):
        raise Phase14PowerError(
            "target calibration requires every frozen extension chunk exactly once"
        )
    extension_rows = []
    for seeds in expected_chunks:
        chunk = by_first[seeds[0]]
        if tuple(chunk["seeds"]) != seeds:
            raise Phase14PowerError("extension chunk seed coverage is incomplete")
        extension_rows.extend(chunk["trials"])
    maxima = [trial.maximum_dimming_snr for trial in old] + [
        row["maximum_dimming_snr"] for row in extension_rows
    ]
    if len(maxima) != PHASE14_TOTAL_SURROGATES:
        raise Phase14PowerError(
            "assembled target calibration does not contain 1023 maxima"
        )
    body = {
        "schema": PHASE14_TARGET_SCHEMA,
        "target_id": target_id,
        "target_name": target_name,
        "sector_label": sector_label,
        "campaign_input_combined_sha256": campaign_input_combined_sha256,
        "reused_phase09_trials": len(old),
        "extension_trials": len(extension_rows),
        "total_surrogate_trials": len(maxima),
        "minimum_resolvable_familywise_p": 1.0 / (len(maxima) + 1.0),
        "phase09_trial_sha256": canonical_json_sha256(
            [trial.to_dict() for trial in old]
        ),
        "extension_chunk_sha256s": [
            by_first[seeds[0]]["chunk_sha256"] for seeds in expected_chunks
        ],
        "maximum_dimming_snr": maxima,
    }
    return {
        **body,
        "target_calibration_sha256": canonical_json_sha256(body),
    }


def recalibrate_phase14_machine_rows(
    machine_rows: Sequence[BlindCandidateInput],
    target_calibration: Mapping[str, object],
) -> list[BlindCandidateInput]:
    calibration = dict(target_calibration)
    digest = calibration.pop("target_calibration_sha256", None)
    if digest != canonical_json_sha256(calibration):
        raise Phase14PowerError("target_calibration_sha256 does not match")
    maxima = tuple(calibration.get("maximum_dimming_snr", ()))
    if len(maxima) != PHASE14_TOTAL_SURROGATES:
        raise Phase14PowerError(
            "target calibration must contain exactly 1023 maxima"
        )
    target_id = calibration.get("target_id")
    campaign_hash = calibration.get("campaign_input_combined_sha256")
    denominator = float(PHASE14_TOTAL_SURROGATES + 1)
    output: list[BlindCandidateInput] = []
    for row in machine_rows:
        if (
            row.target_id != target_id
            or row.campaign_input_combined_sha256 != campaign_hash
        ):
            raise Phase14PowerError(
                "machine row identity differs from target calibration"
            )
        exceedances = sum(
            maximum is not None and float(maximum) >= float(row.snr)
            for maximum in maxima
        )
        output.append(
            replace(
                row,
                empirical_familywise_p=(1.0 + exceedances) / denominator,
            )
        )
    return output


def audit_phase14_power_restoration(
    *, candidate_family_size: int = 63
) -> dict[str, object]:
    if (
        isinstance(candidate_family_size, bool)
        or not isinstance(candidate_family_size, int)
        or candidate_family_size < 1
    ):
        raise Phase14PowerError(
            "candidate_family_size must be a positive integer"
        )
    p_min = 1.0 / (PHASE14_TOTAL_SURROGATES + 1.0)
    rank_one_q = benjamini_hochberg_qvalues(
        [p_min] + [1.0] * (candidate_family_size - 1)
    )[0]
    minimum_surrogates = math.ceil(
        candidate_family_size / TABLE_FDR_ALPHA
    ) - 1
    payload = {
        "schema": PHASE14_SCHEMA,
        "candidate_family_size": candidate_family_size,
        "surrogate_trials_per_target": PHASE14_TOTAL_SURROGATES,
        "minimum_resolvable_familywise_p": p_min,
        "rank_one_bh_q": rank_one_q,
        "target_familywise_alpha": TARGET_FAMILYWISE_ALPHA,
        "table_fdr_alpha": TABLE_FDR_ALPHA,
        "single_rank_one_signal_passes_target_gate": (
            p_min <= TARGET_FAMILYWISE_ALPHA
        ),
        "single_rank_one_signal_passes_global_bh": (
            rank_one_q <= TABLE_FDR_ALPHA
        ),
        "minimum_surrogates_for_rank_one_resolution": minimum_surrogates,
        "power_restored": (
            p_min <= TARGET_FAMILYWISE_ALPHA
            and rank_one_q <= TABLE_FDR_ALPHA
        ),
    }
    return {**payload, "audit_sha256": canonical_json_sha256(payload)}


def build_phase14_plan_lock(
    *,
    source_commit: str,
    frozen_at_utc: str,
    locked_input_set_sha256: str,
    phase12_candidate_table_sha256: str,
    phase12_campaign_evidence_sha256: str,
    target_count: int = PHASE14_TARGETS,
    candidate_family_size: int = 63,
) -> dict[str, object]:
    if not isinstance(source_commit, str) or _GIT.fullmatch(source_commit) is None:
        raise Phase14PowerError("source_commit must be a lowercase Git SHA")
    if not isinstance(frozen_at_utc, str) or _UTC.fullmatch(frozen_at_utc) is None:
        raise Phase14PowerError(
            "frozen_at_utc must use YYYY-MM-DDTHH:MM:SSZ"
        )
    datetime.strptime(frozen_at_utc, "%Y-%m-%dT%H:%M:%SZ")
    _valid_sha(locked_input_set_sha256, "locked_input_set_sha256")
    _valid_sha(
        phase12_candidate_table_sha256,
        "phase12_candidate_table_sha256",
    )
    _valid_sha(
        phase12_campaign_evidence_sha256,
        "phase12_campaign_evidence_sha256",
    )
    if target_count != PHASE14_TARGETS:
        raise Phase14PowerError(
            "Phase 0.14 requires exactly 64 frozen targets"
        )
    audit = audit_phase14_power_restoration(
        candidate_family_size=candidate_family_size
    )
    if not audit["power_restored"]:
        raise Phase14PowerError(
            "Phase 0.14 plan does not restore rank-one global power"
        )
    body = {
        "schema": PHASE14_PLAN_SCHEMA,
        "source_commit": source_commit,
        "frozen_at_utc": frozen_at_utc,
        "locked_input_set_sha256": locked_input_set_sha256,
        "phase12_candidate_table_sha256": phase12_candidate_table_sha256,
        "phase12_campaign_evidence_sha256": phase12_campaign_evidence_sha256,
        "targets": target_count,
        "reused_phase09_seeds": list(PHASE09_SURROGATE_SEEDS),
        "extension_seed_first": PHASE14_EXTENSION_SEEDS[0],
        "extension_seed_last": PHASE14_EXTENSION_SEEDS[-1],
        "extension_trials_per_target": PHASE14_EXTENSION_TRIALS_PER_TARGET,
        "total_surrogate_trials_per_target": PHASE14_TOTAL_SURROGATES,
        "total_extension_trials": PHASE14_TOTAL_EXTENSION_TRIALS,
        "chunk_size": PHASE14_CHUNK_SIZE,
        "chunk_count_per_target": len(phase14_seed_chunks()),
        "surrogate_method": GAP_AWARE_METHOD,
        "surrogate_block_days": PHASE09_SURROGATE_BLOCK_DAYS,
        "surrogate_gap_factor": DEFAULT_GAP_FACTOR,
        "search_direction_for_extension": PHASE14_SEARCH_DIRECTION,
        "search_duration_family_days": list(
            PHASE09_SEARCH_DURATION_FAMILY_DAYS
        ),
        "flatten_window_days": PHASE09_FLATTEN_WINDOW_DAYS,
        "minimum_search_snr": PHASE09_MINIMUM_SEARCH_SNR,
        "candidate_table_freeze_before_complete": False,
        "thresholds_relaxed": False,
        "network_downloads_allowed": False,
        "power_audit": audit,
    }
    return {**body, "plan_lock_sha256": canonical_json_sha256(body)}
