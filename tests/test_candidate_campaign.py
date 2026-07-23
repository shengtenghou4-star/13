import math
import numpy as np
import pytest
from houearth.candidate_campaign import PHASE09_SURROGATE_SEEDS, build_blind_candidate_inputs, campaign_input_combined_sha256
from houearth.core import LightCurve, SingleTransitEvent
from houearth.surrogates import GAP_AWARE_METHOD, SurrogateTrial
DURATIONS = (0.052, 0.08, 0.104, 0.116, 0.16, 0.232)
HASH = 'a' * 64

def event(center: float, duration: float, snr: float, *, direction: str, depth: float=0.0001) -> SingleTransitEvent:
    return SingleTransitEvent(target='SYNTHETIC STAR', center_time_days=center, duration_days=duration, depth=depth, snr=snr, local_points=8, direction=direction)

def surrogates(maxima: list[float | None] | None=None, *, method: str=GAP_AWARE_METHOD, neutralized_events: int=0) -> list[SurrogateTrial]:
    values = maxima if maxima is not None else [5.0] * 64
    return [SurrogateTrial(target='SYNTHETIC STAR', sector_label='1', seed=seed, method=method, block_days=0.5, contiguous_segments=2, gap_factor=3.5, neutralized_events=neutralized_events, neutralized_points=0, dimming_events=1 if values[seed] is not None and values[seed] >= 5.0 else 0, brightening_events=0, maximum_dimming_snr=values[seed], maximum_brightening_snr=4.0, exceeded_dimming_threshold=values[seed] is not None and values[seed] >= 5.0, exceeded_brightening_threshold=False) for seed in PHASE09_SURROGATE_SEEDS]

def build(dimming: list[SingleTransitEvent], controls: list[SingleTransitEvent], nulls: list[SurrogateTrial] | None=None):
    return build_blind_candidate_inputs(target_id='synthetic-star', target_name='SYNTHETIC STAR', sector_label='1', campaign_input_sha256=HASH, search_duration_family_days=DURATIONS, dimming_events=dimming, brightening_control_events=controls, surrogate_trials=surrogates() if nulls is None else nulls)

def test_real_event_rows_use_add_one_familywise_p_and_matched_control() -> None:
    maxima = [5.0] * 62 + [10.0, 11.0]
    rows, receipt = build([event(8.0, 0.08, 10.0, direction='dimming')], [event(2.0, 0.08, 8.0, direction='brightening'), event(3.0, 0.08, 9.0, direction='brightening'), event(4.0, 0.16, 20.0, direction='brightening')], surrogates(maxima))
    assert len(rows) == 1
    assert math.isclose(rows[0].empirical_familywise_p, 3.0 / 65.0)
    assert rows[0].matched_brightening_snr == 9.0
    assert rows[0].snr_above_matched_control == 1.0
    assert receipt.surrogate_trials == 64
    assert math.isclose(receipt.minimum_resolvable_familywise_p, 1.0 / 65.0)

def test_missing_surrogate_maxima_remain_in_denominator() -> None:
    maxima = [None] * 63 + [12.0]
    rows, receipt = build([event(8.0, 0.08, 10.0, direction='dimming')], [], surrogates(maxima))
    assert math.isclose(rows[0].empirical_familywise_p, 2.0 / 65.0)
    assert rows[0].matched_brightening_snr is None
    assert rows[0].snr_above_matched_control is None
    assert receipt.surrogate_trials_without_dimming_maximum == 63

def test_machine_event_order_and_indices_are_input_order_invariant() -> None:
    events = [event(9.0, 0.16, 8.0, direction='dimming'), event(4.0, 0.08, 10.0, direction='dimming')]
    forward, _ = build(events, [])
    reverse, _ = build(list(reversed(events)), [])
    assert [row.to_dict() for row in forward] == [row.to_dict() for row in reverse]
    assert [row.source_event_index for row in forward] == [0, 1]
    assert [row.center_time_days for row in forward] == [4.0, 9.0]

def test_nearest_duration_control_is_selected_deterministically() -> None:
    rows, _ = build([event(8.0, 0.116, 10.0, direction='dimming')], [event(2.0, 0.104, 7.0, direction='brightening'), event(3.0, 0.16, 30.0, direction='brightening')])
    assert rows[0].matched_brightening_snr == 7.0
    assert rows[0].snr_above_matched_control == 3.0

def test_wrong_surrogate_method_or_masking_is_rejected() -> None:
    with pytest.raises(ValueError, match='gap-aware'):
        build([], [], surrogates(method='legacy-block-permutation'))
    with pytest.raises(ValueError, match='unmasked null'):
        build([], [], surrogates(neutralized_events=1))

def test_exact_surrogate_seed_grid_is_required() -> None:
    with pytest.raises(ValueError, match='exactly 64'):
        build([], [], surrogates()[:-1])
    duplicate = surrogates()
    duplicate[-1] = SurrogateTrial(**{**duplicate[-1].to_dict(), 'seed': 62})
    with pytest.raises(ValueError, match='exactly 0 through 63'):
        build([], [], duplicate)

def test_event_target_direction_and_duration_family_are_closed() -> None:
    wrong_target = SingleTransitEvent(target='OTHER STAR', center_time_days=1.0, duration_days=0.08, depth=0.0001, snr=8.0, local_points=8, direction='dimming')
    with pytest.raises(ValueError, match='target'):
        build([wrong_target], [])
    with pytest.raises(ValueError, match='expected dimming'):
        build([event(1.0, 0.08, 8.0, direction='brightening')], [])
    with pytest.raises(ValueError, match='outside'):
        build([event(1.0, 0.09, 8.0, direction='dimming')], [])

def test_campaign_input_hash_must_come_from_fingerprinted_arrays() -> None:
    time = np.linspace(0.0, 2.0, 40)
    lightcurve = LightCurve(time, np.ones_like(time), target='SYNTHETIC STAR', metadata={'campaign_input_array_hashes': {'combined_sha256': HASH}})
    assert campaign_input_combined_sha256(lightcurve) == HASH
    missing = LightCurve(time, np.ones_like(time), target='SYNTHETIC STAR')
    with pytest.raises(ValueError, match='missing campaign_input_array_hashes'):
        campaign_input_combined_sha256(missing)

def test_phase09_search_duration_family_is_fixed() -> None:
    with pytest.raises(ValueError, match='search-duration family is frozen'):
        build_blind_candidate_inputs(target_id='synthetic-star', target_name='SYNTHETIC STAR', sector_label='1', campaign_input_sha256=HASH, search_duration_family_days=(0.08, 0.16), dimming_events=[], brightening_control_events=[], surrogate_trials=surrogates())

def test_surrogate_integer_and_threshold_semantics_are_strict() -> None:
    invalid_segments = surrogates()
    invalid_segments[0] = SurrogateTrial(**{**invalid_segments[0].to_dict(), 'contiguous_segments': True})
    with pytest.raises(ValueError, match='contiguous_segments'):
        build([], [], invalid_segments)
    invalid_count = surrogates()
    invalid_count[0] = SurrogateTrial(**{**invalid_count[0].to_dict(), 'maximum_brightening_snr': 6.0, 'exceeded_brightening_threshold': True, 'brightening_events': 0})
    with pytest.raises(ValueError, match='brightening event count is inconsistent'):
        build([], [], invalid_count)
    invalid_flag = surrogates()
    invalid_flag[0] = SurrogateTrial(**{**invalid_flag[0].to_dict(), 'exceeded_dimming_threshold': False})
    with pytest.raises(ValueError, match='dimming threshold flag is inconsistent'):
        build([], [], invalid_flag)
