"""HOU-EARTH: an auditable transit-search and calibration toolkit."""

from .core import LightCurve, PeriodicCandidate, SingleTransitEvent
from .evaluation import CompletenessCell, SingleTransitTrial
from .search import search_periodic_transits, search_single_transits

__all__ = [
    "CompletenessCell",
    "LightCurve",
    "PeriodicCandidate",
    "SingleTransitEvent",
    "SingleTransitTrial",
    "search_periodic_transits",
    "search_single_transits",
]

__version__ = "0.2.0"
