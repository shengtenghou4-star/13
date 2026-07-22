import numpy as np

from houearth.core import LightCurve, SingleTransitEvent
from houearth.surrogates import block_permuted_surrogate, run_surrogate_null_campaign


def make_correlated_fixture() -> LightCurve:
    rng = np.random.default_rng(12)
    time = np.arange(0.0, 12.0, 1.0 / 48.0)
    innovations = rng.normal(0.0, 0.0004, len(time))
    residual = np.zeros_like(innovations)
    for index in range(1, len(residual)):
        residual[index] = 0.88 * residual[index - 1] + innovations[index]
    return LightCurve(
        time,
        1.0 + residual,
        np.full_like(time, 0.0004),
        target="red-noise-fixture",
        metadata={"sectors": [88]},
    )


def test_block_surrogate_is_deterministic_and_does_not_sign_flip() -> None:
    lc = make_correlated_fixture()
    first = block_permuted_surrogate(lc, block_days=0.5, seed=7)
    second = block_permuted_surrogate(lc, block_days=0.5, seed=7)
    different = block_permuted_surrogate(lc, block_days=0.5, seed=8)
    assert np.array_equal(first.time, lc.time)
    assert np.allclose(first.flux, second.flux)
    assert not np.allclose(first.flux, different.flux)

    original = lc.normalized().flux - 1.0
    surrogate = first.flux - 1.0
    assert np.min(surrogate) >= np.min(original) - 1e-15
    assert np.max(surrogate) <= np.max(original) + 1e-15
    original_scale = np.std(original)
    surrogate_scale = np.std(surrogate)
    assert abs(surrogate_scale / original_scale - 1.0) < 0.20


def test_detected_event_is_neutralized_before_bootstrap() -> None:
    base = make_correlated_fixture()
    flux = np.array(base.flux, copy=True)
    event_mask = np.abs(base.time - 6.0) <= 0.10
    flux[event_mask] -= 0.02
    lc = LightCurve(
        base.time,
        flux,
        base.flux_err,
        target=base.target,
        metadata=base.metadata,
    )
    event = SingleTransitEvent(
        target=lc.target,
        center_time_days=6.0,
        duration_days=0.20,
        depth=0.02,
        snr=30.0,
        local_points=int(np.count_nonzero(event_mask)),
    )
    surrogate = block_permuted_surrogate(
        lc,
        block_days=0.5,
        seed=3,
        excluded_events=(event,),
    )
    assert surrogate.metadata["surrogate_neutralized_events"] == 1
    assert surrogate.metadata["surrogate_neutralized_points"] > 0
    assert np.min(surrogate.flux - 1.0) > -0.01


def test_surrogate_tail_uses_all_trials_not_only_exceedances() -> None:
    lc = make_correlated_fixture()
    trials, summary = run_surrogate_null_campaign(
        lc,
        seeds=range(4),
        block_days=0.5,
        durations=(0.08, 0.16),
        min_snr=1e6,
    )
    assert len(trials) == 4
    assert summary.trials == 4
    assert summary.sector_label == "88"
    assert summary.trials_with_dimming_events == 0
    assert summary.dimming_false_alarm_rate == 0.0
    assert summary.median_maximum_dimming_snr is not None
    assert summary.p95_maximum_dimming_snr is not None
    assert summary.maximum_dimming_snr is not None
