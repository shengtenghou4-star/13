"""HOU-EARTH: an auditable transit-search and calibration toolkit."""

from .core import LightCurve, PeriodicCandidate, SingleTransitEvent
from .evaluation import CompletenessCell, SingleTransitTrial
from .physical import inject_physical_single_transit, physical_single_transit_decrement
from .physical_evaluation import (
    PhysicalCompletenessCell,
    PhysicalInjectionTrial,
    run_physical_campaign,
)
from .real_evaluation import (
    NullScreenResult,
    RealCompletenessCell,
    RealInjectionTrial,
    run_real_lightcurve_campaign,
    wilson_interval,
)
from .search import search_periodic_transits, search_single_transits
from .stratification import LightCurveStratum, classify_lightcurve
from .surrogates import SurrogateSummary, SurrogateTrial, run_surrogate_null_campaign

__all__ = [
    "CompletenessCell",
    "LightCurve",
    "LightCurveStratum",
    "NullScreenResult",
    "PeriodicCandidate",
    "PhysicalCompletenessCell",
    "PhysicalInjectionTrial",
    "RealCompletenessCell",
    "RealInjectionTrial",
    "SingleTransitEvent",
    "SingleTransitTrial",
    "SurrogateSummary",
    "SurrogateTrial",
    "classify_lightcurve",
    "inject_physical_single_transit",
    "physical_single_transit_decrement",
    "run_physical_campaign",
    "run_real_lightcurve_campaign",
    "run_surrogate_null_campaign",
    "search_periodic_transits",
    "search_single_transits",
    "wilson_interval",
]

__version__ = "0.7.0"
