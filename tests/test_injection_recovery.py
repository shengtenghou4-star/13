from houearth.search import search_periodic_transits, search_single_transits
from houearth.synthetic import make_synthetic_lightcurve


def test_periodic_injection_recovery() -> None:
    injected_period = 7.25
    lc = make_synthetic_lightcurve(period=injected_period, add_single_event=False)
    candidate = search_periodic_transits(
        lc,
        min_period=5.5,
        max_period=9.0,
        period_steps=500,
    )
    relative_error = abs(candidate.period_days - injected_period) / injected_period
    assert relative_error < 0.02
    assert candidate.snr > 8
    assert candidate.depth > 0.004


def test_single_event_recovery() -> None:
    lc = make_synthetic_lightcurve(add_single_event=True)
    injected_center = lc.metadata["single_event_center_days"]
    events = search_single_transits(lc, min_snr=5.0)
    assert events
    nearest = min(events, key=lambda event: abs(event.center_time_days - injected_center))
    assert abs(nearest.center_time_days - injected_center) < 0.35
    assert nearest.snr > 5
