import numpy as np

from houearth.core import LightCurve
from houearth.provenance import HASH_SCHEMA
from houearth.stratification import classify_lightcurve


def test_classify_lightcurve_uses_tess_metadata_and_separates_scales() -> None:
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
            "campaign_input_array_hashes": {
                "schema": HASH_SCHEMA,
                "combined_sha256": "a" * 64,
            },
            "product_provenance_sha256": "b" * 64,
            "query_provenance_sha256": "c" * 64,
        },
    )
    stratum = classify_lightcurve(lc)
    assert stratum.magnitude_bin == "10to12"
    assert stratum.crowding_bin == "mixed"
    assert stratum.scatter_bin == "low"
    assert stratum.point_to_point_bin == "low"
    assert stratum.robust_scatter_ppm > stratum.point_to_point_scatter_ppm
    assert stratum.six_hour_scatter_ppm > 0
    assert 0.9 < stratum.lag1_autocorrelation <= 1.0
    assert stratum.correlation_bin == "high"
    assert stratum.variability_to_point_ratio > 1.0
    assert stratum.cadence_bin == "20min"
    assert stratum.sectors == "7"
    assert stratum.cameras == "2"
    assert stratum.ccds == "4"
    assert stratum.campaign_input_hash_schema == HASH_SCHEMA
    assert stratum.campaign_input_combined_sha256 == "a" * 64
    assert stratum.product_provenance_sha256 == "b" * 64
    assert stratum.query_provenance_sha256 == "c" * 64


def test_correlation_metric_distinguishes_white_and_red_noise() -> None:
    rng = np.random.default_rng(9)
    time = np.arange(0.0, 10.0, 1.0 / 48.0)
    white = rng.normal(0.0, 0.0004, len(time))
    innovations = rng.normal(0.0, 0.00018, len(time))
    red = np.zeros_like(innovations)
    for index in range(1, len(red)):
        red[index] = 0.9 * red[index - 1] + innovations[index]
    white_stratum = classify_lightcurve(
        LightCurve(time, 1.0 + white, target="white")
    )
    red_stratum = classify_lightcurve(
        LightCurve(time, 1.0 + red, target="red")
    )
    assert abs(white_stratum.lag1_autocorrelation) < 0.2
    assert red_stratum.lag1_autocorrelation > 0.7
    assert red_stratum.variability_to_point_ratio > white_stratum.variability_to_point_ratio
    assert white_stratum.campaign_input_combined_sha256 is None
