"""HOU-EARTH: an auditable transit-search and calibration toolkit."""

from .candidate_freeze import (
    BlindCandidateInput,
    FrozenCandidateRecord,
    FrozenCandidateTable,
    benjamini_hochberg_qvalues,
    freeze_candidate_table,
    write_frozen_candidate_table,
)
from .candidate_protocol_validation import (
    CandidateProtocolValidationError,
    CandidateProtocolValidationReport,
    validate_frozen_candidate_table,
)
from .core import LightCurve, PeriodicCandidate, SingleTransitEvent
from .evaluation import CompletenessCell, SingleTransitTrial
from .gap_protocol_validation import (
    GapProtocolValidationError,
    GapProtocolValidationReport,
    validate_phase07_gap_summary,
)
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
from .provenance import (
    HASH_SCHEMA,
    canonical_array_sha256,
    canonical_json_sha256,
    lightcurve_array_hashes,
)
from .real_evaluation import (
    NullScreenResult,
    RealCompletenessCell,
    RealInjectionTrial,
    run_real_lightcurve_campaign,
    wilson_interval,
)
from .search import search_periodic_transits, search_single_transits
from .search_grids import physical_single_event_search_durations
from .stratification import LightCurveStratum, classify_lightcurve
from .surrogate_significance import (
    SurrogateCalibratedCell,
    SurrogateCalibratedTrial,
    calibrate_physical_trials,
    empirical_familywise_p,
    summarize_surrogate_calibrated_trials,
)
from .surrogates import (
    DEFAULT_GAP_FACTOR,
    GAP_AWARE_METHOD,
    SurrogateSummary,
    SurrogateTrial,
    run_surrogate_null_campaign,
)

__all__ = [
    "BlindCandidateInput",
    "CandidateProtocolValidationError",
    "CandidateProtocolValidationReport",
    "CompletenessCell",
    "DEFAULT_GAP_FACTOR",
    "FrozenCandidateRecord",
    "FrozenCandidateTable",
    "GAP_AWARE_METHOD",
    "GapProtocolValidationError",
    "GapProtocolValidationReport",
    "HASH_SCHEMA",
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
    "benjamini_hochberg_qvalues",
    "calibrate_physical_trials",
    "canonical_array_sha256",
    "canonical_json_sha256",
    "classify_lightcurve",
    "empirical_familywise_p",
    "exposure_averaged_single_transit_decrement",
    "freeze_candidate_table",
    "inject_physical_single_transit",
    "lightcurve_array_hashes",
    "physical_single_event_search_durations",
    "physical_single_transit_decrement",
    "run_physical_campaign",
    "run_real_lightcurve_campaign",
    "run_surrogate_null_campaign",
    "search_periodic_transits",
    "search_single_transits",
    "summarize_surrogate_calibrated_trials",
    "validate_frozen_candidate_table",
    "validate_phase07_gap_summary",
    "validate_phase07_summary",
    "wilson_interval",
    "write_frozen_candidate_table",
]

__version__ = "0.8.0.dev0"
