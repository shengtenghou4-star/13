import numpy as np

from houearth.core import LightCurve
from houearth.evaluation import make_noise_lightcurve
from houearth.physical import (
    inject_physical_single_transit,
    physical_single_transit_decrement,
    radius_ratio_for_midpoint_depth,
)
from houearth.physical_evaluation import run_physical_campaign


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


def test_physical_campaign_recovers_strong_events() -> None:
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
        depths=(0.012,),
        durations_days=(0.16,),
        impact_parameters=(0.0, 0.6),
        seeds=range(2),
    )
    assert len(trials) == 4
    assert sum(trial.recovered for trial in trials) >= 3
    assert len(cells) == 2
    assert all(trial.radius_ratio > 0 for trial in trials)
