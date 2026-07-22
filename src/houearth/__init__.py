"""HOU-EARTH: an auditable transit-search and calibration toolkit."""

from .core import LightCurve, PeriodicCandidate, SingleTransitEvent
from .evaluation import CompletenessCell, SingleTransitTrial
from .physical import (
    exposure_averaged_single_transit_decrement,
    inject_physical_single_transit,
    physical_single_transit_decrement,
)
from .physical_evaluation import (
    PhysicalCompletenessCell,
    PhysicalInjectionTrial,
    run_physical_campaign,
)
from .protocol_validation import (
    ProtocolValidationError,
    ProtocolValidationReport,
    validate_phase07_summary,
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
from .surrogate_significance import (
    SurrogateCalibratedCell,
    SurrogateCalibratedTrial,
    calibrate_physical_trials,
    empirical_familywise_p,
    summarize_surrogate_calibrated_trials,
)
from .surrogates import SurrogateSummary, SurrogateTrial, run_surrogate_null_campaign

__all__ = [
    "CompletenessCell",
    "LightCurve",
    "LightCurveStratum",
    "NullScreenResult",
    "PeriodicCandidate",
    "PhysicalCompletenessCell",
    "PhysicalInjectionTrial",
    "ProtocolValidationError",
    "ProtocolValidationReport",
    "RealCompletenessCell",
    "RealInjectionTrial",
    "SingleTransitEvent",
    "SingleTransitTrial",
    "SurrogateCalibratedCell",
    "SurrogateCalibratedTrial",
    "SurrogateSummary",
    "SurrogateTrial",
    "calibrate_physical_trials",
    "classify_lightcurve",
    "empirical_familywise_p",
    "exposure_averaged_single_transit_decrement",
    "inject_physical_single_transit",
    "physical_single_transit_decrement",
    "run_physical_campaign",
    "run_real_lightcurve_campaign",
    "run_surrogate_null_campaign",
    "search_periodic_transits",
    "search_single_transits",
    "summarize_surrogate_calibrated_trials",
    "validate_phase07_summary",
    "wilson_interval",
]

__version__ = "0.7.0"
