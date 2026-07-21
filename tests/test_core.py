import numpy as np
import pytest

from houearth.core import LightCurve


def test_lightcurve_sorts_and_filters() -> None:
    time = np.arange(30.0)[::-1]
    flux = np.ones(30)
    flux[3] = np.nan
    lc = LightCurve(time, flux)
    assert np.all(np.diff(lc.time) > 0)
    assert len(lc.time) == 29


def test_lightcurve_rejects_short_input() -> None:
    with pytest.raises(ValueError):
        LightCurve(np.arange(5.0), np.ones(5))
