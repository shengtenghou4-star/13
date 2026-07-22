import numpy as np
import pytest

from houearth.core import LightCurve
from houearth.search import search_single_transits


def test_mirrored_search_finds_dip_and_brightening() -> None:
    time = np.linspace(0.0, 10.0, 1001)
    flux = 1.0 + 0.00015 * np.sin(2 * np.pi * time / 2.3)
    flux[np.abs(time - 3.0) <= 0.06] -= 0.012
    flux[np.abs(time - 7.0) <= 0.06] += 0.010
    lc = LightCurve(time, flux, target="signed-control-fixture")

    dimmings = search_single_transits(
        lc,
        durations=(0.12,),
        flatten_window_days=1.0,
        min_snr=5.0,
        direction="dimming",
    )
    brightenings = search_single_transits(
        lc,
        durations=(0.12,),
        flatten_window_days=1.0,
        min_snr=5.0,
        direction="brightening",
    )

    assert dimmings
    assert brightenings
    assert dimmings[0].direction == "dimming"
    assert brightenings[0].direction == "brightening"
    assert abs(dimmings[0].center_time_days - 3.0) < 0.08
    assert abs(brightenings[0].center_time_days - 7.0) < 0.08


def test_single_event_direction_is_validated() -> None:
    time = np.linspace(0.0, 5.0, 501)
    lc = LightCurve(time, np.ones_like(time), target="invalid-direction")
    with pytest.raises(ValueError):
        search_single_transits(lc, direction="sideways")
