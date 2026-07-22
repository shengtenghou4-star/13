import numpy as np

from houearth.core import LightCurve, SingleTransitEvent
from houearth.surrogates import block_permuted_surrogate, run_surrogate_null_campaign


def two_segment_lightcurve() -> tuple[LightCurve, int]:
    cadence = 1.0 / 48.0
    first_time = np.arange(0.0, 4.0, cadence)
    second_time = np.arange(10.0, 14.0, cadence)
    time = np.concatenate([first_time, second_time])
    rng = np.random.default_rng(20260722)
    first = rng.normal(0.0, 0.00012, len(first_time))
    second = rng.normal(0.0, 0.0030, len(second_time))
    flux = 1.0 + np.concatenate([first, second])
    flux_err = np.concatenate(
        [np.full(len(first_time), 0.0002), np.full(len(second_time), 0.0040)]
    )
    return LightCurve(time, flux, flux_err, target="two-segment"), len(first_time)


def test_gap_aware_bootstrap_keeps_noise_and_errors_in_their_segments() -> None:
    lc, split = two_segment_lightcurve()
    surrogate = block_permuted_surrogate(lc, block_days=0.5, seed=17)

    first_scale = float(np.std(surrogate.flux[:split]))
    second_scale = float(np.std(surrogate.flux[split:]))
    assert surrogate.metadata["surrogate_contiguous_segments"] == 2
    assert surrogate.metadata["surrogate_gap_factor"] == 3.5
    assert second_scale > 10.0 * first_scale
    assert np.all(surrogate.flux_err[:split] == 0.0002)
    assert np.all(surrogate.flux_err[split:] == 0.0040)


def test_event_neutralization_does_not_interpolate_across_a_gap() -> None:
    lc, split = two_segment_lightcurve()
    event = SingleTransitEvent(
        target=lc.target,
        center_time_days=float(lc.time[split - 4]),
        duration_days=0.20,
        depth=0.02,
        snr=30.0,
        local_points=10,
    )
    surrogate = block_permuted_surrogate(
        lc,
        block_days=0.5,
        seed=19,
        excluded_events=(event,),
    )
    assert surrogate.metadata["surrogate_contiguous_segments"] == 2
    assert surrogate.metadata["surrogate_neutralized_events"] == 1
    assert surrogate.metadata["surrogate_neutralized_points"] > 0
    assert float(np.std(surrogate.flux[split:])) > 10.0 * float(
        np.std(surrogate.flux[:split])
    )


def test_campaign_records_segment_count_in_every_null_trial() -> None:
    lc, _ = two_segment_lightcurve()
    trials, summary = run_surrogate_null_campaign(
        lc,
        seeds=range(3),
        block_days=0.5,
        durations=(0.08, 0.16),
    )
    assert len(trials) == 3
    assert all(trial.contiguous_segments == 2 for trial in trials)
    assert all(trial.gap_factor == 3.5 for trial in trials)
    assert summary.minimum_segments == 2
    assert summary.maximum_segments == 2
    assert summary.gap_factor == 3.5
