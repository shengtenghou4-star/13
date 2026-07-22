import numpy as np

from houearth.core import LightCurve
from houearth.evaluation import make_noise_lightcurve
from houearth.real_evaluation import (
    run_real_lightcurve_campaign,
    wilson_interval,
)


def test_wilson_interval_is_bounded() -> None:
    low, high = wilson_interval(6, 8)
    assert 0.0 < low < 0.75 < high < 1.0


def test_real_campaign_recovers_strong_injections() -> None:
    lc = make_noise_lightcurve(
        baseline_days=12.0,
        cadence_minutes=30.0,
        noise=0.0018,
        seed=22,
        target="observed-background-fixture",
    )
    lc = LightCurve(
        lc.time,
        lc.flux,
        lc.flux_err,
        target=lc.target,
        metadata={**lc.metadata, "sectors": [99]},
    )
    null_screen, background, brightening, trials, cells = run_real_lightcurve_campaign(
        lc,
        depths=(0.012,),
        durations_days=(0.16,),
        seeds=range(2),
    )
    assert null_screen.sector_label == "99"
    assert null_screen.brightening_event_count == len(brightening)
    assert len(trials) == 2
    assert len(cells) == 1
    assert cells[0].recovered == 2
    assert all(trial.local_coverage_fraction >= 0.7 for trial in trials)
    assert all(
        trial.background_brightening_event_count == len(brightening)
        for trial in trials
    )
    assert isinstance(background, list)
    assert isinstance(brightening, list)


def test_default_clipping_preserves_deep_dips() -> None:
    time = np.linspace(0.0, 5.0, 500)
    flux = 1.0 + 0.0002 * np.sin(2 * np.pi * time)
    flux[100:104] -= 0.03
    flux[300] += 0.03
    lc = LightCurve(time, flux, target="bright-star")
    clipped = lc.sigma_clipped(sigma=8.0)
    assert np.min(clipped.flux) < 0.98
    assert np.max(clipped.flux) < 1.02


def test_mirrored_clipping_preserves_brightenings() -> None:
    time = np.linspace(0.0, 5.0, 500)
    flux = 1.0 + 0.0002 * np.sin(2 * np.pi * time)
    flux[100:104] -= 0.03
    flux[300:304] += 0.03
    lc = LightCurve(time, flux, target="bright-star")
    clipped = lc.sigma_clipped(
        sigma=8.0,
        clip_positive=False,
        clip_negative=True,
    )
    assert np.max(clipped.flux) > 1.02
    assert np.min(clipped.flux) > 0.98
