import numpy as np

from houearth.core import LightCurve, SingleTransitEvent
from houearth.evaluation import make_noise_lightcurve
from houearth.physical import (
    exposure_averaged_single_transit_decrement,
    inject_physical_single_transit,
    physical_single_transit_decrement,
    radius_ratio_for_midpoint_depth,
)
from houearth.physical_evaluation import _matched_control, run_physical_campaign
from houearth.search_grids import physical_single_event_search_durations


def test_physical_model_matches_requested_midpoint_depth() -> None:
    time = np.linspace(-0.2, 0.2, 2001)
    depth = 0.001
    radius_ratio = radius_ratio_for_midpoint_depth(depth, impact_parameter=0.4)
    decrement = physical_single_transit_decrement(
        time,
        center=0.0,
        duration=0.16,
        radius_ratio=radius_ratio,
        impact_parameter=0.4,
    )
    midpoint = int(np.argmin(np.abs(time)))
    assert abs(decrement[midpoint] - depth) < 2e-6
    assert decrement[0] == 0.0
    assert decrement[-1] == 0.0
    assert np.count_nonzero((decrement > 0) & (decrement < depth)) > 10


def test_exposure_averaging_matches_instantaneous_at_supersample_one() -> None:
    time = np.linspace(-0.1, 0.1, 501)
    radius_ratio = radius_ratio_for_midpoint_depth(0.001)
    instantaneous = physical_single_transit_decrement(
        time,
        center=0.0,
        duration=0.08,
        radius_ratio=radius_ratio,
    )
    sampled = exposure_averaged_single_transit_decrement(
        time,
        center=0.0,
        duration=0.08,
        radius_ratio=radius_ratio,
        exposure_days=2.0 / (24.0 * 60.0),
        supersample=1,
    )
    assert np.allclose(sampled, instantaneous)


def test_finite_exposure_smooths_contact_boundary() -> None:
    radius_ratio = radius_ratio_for_midpoint_depth(0.001)
    contact_time = np.array([0.04])
    instantaneous = physical_single_transit_decrement(
        contact_time,
        center=0.0,
        duration=0.08,
        radius_ratio=radius_ratio,
    )[0]
    averaged = exposure_averaged_single_transit_decrement(
        contact_time,
        center=0.0,
        duration=0.08,
        radius_ratio=radius_ratio,
        exposure_days=0.01,
        supersample=9,
    )[0]
    assert instantaneous == 0.0
    assert averaged > 0.0
    assert averaged < 0.001


def test_physical_injection_returns_radius_ratio() -> None:
    time = np.linspace(0.0, 2.0, 2000)
    flux, radius_ratio = inject_physical_single_transit(
        time,
        np.ones_like(time),
        center=1.0,
        duration=0.12,
        depth=0.0002,
        impact_parameter=0.6,
    )
    assert 0.005 < radius_ratio < 0.05
    assert 0.9997 < np.min(flux) < 0.9999


def test_brightening_control_matches_winning_filter_duration() -> None:
    controls = [
        SingleTransitEvent(
            target="control",
            center_time_days=1.0,
            duration_days=0.052,
            depth=0.001,
            snr=6.0,
            local_points=10,
            direction="brightening",
        ),
        SingleTransitEvent(
            target="control",
            center_time_days=2.0,
            duration_days=0.116,
            depth=0.001,
            snr=9.0,
            local_points=20,
            direction="brightening",
        ),
        SingleTransitEvent(
            target="control",
            center_time_days=3.0,
            duration_days=0.16,
            depth=0.001,
            snr=7.0,
            local_points=30,
            direction="brightening",
        ),
    ]
    matched_duration, matched_snr = _matched_control(controls, 0.11)
    assert matched_duration == 0.116
    assert matched_snr == 9.0


def test_physical_campaign_recovers_strong_events_and_freezes_generators() -> None:
    base = make_noise_lightcurve(
        baseline_days=12.0,
        cadence_minutes=30.0,
        noise=0.0018,
        seed=33,
        target="physical-fixture",
    )
    lc = LightCurve(
        base.time,
        base.flux,
        base.flux_err,
        target=base.target,
        metadata={**base.metadata, "sectors": [99]},
    )
    _, _, _, trials, cells = run_physical_campaign(
        lc,
        depths=(value for value in (0.012,)),
        durations_days=(value for value in (0.16,)),
        impact_parameters=(value for value in (0.0, 0.6)),
        seeds=(value for value in range(2)),
        supersample=7,
    )
    assert len(trials) == 4
    assert sum(trial.recovered for trial in trials) >= 3
    assert len(cells) == 2
    assert all(trial.radius_ratio > 0 for trial in trials)
    assert all(trial.supersample == 7 for trial in trials)
    assert all(abs(trial.exposure_days - lc.cadence) < 1e-12 for trial in trials)
    search_family = physical_single_event_search_durations((0.16,))
    assert all(
        trial.recovered_duration_days in search_family
        for trial in trials
        if trial.recovered
    )
