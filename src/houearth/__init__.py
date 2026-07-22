"""HOU-EARTH: an auditable transit-search and calibration toolkit."""

from .core import LightCurve, PeriodicCandidate, SingleTransitEvent
from .evaluation import CompletenessCell, SingleTransitTrial
from .real_evaluation import (
    NullScreenResult,
    RealCompletenessCell,
    RealInjectionTrial,
    run_real_lightcurve_campaign,
    wilson_interval,
)
from .search import search_periodic_transits, search_single_transits

__all__ = [
    "CompletenessCell",
    "LightCurve",
    "NullScreenResult",
    "PeriodicCandidate",
    "RealCompletenessCell",
    "RealInjectionTrial",
    "SingleTransitEvent",
    "SingleTransitTrial",
    "run_real_lightcurve_campaign",
    "search_periodic_transits",
    "search_single_transits",
    "wilson_interval",
]

__version__ = "0.3.0"
