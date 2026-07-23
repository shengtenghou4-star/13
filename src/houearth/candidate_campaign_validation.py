from ._candidate_campaign_validation_support import *

def validate_candidate_campaign_evidence(payload: Mapping[str, object]) -> CandidateCampaignValidationReport:
    errors: list[str] = []
    _closed(payload, _PACKAGE_FIELDS, 'campaign evidence', errors)
    if payload.get('schema') != PHASE09_CAMPAIGN_EVIDENCE_SCHEMA:
        errors.append('campaign evidence schema is missing or inconsistent')
    source_commit = payload.get('source_commit')
    if not isinstance(source_commit, str) or _GIT_SHA.fullmatch(source_commit) is None:
        errors.append('campaign evidence source commit is invalid')
    frozen_at = payload.get('frozen_at_utc')
    if not _valid_utc(frozen_at):
        errors.append('campaign evidence freeze timestamp is invalid')
    lock_value = payload.get('campaign_lock')
    lock = lock_value if isinstance(lock_value, Mapping) else {}
    if not lock:
        errors.append('campaign lock is missing or malformed')
    else:
        _closed(lock, _LOCK_FIELDS, 'campaign lock', errors)
    lock_hash = lock.get('campaign_lock_sha256')
    expected_lock_hash = _hash_without(lock, 'campaign_lock_sha256')
    if not _valid_sha256(lock_hash) or lock_hash != expected_lock_hash:
        errors.append('campaign_lock_sha256 does not match the campaign lock')
    if lock.get('schema') != PHASE09_CAMPAIGN_LOCK_SCHEMA:
        errors.append('campaign lock schema is inconsistent')
    if lock.get('source_commit') != source_commit:
        errors.append('campaign lock and package source commits differ')
    if lock.get('frozen_at_utc') != frozen_at:
        errors.append('campaign lock and package freeze timestamps differ')
    if not _valid_sha256(lock.get('manifest_sha256')):
        errors.append('campaign lock manifest SHA-256 is invalid')
    if lock.get('eligible_target_rule') != PHASE09_ELIGIBLE_TARGET_RULE:
        errors.append('campaign lock eligible-target rule is inconsistent')
    if lock.get('surrogate_method') != GAP_AWARE_METHOD:
        errors.append('campaign lock surrogate method is inconsistent')
    if lock.get('surrogate_seeds') != list(PHASE09_SURROGATE_SEEDS):
        errors.append('campaign lock surrogate seed grid is inconsistent')
    if not _same(lock.get('surrogate_block_days'), PHASE09_SURROGATE_BLOCK_DAYS):
        errors.append('campaign lock surrogate block length is inconsistent')
    if not _same(lock.get('surrogate_gap_factor'), DEFAULT_GAP_FACTOR):
        errors.append('campaign lock surrogate gap factor is inconsistent')
    if not _same(lock.get('flatten_window_days'), PHASE09_FLATTEN_WINDOW_DAYS):
        errors.append('campaign lock flattening window is inconsistent')
    if not _same(lock.get('minimum_search_snr'), PHASE09_MINIMUM_SEARCH_SNR):
        errors.append('campaign lock minimum search SNR is inconsistent')
    if lock.get('maximum_machine_events_per_direction') != PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION:
        errors.append('campaign lock maximum machine-event count is inconsistent')
    durations = _duration_family(lock.get('search_duration_family_days'))
    if durations != PHASE09_SEARCH_DURATION_FAMILY_DAYS:
        errors.append('campaign lock search-duration family is inconsistent')
    excluded_value = lock.get('excluded_targets')
    excluded_targets = list(excluded_value) if isinstance(excluded_value, Sequence) and (not isinstance(excluded_value, (str, bytes))) else []
    if not isinstance(excluded_value, Sequence) or isinstance(excluded_value, (str, bytes)):
        errors.append('campaign lock excluded_targets is malformed')
    excluded_ids: set[str] = set()
    for index, row in enumerate(excluded_targets):
        label = f'campaign lock excluded target {index}'
        if not isinstance(row, Mapping):
            errors.append(f'{label} is not an object')
            continue
        _closed(row, _EXCLUDED_TARGET_FIELDS, label, errors)
        values = (row.get('target_id'), row.get('query'), row.get('reason'))
        if not all((isinstance(value, str) and value.strip() for value in values)):
            errors.append(f'{label} has invalid identity or reason')
            continue
        if row['target_id'] in excluded_ids:
            errors.append(f"{label} repeats target_id {row['target_id']}")
        excluded_ids.add(row['target_id'])
    lock_targets_value = lock.get('targets')
    lock_targets = list(lock_targets_value) if isinstance(lock_targets_value, Sequence) and (not isinstance(lock_targets_value, (str, bytes))) else []
    if not isinstance(lock_targets_value, Sequence) or isinstance(lock_targets_value, (str, bytes)):
        errors.append('campaign lock targets is malformed')
    lock_map: dict[str, Mapping[str, object]] = {}
    canonical_lock_keys: list[tuple[str, str]] = []
    for index, row in enumerate(lock_targets):
        label = f'campaign lock target {index}'
        if not isinstance(row, Mapping):
            errors.append(f'{label} is not an object')
            continue
        _closed(row, _LOCK_TARGET_FIELDS, label, errors)
        target_id = row.get('target_id')
        query = row.get('query')
        role = row.get('intended_role')
        sector = row.get('sector_label')
        campaign_hash = row.get('campaign_input_combined_sha256')
        if not all((isinstance(value, str) and value.strip() for value in (target_id, query, role, sector))):
            errors.append(f'{label} has invalid target identity')
            continue
        for field in ('campaign_input_combined_sha256', 'query_provenance_sha256', 'product_provenance_sha256'):
            if not _valid_sha256(row.get(field)):
                errors.append(f'{label} field {field} is invalid')
        if target_id in lock_map:
            errors.append(f'{label} repeats target_id {target_id}')
        else:
            lock_map[target_id] = row
        if target_id in excluded_ids:
            errors.append(f'{label} is also listed as excluded')
        canonical_lock_keys.append((target_id, str(campaign_hash)))
    if canonical_lock_keys != sorted(canonical_lock_keys):
        errors.append('campaign lock targets are not in canonical order')
    calibration_value = payload.get('target_calibrations')
    calibrations = list(calibration_value) if isinstance(calibration_value, Sequence) and (not isinstance(calibration_value, (str, bytes))) else []
    expected_rows: dict[tuple[str, str, int], dict[str, object]] = {}
    total_surrogates = 0
    seen: set[str] = set()
    calibration_keys: list[tuple[str, str]] = []
    for index, value in enumerate(calibrations):
        label = f'target calibration {index}'
        if not isinstance(value, Mapping):
            errors.append(f'{label} is not an object')
            continue
        _closed(value, _TARGET_FIELDS, label, errors)
        target_id = value.get('target_id')
        target_name = value.get('target_name')
        sector = value.get('sector_label')
        campaign_hash = value.get('campaign_input_combined_sha256')
        if not all((isinstance(item, str) and item for item in (target_id, target_name, sector))):
            errors.append(f'{label} has invalid target identity')
            continue
        if target_id in seen:
            errors.append(f'{label} repeats target_id {target_id}')
        seen.add(target_id)
        calibration_keys.append((target_id, str(campaign_hash)))
        if not _valid_sha256(campaign_hash):
            errors.append(f'{label} has invalid campaign input SHA-256')
            continue
        lock_row = lock_map.get(target_id)
        if not isinstance(lock_row, Mapping) or (lock_row.get('query'), lock_row.get('sector_label'), lock_row.get('campaign_input_combined_sha256')) != (target_name, sector, campaign_hash):
            errors.append(f'{label} identity differs from the campaign lock')
        if _duration_family(value.get('search_duration_family_days')) != durations:
            errors.append(f'{label} search-duration family differs from campaign lock')
        parsed_events: dict[str, list[dict[str, object]]] = {}
        for field, direction in (('dimming_events', 'dimming'), ('brightening_control_events', 'brightening')):
            raw = value.get(field)
            rows = list(raw) if isinstance(raw, Sequence) and (not isinstance(raw, (str, bytes))) else []
            parsed: list[dict[str, object]] = []
            for event_index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    errors.append(f'{label} {field} {event_index} is not an object')
                    continue
                _closed(row, _EVENT_FIELDS, f'{label} {field} {event_index}', errors)
                result = _event(row, target_name, direction, durations)
                if result is None:
                    errors.append(f'{label} {field} {event_index} is invalid')
                else:
                    parsed.append(result)
            parsed_events[field] = sorted(parsed, key=_event_key)
        surrogate_value = value.get('surrogate_trials')
        surrogate_rows = list(surrogate_value) if isinstance(surrogate_value, Sequence) and (not isinstance(surrogate_value, (str, bytes))) else []
        if not isinstance(surrogate_value, Sequence) or isinstance(surrogate_value, (str, bytes)):
            errors.append(f'{label} surrogate_trials is malformed')
        total_surrogates += len(surrogate_rows)
        maxima_by_seed: dict[int, float | None] = {}
        for trial_index, row in enumerate(surrogate_rows):
            trial_label = f'{label} surrogate trial {trial_index}'
            if not isinstance(row, Mapping):
                errors.append(f'{trial_label} is not an object')
                continue
            _closed(row, _SURROGATE_FIELDS, trial_label, errors)
            seed = row.get('seed')
            maximum = row.get('maximum_dimming_snr')
            maximum_brightening = row.get('maximum_brightening_snr')
            maximum_value = None if maximum is None else _number(maximum)
            brightening_value = None if maximum_brightening is None else _number(maximum_brightening)
            counts = {field: _exact_nonnegative_int(row.get(field)) for field in ('contiguous_segments', 'neutralized_events', 'neutralized_points', 'dimming_events', 'brightening_events')}
            valid = row.get('target') == target_name and row.get('sector_label') == sector and (row.get('method') == GAP_AWARE_METHOD) and _same(row.get('block_days'), PHASE09_SURROGATE_BLOCK_DAYS) and _same(row.get('gap_factor'), DEFAULT_GAP_FACTOR) and (counts['neutralized_events'] == 0) and (counts['neutralized_points'] == 0) and (counts['contiguous_segments'] is not None) and (counts['contiguous_segments'] >= 1) and isinstance(seed, int) and (not isinstance(seed, bool)) and (maximum is None or (maximum_value is not None and maximum_value >= 0)) and (maximum_brightening is None or (brightening_value is not None and brightening_value >= 0)) and isinstance(row.get('exceeded_dimming_threshold'), bool) and isinstance(row.get('exceeded_brightening_threshold'), bool) and (counts['dimming_events'] is not None) and (counts['brightening_events'] is not None)
            if valid:
                dimming_exceeded = maximum_value is not None and maximum_value >= PHASE09_MINIMUM_SEARCH_SNR
                brightening_exceeded = brightening_value is not None and brightening_value >= PHASE09_MINIMUM_SEARCH_SNR
                valid = row.get('exceeded_dimming_threshold') == dimming_exceeded and row.get('exceeded_brightening_threshold') == brightening_exceeded and ((counts['dimming_events'] > 0) == dimming_exceeded) and ((counts['brightening_events'] > 0) == brightening_exceeded)
            if not valid or seed in maxima_by_seed:
                errors.append(f'{trial_label} is invalid')
            else:
                maxima_by_seed[seed] = maximum_value
        if tuple(sorted(maxima_by_seed)) != PHASE09_SURROGATE_SEEDS:
            errors.append(f'{label} does not contain the exact 64-trial seed grid')
        maxima = [maxima_by_seed.get(seed) for seed in PHASE09_SURROGATE_SEEDS]
        dimming = parsed_events['dimming_events']
        controls = parsed_events['brightening_control_events']
        for source_index, event in enumerate(dimming):
            exceedances = sum((maximum is not None and maximum >= float(event['snr']) for maximum in maxima))
            p_value = (1.0 + exceedances) / 65.0
            control = _control_snr(event, controls)
            key = (target_id, campaign_hash, source_index)
            expected_rows[key] = {'target_id': target_id, 'target_name': target_name, 'sector_label': sector, 'center_time_days': event['center_time_days'], 'duration_days': event['duration_days'], 'depth': event['depth'], 'snr': event['snr'], 'empirical_familywise_p': p_value, 'matched_brightening_snr': control, 'snr_above_matched_control': None if control is None else float(event['snr']) - control, 'campaign_input_combined_sha256': campaign_hash, 'search_duration_family_days': list(durations), 'source_event_index': source_index, 'event_direction': 'dimming'}
        receipt = value.get('calibration_receipt')
        if not isinstance(receipt, Mapping):
            errors.append(f'{label} calibration receipt is missing or inconsistent')
        else:
            _closed(receipt, _RECEIPT_FIELDS, f'{label} calibration receipt', errors)
            checks = {'schema': PHASE09_CALIBRATION_SCHEMA, 'target_id': target_id, 'target_name': target_name, 'sector_label': sector, 'campaign_input_combined_sha256': campaign_hash, 'search_duration_family_days': list(durations), 'surrogate_method': GAP_AWARE_METHOD, 'surrogate_trials': 64, 'surrogate_trials_without_dimming_maximum': sum((maximum is None for maximum in maxima)), 'dimming_events': len(dimming), 'brightening_control_events': len(controls), 'derived_machine_events': len(dimming)}
            for field, expected in checks.items():
                value_seen = receipt.get(field)
                if field == 'search_duration_family_days':
                    valid = isinstance(value_seen, Sequence) and (not isinstance(value_seen, (str, bytes))) and (tuple(value_seen) == tuple(expected))
                else:
                    valid = value_seen == expected
                if not valid:
                    errors.append(f'{label} calibration receipt field {field} is inconsistent')
            if not _same(receipt.get('surrogate_block_days'), PHASE09_SURROGATE_BLOCK_DAYS):
                errors.append(f'{label} calibration receipt block length is inconsistent')
            if not _same(receipt.get('surrogate_gap_factor'), DEFAULT_GAP_FACTOR):
                errors.append(f'{label} calibration receipt gap factor is inconsistent')
            if not _same(receipt.get('minimum_resolvable_familywise_p'), 1.0 / 65.0):
                errors.append(f'{label} calibration p-value resolution is inconsistent')
    if set(lock_map) != seen:
        errors.append('campaign lock targets do not match target calibrations')
    if calibration_keys != sorted(calibration_keys):
        errors.append('target calibrations are not in canonical order')
    if [key[0] for key in calibration_keys] != list(lock_map):
        errors.append('target calibration order differs from campaign lock order')
    evidence_value = payload.get('candidate_evidence')
    evidence = evidence_value if isinstance(evidence_value, Mapping) else {}
    if not evidence:
        errors.append('candidate_evidence is missing or malformed')
    else:
        try:
            validate_candidate_evidence(evidence)
        except Exception as exc:
            report = getattr(exc, 'report', None)
            if report is None:
                errors.append('candidate_evidence validation crashed')
            else:
                errors.extend((f'candidate_evidence: {item}' for item in report.errors))
    if evidence.get('source_commit') != payload.get('source_commit'):
        errors.append('candidate evidence and campaign source commits differ')
    if evidence.get('frozen_at_utc') != payload.get('frozen_at_utc'):
        errors.append('candidate evidence and campaign freeze timestamps differ')
    observed_value = evidence.get('machine_events')
    observed_rows = list(observed_value) if isinstance(observed_value, Sequence) and (not isinstance(observed_value, (str, bytes))) else []
    observed: dict[tuple[str, str, int], Mapping[str, object]] = {}
    for row in observed_rows:
        if not isinstance(row, Mapping):
            continue
        key = (row.get('target_id'), row.get('campaign_input_combined_sha256'), row.get('source_event_index'))
        if isinstance(key[0], str) and isinstance(key[1], str) and isinstance(key[2], int) and (not isinstance(key[2], bool)):
            if key in observed:
                errors.append(f'candidate evidence repeats machine event identity {key[0]}:{key[2]}')
            observed[key] = row
    if set(observed) != set(expected_rows):
        errors.append('derived machine event identities do not match raw calibration inputs')
    numeric = {'center_time_days', 'duration_days', 'depth', 'snr', 'empirical_familywise_p', 'matched_brightening_snr', 'snr_above_matched_control'}
    for key, expected in expected_rows.items():
        row = observed.get(key)
        if row is None:
            continue
        for field, value in expected.items():
            if field in numeric:
                valid = _same(row.get(field), value)
            elif field == 'search_duration_family_days':
                raw = row.get(field)
                valid = isinstance(raw, Sequence) and (not isinstance(raw, (str, bytes))) and (tuple(raw) == tuple(value))
            else:
                valid = row.get(field) == value
            if not valid:
                errors.append(f'{key[0]} event {key[2]} field {field} is inconsistent')
    package_hash = payload.get('package_sha256')
    expected_hash = _hash_without(payload, 'package_sha256')
    if not _valid_sha256(package_hash) or package_hash != expected_hash:
        errors.append('campaign evidence package SHA-256 is missing or inconsistent')
    report = CandidateCampaignValidationReport(protocol='HOU-EARTH Phase 0.9 blind real-campaign calibration evidence', accepted=not errors, targets=len(calibrations), surrogate_trials=total_surrogates, machine_events=len(observed_rows), errors=tuple(errors))
    if errors:
        raise CandidateCampaignValidationError(report)
    return report
