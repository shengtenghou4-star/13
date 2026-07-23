from __future__ import annotations
import math
import re
from datetime import datetime
from dataclasses import asdict, dataclass
from numbers import Real
from typing import Mapping, Sequence
from .candidate_campaign import PHASE09_CALIBRATION_SCHEMA, PHASE09_CAMPAIGN_EVIDENCE_SCHEMA, PHASE09_CAMPAIGN_LOCK_SCHEMA, PHASE09_ELIGIBLE_TARGET_RULE, PHASE09_FLATTEN_WINDOW_DAYS, PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION, PHASE09_MINIMUM_SEARCH_SNR, PHASE09_SEARCH_DURATION_FAMILY_DAYS, PHASE09_SURROGATE_BLOCK_DAYS, PHASE09_SURROGATE_SEEDS
from .candidate_evidence import validate_candidate_evidence
from .provenance import canonical_json_sha256
from .surrogates import DEFAULT_GAP_FACTOR, GAP_AWARE_METHOD
_SHA256 = re.compile('^[0-9a-f]{64}$')
_GIT_SHA = re.compile('^[0-9a-f]{40}$')
_UTC = re.compile('^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$')
_PACKAGE_FIELDS = {'schema', 'source_commit', 'frozen_at_utc', 'campaign_lock', 'target_calibrations', 'candidate_evidence', 'package_sha256'}
_LOCK_FIELDS = {'schema', 'source_commit', 'frozen_at_utc', 'manifest_sha256', 'eligible_target_rule', 'excluded_targets', 'search_duration_family_days', 'flatten_window_days', 'minimum_search_snr', 'maximum_machine_events_per_direction', 'surrogate_method', 'surrogate_seeds', 'surrogate_block_days', 'surrogate_gap_factor', 'targets', 'campaign_lock_sha256'}
_LOCK_TARGET_FIELDS = {'target_id', 'query', 'intended_role', 'sector_label', 'campaign_input_combined_sha256', 'query_provenance_sha256', 'product_provenance_sha256'}
_EXCLUDED_TARGET_FIELDS = {'target_id', 'query', 'reason'}
_TARGET_FIELDS = {'target_id', 'target_name', 'sector_label', 'campaign_input_combined_sha256', 'search_duration_family_days', 'dimming_events', 'brightening_control_events', 'surrogate_trials', 'calibration_receipt'}
_EVENT_FIELDS = {'target', 'center_time_days', 'duration_days', 'depth', 'snr', 'local_points', 'direction'}
_SURROGATE_FIELDS = {'target', 'sector_label', 'seed', 'method', 'block_days', 'contiguous_segments', 'gap_factor', 'neutralized_events', 'neutralized_points', 'dimming_events', 'brightening_events', 'maximum_dimming_snr', 'maximum_brightening_snr', 'exceeded_dimming_threshold', 'exceeded_brightening_threshold'}
_RECEIPT_FIELDS = {'schema', 'target_id', 'target_name', 'sector_label', 'campaign_input_combined_sha256', 'search_duration_family_days', 'surrogate_method', 'surrogate_block_days', 'surrogate_gap_factor', 'surrogate_trials', 'surrogate_trials_without_dimming_maximum', 'minimum_resolvable_familywise_p', 'dimming_events', 'brightening_control_events', 'derived_machine_events'}

@dataclass(frozen=True)
class CandidateCampaignValidationReport:
    protocol: str
    accepted: bool
    targets: int
    surrogate_trials: int
    machine_events: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

class CandidateCampaignValidationError(ValueError):

    def __init__(self, report: CandidateCampaignValidationReport):
        self.report = report
        super().__init__('; '.join(report.errors))

def _closed(row: Mapping[object, object], expected: set[str], label: str, errors: list[str]) -> None:
    keys = {key for key in row if isinstance(key, str)}
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    extra.extend((repr(key) for key in row if not isinstance(key, str)))
    if missing:
        errors.append(f"{label} is missing fields: {', '.join(missing)}")
    if extra:
        errors.append(f"{label} contains undeclared fields: {', '.join(extra)}")

def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None

def _same(left: object, right: object) -> bool:
    a, b = (_number(left), _number(right))
    if a is None or b is None:
        return left is None and right is None
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)

def _exact_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value

def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None

def _valid_utc(value: object) -> bool:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        return False
    try:
        datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return False
    return True

def _hash_without(row: Mapping[object, object], excluded: str) -> str | None:
    try:
        return canonical_json_sha256({key: value for key, value in row.items() if key != excluded})
    except (TypeError, ValueError, OverflowError):
        return None

def _duration_family(value: object) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    parsed = [_number(item) for item in value]
    if not parsed or any((item is None or item <= 0 for item in parsed)):
        return ()
    result = tuple((float(item) for item in parsed))
    return result if result == tuple(sorted(set(result))) else ()

def _event(row: Mapping[str, object], target: str, direction: str, durations: tuple[float, ...]) -> dict[str, object] | None:
    if row.get('target') != target or row.get('direction') != direction:
        return None
    center = _number(row.get('center_time_days'))
    duration = _number(row.get('duration_days'))
    depth = _number(row.get('depth'))
    snr = _number(row.get('snr'))
    points = row.get('local_points')
    if center is None or duration is None or depth is None or (snr is None) or (center < 0) or (duration <= 0) or (depth <= 0) or (snr < 0) or isinstance(points, bool) or (not isinstance(points, int)) or (points < 1) or (not any((math.isclose(duration, item, rel_tol=0.0, abs_tol=1e-12) for item in durations))):
        return None
    return {'target': target, 'center_time_days': center, 'duration_days': duration, 'depth': depth, 'snr': snr, 'local_points': points, 'direction': direction}

def _event_key(row: Mapping[str, object]) -> tuple[object, ...]:
    return (float(row['center_time_days']), float(row['duration_days']), -float(row['snr']), -float(row['depth']), int(row['local_points']), row['direction'])

def _control_snr(event: Mapping[str, object], controls: Sequence[Mapping[str, object]]) -> float | None:
    if not controls:
        return None
    available = sorted({float(row['duration_days']) for row in controls})
    duration = min(available, key=lambda item: (abs(item - float(event['duration_days'])), item))
    return max((float(row['snr']) for row in controls if math.isclose(float(row['duration_days']), duration, rel_tol=0.0, abs_tol=1e-12)))

__all__ = [name for name in globals() if not name.startswith("__")]
