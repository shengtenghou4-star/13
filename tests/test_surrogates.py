import numpy as np

from houearth.core import LightCurve
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


def test_block_surrogate_is_deterministic_and_preserves_distribution() -> None:
    lc = make_correlated_fixture()
    first = block_permuted_surrogate(lc, block_days=0.5, seed=7)
    second = block_permuted_surrogate(lc, block_days=0.5, seed=7)
    different = block_permuted_surrogate(lc, block_days=0.5, seed=8)
    assert np.array_equal(first.time, lc.time)
    assert np.allclose(first.flux, second.flux)
    assert not np.allclose(first.flux, different.flux)
    original_scale = np.std(lc.normalized().flux - 1.0)
    surrogate_scale = np.std(first.flux - 1.0)
    assert abs(surrogate_scale / original_scale - 1.0) < 0.05


def test_surrogate_campaign_reports_tail_statistics() -> None:
    lc = make_correlated_fixture()
    trials, summary = run_surrogate_null_campaign(
        lc,
        seeds=range(4),
        block_days=0.5,
        durations=(0.08, 0.16),
    )
    assert len(trials) == 4
    assert summary.trials == 4
    assert summary.sector_label == "88"
    assert 0 <= summary.trials_with_dimming_events <= 4
