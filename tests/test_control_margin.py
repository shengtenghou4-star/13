import numpy as np

from houearth.core import LightCurve
from houearth.evaluation import make_noise_lightcurve
from houearth.real_evaluation import run_real_lightcurve_campaign


def test_recovery_records_margin_above_brightening_control() -> None:
    base = make_noise_lightcurve(
        baseline_days=12.0,
        cadence_minutes=30.0,
        noise=0.0018,
        seed=22,
        target="control-margin-fixture",
    )
    flux = base.flux.copy()
    flux[np.abs(base.time - 2.5) <= 0.08] += 0.012
    lc = LightCurve(
        base.time,
        flux,
        base.flux_err,
        target=base.target,
        metadata={**base.metadata, "sectors": [99]},
    )

    null_screen, _, controls, trials, cells = run_real_lightcurve_campaign(
        lc,
        depths=(0.012,),
        durations_days=(0.16,),
        seeds=range(2),
    )

    assert null_screen.brightening_event_count == 1
    assert len(controls) == 1
    assert all(trial.recovered for trial in trials)
    assert all(trial.snr_above_control is not None for trial in trials)
    assert cells[0].median_snr_above_control is not None
    assert cells[0].median_snr_above_control > 0
