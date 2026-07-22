import numpy as np

from houearth.core import LightCurve
from houearth.stratification import classify_lightcurve


def test_classify_lightcurve_uses_tess_metadata() -> None:
    time = np.linspace(0.0, 5.0, 500)
    flux = 1.0 + 0.00015 * np.sin(2 * np.pi * time)
    lc = LightCurve(
        time,
        flux,
        target="stratum-fixture",
        metadata={
            "sectors": [7],
            "product_provenance": [
                {"tessmag": 10.8, "crowdsap": 0.91, "camera": 2, "ccd": 4}
            ],
        },
    )
    stratum = classify_lightcurve(lc)
    assert stratum.magnitude_bin == "10to12"
    assert stratum.crowding_bin == "mixed"
    assert stratum.scatter_bin == "low"
    assert stratum.cadence_bin == "20min"
    assert stratum.sectors == "7"
    assert stratum.cameras == "2"
    assert stratum.ccds == "4"
