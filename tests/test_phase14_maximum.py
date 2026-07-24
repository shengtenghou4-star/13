from __future__ import annotations

import numpy as np

from houearth.core import LightCurve
from houearth.phase14_maximum import (
    maximum_single_transit_snr,
    run_phase14_dimming_surrogate_trial_maximum_only,
)
from houearth.phase14_power_restore import (
    run_phase14_dimming_surrogate_trial,
)
from houearth.provenance import lightcurve_array_hashes
from houearth.search import search_single_transits


def _lightcurve() -> LightCurve:
    time = np.arange(0.0, 16.0, 0.02)
    flux = 1.0 + 0.0002 * np.sin(2 * np.pi * time / 3.7)
    flux -= 0.0012 * np.exp(-0.5 * ((time - 7.3) / 0.06) ** 2)
    error = np.full_like(time, 0.0002)
    hashes = lightcurve_array_hashes(time, flux, error)
    return LightCurve(
        time,
        flux,
        error,
        target="maximum-fixture",
        metadata={
            "sectors": [1, 2],
            "campaign_input_array_hashes": hashes,
        },
    )


def test_maximum_only_matches_full_event_search() -> None:
    lc = _lightcurve()
    full = search_single_transits(
        lc,
        durations=(0.052, 0.08, 0.16, 0.232),
        flatten_window_days=1.5,
        min_snr=1e-6,
        max_events=1,
        direction="dimming",
    )
    maximum = maximum_single_transit_snr(
        lc,
        durations=(0.052, 0.08, 0.16, 0.232),
        flatten_window_days=1.5,
        min_snr=1e-6,
        direction="dimming",
    )
    assert maximum == max(event.snr for event in full)


def test_phase14_maximum_only_has_identical_trial_hashes() -> None:
    lc = _lightcurve()
    campaign_hash = lc.metadata["campaign_input_array_hashes"][
        "combined_sha256"
    ]
    for seed in range(64, 72):
        full = run_phase14_dimming_surrogate_trial(
            lc,
            target_id="fixture-target",
            campaign_input_combined_sha256=campaign_hash,
            seed=seed,
        )
        maximum_only = run_phase14_dimming_surrogate_trial_maximum_only(
            lc,
            target_id="fixture-target",
            campaign_input_combined_sha256=campaign_hash,
            seed=seed,
        )
        assert maximum_only.trial_sha256 == full.trial_sha256
        assert maximum_only.to_dict() == full.to_dict()


def test_invalid_edge_peak_does_not_replace_an_interior_candidate() -> None:
    time = np.arange(0.0, 8.0, 0.02)
    flux = np.ones_like(time)
    flux[:5] -= 0.02
    flux[198:205] -= 0.003
    error = np.full_like(time, 0.0002)
    lc = LightCurve(time, flux, error, target="edge-fixture")
    full = search_single_transits(
        lc,
        durations=(0.08,),
        flatten_window_days=1.5,
        min_snr=1e-6,
        max_events=1,
        direction="dimming",
    )
    maximum = maximum_single_transit_snr(
        lc,
        durations=(0.08,),
        flatten_window_days=1.5,
        min_snr=1e-6,
        direction="dimming",
    )
    assert maximum == max(event.snr for event in full)
