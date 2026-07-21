"""HOU-EARTH: reproducible transit discovery tooling for TESS light curves."""

from .core import LightCurve, PeriodicCandidate, SingleTransitEvent
from .search import search_periodic_transits, search_single_transits

__all__ = [
    "LightCurve",
    "PeriodicCandidate",
    "SingleTransitEvent",
    "search_periodic_transits",
    "search_single_transits",
]

__version__ = "0.1.0"
