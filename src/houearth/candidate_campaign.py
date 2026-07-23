from __future__ import annotations
import math
import re
from datetime import datetime
from dataclasses import asdict, dataclass
from numbers import Real
from typing import Iterable, Mapping, Sequence
from .candidate_freeze import BlindCandidateInput
from .core import LightCurve, SingleTransitEvent
from .provenance import canonical_json_sha256
from .surrogates import DEFAULT_GAP_FACTOR, GAP_AWARE_METHOD, SurrogateTrial
PHASE09_CALIBRATION_SCHEMA = 'houearth-target-candidate-calibration-v0.9.0'
PHASE09_CAMPAIGN_EVIDENCE_SCHEMA = 'houearth-blind-candidate-campaign-evidence-v0.9.0'
PHASE09_SURROGATE_SEEDS = tuple(range(64))
PHASE09_SURROGATE_BLOCK_DAYS = 0.5
PHASE09_SEARCH_DURATION_FAMILY_DAYS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)
PHASE09_FLATTEN_WINDOW_DAYS = 1.5
PHASE09_MINIMUM_SEARCH_SNR = 5.0
PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION = 200
PHASE09_ELIGIBLE_TARGET_RULE = 'surrogate_policy == unmasked-null'
PHASE09_CAMPAIGN_LOCK_SCHEMA = 'houearth-blind-real-campaign-lock-v0.9.0'
_SHA256_PATTERN = re.compile('^[0-9a-f]{64}$')
_UTC_PATTERN = re.compile('^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$')

@dataclass(frozen=True)
class CandidateCalibrationReceipt:
    schema: str
    target_id: str
    target_name: str
    sector_label: str
    campaign_input_combined_sha256: str
    search_duration_family_days: tuple[float, ...]
    surrogate_method: str
    surrogate_block_days: float
    surrogate_gap_factor: float
    surrogate_trials: int
    surrogate_trials_without_dimming_maximum: int
    minimum_resolvable_familywise_p: float
    dimming_events: int
    brightening_control_events: int
    derived_machine_events: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

def campaign_input_combined_sha256(lightcurve: LightCurve) -> str:
    """Return the exact cleaned campaign-input array hash recorded at download time."""
    hashes = lightcurve.metadata.get('campaign_input_array_hashes')
    if not isinstance(hashes, dict):
        raise ValueError('light curve is missing campaign_input_array_hashes')
    value = hashes.get('combined_sha256')
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError('light curve campaign-input combined hash is missing or invalid')
    return value

def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f'{name} must be a real number')
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f'{name} must be finite')
    return parsed

def _duration_family(values: Sequence[float]) -> tuple[float, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError('search_duration_family_days must be a numeric sequence')
    durations = tuple((_finite_number(value, 'search duration') for value in values))
    if not durations or any((value <= 0 for value in durations)):
        raise ValueError('search duration family must contain positive values')
    if durations != tuple(sorted(set(durations))):
        raise ValueError('search duration family must be sorted and unique')
    return durations

def _validate_event(event: SingleTransitEvent, *, target_name: str, direction: str, durations: tuple[float, ...]) -> None:
    if event.target != target_name:
        raise ValueError('machine event target does not match the calibrated target')
    if event.direction != direction:
        raise ValueError(f'expected {direction} machine events')
    center = _finite_number(event.center_time_days, 'center_time_days')
    duration = _finite_number(event.duration_days, 'duration_days')
    depth = _finite_number(event.depth, 'depth')
    snr = _finite_number(event.snr, 'snr')
    if center < 0:
        raise ValueError('center_time_days must be non-negative')
    if duration <= 0 or depth <= 0 or snr < 0:
        raise ValueError('event duration/depth must be positive and SNR non-negative')
    if not any((math.isclose(duration, value, rel_tol=0.0, abs_tol=1e-12) for value in durations)):
        raise ValueError('event duration is outside the frozen search-duration family')
    if isinstance(event.local_points, bool) or not isinstance(event.local_points, int):
        raise ValueError('event local_points must be an exact integer')
    if event.local_points < 1:
        raise ValueError('event local_points must be positive')

def _canonical_event_key(event: SingleTransitEvent) -> tuple[object, ...]:
    return (float(event.center_time_days), float(event.duration_days), -float(event.snr), -float(event.depth), int(event.local_points), event.direction)

def _validate_surrogate_trials(trials: Iterable[SurrogateTrial], *, target_name: str, sector_label: str) -> tuple[SurrogateTrial, ...]:
    materialized = tuple(trials)
    if len(materialized) != len(PHASE09_SURROGATE_SEEDS):
        raise ValueError('Phase 0.9 requires exactly 64 surrogate trials per campaign input')
    seeds: list[int] = []
    for trial in materialized:
        if trial.target != target_name or trial.sector_label != sector_label:
            raise ValueError('surrogate target or sector does not match the campaign input')
        if trial.method != GAP_AWARE_METHOD:
            raise ValueError('Phase 0.9 requires the frozen gap-aware surrogate method')
        block_days = _finite_number(trial.block_days, 'surrogate block_days')
        if not math.isclose(block_days, PHASE09_SURROGATE_BLOCK_DAYS, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError('Phase 0.9 surrogate block length is frozen at 0.5 days')
        gap_factor = _finite_number(trial.gap_factor, 'surrogate gap_factor')
        if not math.isclose(gap_factor, DEFAULT_GAP_FACTOR, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError('Phase 0.9 surrogate gap factor is frozen at 3.5')
        integer_fields = {'contiguous_segments': trial.contiguous_segments, 'neutralized_events': trial.neutralized_events, 'neutralized_points': trial.neutralized_points, 'dimming_events': trial.dimming_events, 'brightening_events': trial.brightening_events}
        for field, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f'surrogate {field} must be a non-negative exact integer')
        if trial.neutralized_events != 0 or trial.neutralized_points != 0:
            raise ValueError('Phase 0.9 candidate calibration requires an unmasked null')
        if trial.contiguous_segments < 1:
            raise ValueError('surrogate trial must retain at least one observing segment')
        if isinstance(trial.seed, bool) or not isinstance(trial.seed, int):
            raise ValueError('surrogate seed must be an exact integer')
        if not isinstance(trial.exceeded_dimming_threshold, bool) or not isinstance(trial.exceeded_brightening_threshold, bool):
            raise ValueError('surrogate threshold flags must be booleans')
        seeds.append(trial.seed)
        maximum = trial.maximum_dimming_snr
        maximum_brightening = trial.maximum_brightening_snr
        if maximum is not None and _finite_number(maximum, 'maximum_dimming_snr') < 0:
            raise ValueError('surrogate maximum dimming SNR must be non-negative')
        if maximum_brightening is not None and _finite_number(maximum_brightening, 'maximum_brightening_snr') < 0:
            raise ValueError('surrogate maximum brightening SNR must be non-negative')
        dimming_exceeded = maximum is not None and float(maximum) >= PHASE09_MINIMUM_SEARCH_SNR
        brightening_exceeded = maximum_brightening is not None and float(maximum_brightening) >= PHASE09_MINIMUM_SEARCH_SNR
        if trial.exceeded_dimming_threshold != dimming_exceeded:
            raise ValueError('surrogate dimming threshold flag is inconsistent')
        if trial.exceeded_brightening_threshold != brightening_exceeded:
            raise ValueError('surrogate brightening threshold flag is inconsistent')
        if (trial.dimming_events > 0) != dimming_exceeded:
            raise ValueError('surrogate dimming event count is inconsistent')
        if (trial.brightening_events > 0) != brightening_exceeded:
            raise ValueError('surrogate brightening event count is inconsistent')
    if tuple(sorted(seeds)) != PHASE09_SURROGATE_SEEDS or len(set(seeds)) != len(seeds):
        raise ValueError('Phase 0.9 surrogate seeds must be exactly 0 through 63')
    return tuple(sorted(materialized, key=lambda trial: trial.seed))

def _matched_brightening_control(event: SingleTransitEvent, controls: Sequence[SingleTransitEvent]) -> tuple[float | None, float | None]:
    if not controls:
        return (None, None)
    available = sorted({float(control.duration_days) for control in controls})
    duration = min(available, key=lambda value: (abs(value - float(event.duration_days)), value))
    values = [float(control.snr) for control in controls if math.isclose(float(control.duration_days), duration, rel_tol=0.0, abs_tol=1e-12)]
    return (duration, max(values))

def build_blind_candidate_inputs(*, target_id: str, target_name: str, sector_label: str, campaign_input_sha256: str, search_duration_family_days: Sequence[float], dimming_events: Iterable[SingleTransitEvent], brightening_control_events: Iterable[SingleTransitEvent], surrogate_trials: Iterable[SurrogateTrial]) -> tuple[list[BlindCandidateInput], CandidateCalibrationReceipt]:
    """Derive auditable Phase 0.8 machine rows from one real campaign input.

    The empirical p-value uses every one of the 64 full-search surrogate trials.
    A surrogate with no dimming maximum is retained in the denominator as a
    non-exceedance rather than silently discarded.
    """
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError('target_id must be a non-empty string')
    if not isinstance(target_name, str) or not target_name.strip():
        raise ValueError('target_name must be a non-empty string')
    if not isinstance(sector_label, str) or not sector_label.strip():
        raise ValueError('sector_label must be a non-empty string')
    if not isinstance(campaign_input_sha256, str) or _SHA256_PATTERN.fullmatch(campaign_input_sha256) is None:
        raise ValueError('campaign_input_sha256 must be a lowercase SHA-256')
    durations = _duration_family(search_duration_family_days)
    if durations != PHASE09_SEARCH_DURATION_FAMILY_DAYS:
        raise ValueError('Phase 0.9 search-duration family is frozen')
    dimming = tuple(dimming_events)
    controls = tuple(brightening_control_events)
    for event in dimming:
        _validate_event(event, target_name=target_name, direction='dimming', durations=durations)
    for event in controls:
        _validate_event(event, target_name=target_name, direction='brightening', durations=durations)
    dimming = tuple(sorted(dimming, key=_canonical_event_key))
    controls = tuple(sorted(controls, key=_canonical_event_key))
    null_trials = _validate_surrogate_trials(surrogate_trials, target_name=target_name, sector_label=sector_label)
    maxima = [None if trial.maximum_dimming_snr is None else float(trial.maximum_dimming_snr) for trial in null_trials]
    rows: list[BlindCandidateInput] = []
    denominator = 1.0 + len(maxima)
    for source_index, event in enumerate(dimming):
        exceedances = sum((maximum is not None and maximum >= float(event.snr) for maximum in maxima))
        p_value = (1.0 + exceedances) / denominator
        _, control_snr = _matched_brightening_control(event, controls)
        margin = None if control_snr is None else float(event.snr - control_snr)
        rows.append(BlindCandidateInput(target_id=target_id, target_name=target_name, sector_label=sector_label, center_time_days=float(event.center_time_days), duration_days=float(event.duration_days), depth=float(event.depth), snr=float(event.snr), empirical_familywise_p=float(p_value), matched_brightening_snr=control_snr, snr_above_matched_control=margin, campaign_input_combined_sha256=campaign_input_sha256, search_duration_family_days=durations, source_event_index=source_index, event_direction='dimming'))
    receipt = CandidateCalibrationReceipt(schema=PHASE09_CALIBRATION_SCHEMA, target_id=target_id, target_name=target_name, sector_label=sector_label, campaign_input_combined_sha256=campaign_input_sha256, search_duration_family_days=durations, surrogate_method=GAP_AWARE_METHOD, surrogate_block_days=PHASE09_SURROGATE_BLOCK_DAYS, surrogate_gap_factor=DEFAULT_GAP_FACTOR, surrogate_trials=len(null_trials), surrogate_trials_without_dimming_maximum=sum((maximum is None for maximum in maxima)), minimum_resolvable_familywise_p=1.0 / denominator, dimming_events=len(dimming), brightening_control_events=len(controls), derived_machine_events=len(rows))
    return (rows, receipt)

def freeze_candidate_campaign_evidence(*, source_commit: str, frozen_at_utc: str, campaign_lock: Mapping[str, object], target_calibrations: Sequence[Mapping[str, object]], candidate_evidence: Mapping[str, object]) -> dict[str, object]:
    """Bind the campaign lock, raw calibration inputs, and Phase 0.8 evidence."""
    if not isinstance(source_commit, str) or re.fullmatch('[0-9a-f]{40}', source_commit) is None:
        raise ValueError('source_commit must be a lowercase 40-character Git SHA')
    if not isinstance(frozen_at_utc, str) or _UTC_PATTERN.fullmatch(frozen_at_utc) is None:
        raise ValueError('frozen_at_utc must use YYYY-MM-DDTHH:MM:SSZ')
    try:
        datetime.strptime(frozen_at_utc, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError as exc:
        raise ValueError('frozen_at_utc is not a valid UTC timestamp') from exc
    lock = dict(campaign_lock)
    lock_hash = lock.get('campaign_lock_sha256')
    if not isinstance(lock_hash, str) or _SHA256_PATTERN.fullmatch(lock_hash) is None:
        raise ValueError('campaign lock is missing campaign_lock_sha256')
    expected_lock_hash = canonical_json_sha256({key: value for key, value in lock.items() if key != 'campaign_lock_sha256'})
    if lock_hash != expected_lock_hash:
        raise ValueError('campaign_lock_sha256 does not match the campaign lock')
    if lock.get('source_commit') != source_commit:
        raise ValueError('campaign lock source commit differs from the evidence source')
    if lock.get('frozen_at_utc') != frozen_at_utc:
        raise ValueError('campaign lock freeze time differs from the evidence freeze time')
    evidence = dict(candidate_evidence)
    if evidence.get('source_commit') != source_commit:
        raise ValueError('candidate evidence source commit differs from the campaign')
    if evidence.get('frozen_at_utc') != frozen_at_utc:
        raise ValueError('candidate evidence freeze time differs from the campaign')
    targets = [dict(target) for target in target_calibrations]
    targets.sort(key=lambda target: (str(target.get('target_id', '')), str(target.get('campaign_input_combined_sha256', ''))))
    payload = {'schema': PHASE09_CAMPAIGN_EVIDENCE_SCHEMA, 'source_commit': source_commit, 'frozen_at_utc': frozen_at_utc, 'campaign_lock': lock, 'target_calibrations': targets, 'candidate_evidence': evidence}
    return {**payload, 'package_sha256': canonical_json_sha256(payload)}
