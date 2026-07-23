"""HOU-EARTH: an auditable transit-search and calibration toolkit."""

from .candidate_campaign import (
    PHASE09_CALIBRATION_SCHEMA,
    PHASE09_CAMPAIGN_EVIDENCE_SCHEMA,
    PHASE09_CAMPAIGN_LOCK_SCHEMA,
    PHASE09_ELIGIBLE_TARGET_RULE,
    PHASE09_FLATTEN_WINDOW_DAYS,
    PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION,
    PHASE09_MINIMUM_SEARCH_SNR,
    PHASE09_SEARCH_DURATION_FAMILY_DAYS,
    PHASE09_SURROGATE_BLOCK_DAYS,
    PHASE09_SURROGATE_SEEDS,
    CandidateCalibrationReceipt,
    build_blind_candidate_inputs,
    campaign_input_combined_sha256,
    freeze_candidate_campaign_evidence,
)
from .candidate_campaign_validation import (
    CandidateCampaignValidationError,
    CandidateCampaignValidationReport,
    validate_candidate_campaign_evidence,
)
from .candidate_evidence import (
    CandidateEvidenceValidationError,
    CandidateEvidenceValidationReport,
    FrozenCandidateEvidence,
    freeze_candidate_evidence,
    validate_candidate_evidence,
    write_candidate_evidence,
)
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
from .private_campaign import PrivateCampaignResult, run_phase10_private_campaign
from .private_campaign_protocol import (
    PHASE10_PRIVATE_GUARD_ENV,
    PHASE10_PRIVATE_MANIFEST_SCHEMA,
    PHASE10_PRIVATE_RECEIPT_SCHEMA,
    PHASE10_REQUIRED_TARGET_IDS,
    PHASE10_VISIBILITY_ENV,
    PrivateCampaignError,
    PrivateCampaignTarget,
    acquire_and_lock_inputs,
    load_phase10_manifest,
    require_private_evidence_sink,
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
    "CandidateCalibrationReceipt",
    "CandidateCampaignValidationError",
    "CandidateCampaignValidationReport",
    "CandidateEvidenceValidationError",
    "CandidateEvidenceValidationReport",
    "CandidateProtocolValidationError",
    "CandidateProtocolValidationReport",
    "CompletenessCell",
    "DEFAULT_GAP_FACTOR",
    "FrozenCandidateEvidence",
    "FrozenCandidateRecord",
    "FrozenCandidateTable",
    "GAP_AWARE_METHOD",
    "GapProtocolValidationError",
    "GapProtocolValidationReport",
    "HASH_SCHEMA",
    "LightCurve",
    "LightCurveStratum",
    "NullScreenResult",
    "PHASE09_CALIBRATION_SCHEMA",
    "PHASE09_CAMPAIGN_EVIDENCE_SCHEMA",
    "PHASE09_CAMPAIGN_LOCK_SCHEMA",
    "PHASE09_ELIGIBLE_TARGET_RULE",
    "PHASE09_FLATTEN_WINDOW_DAYS",
    "PHASE09_MAX_MACHINE_EVENTS_PER_DIRECTION",
    "PHASE09_MINIMUM_SEARCH_SNR",
    "PHASE09_SEARCH_DURATION_FAMILY_DAYS",
    "PHASE09_SURROGATE_BLOCK_DAYS",
    "PHASE09_SURROGATE_SEEDS",
    "PHASE10_PRIVATE_GUARD_ENV",
    "PHASE10_PRIVATE_MANIFEST_SCHEMA",
    "PHASE10_PRIVATE_RECEIPT_SCHEMA",
    "PHASE10_REQUIRED_TARGET_IDS",
    "PHASE10_VISIBILITY_ENV",
    "PeriodicCandidate",
    "PhysicalCompletenessCell",
    "PhysicalInjectionTrial",
    "PrivateCampaignError",
    "PrivateCampaignResult",
    "PrivateCampaignTarget",
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
    "acquire_and_lock_inputs",
    "benjamini_hochberg_qvalues",
    "build_blind_candidate_inputs",
    "calibrate_physical_trials",
    "campaign_input_combined_sha256",
    "canonical_array_sha256",
    "canonical_json_sha256",
    "classify_lightcurve",
    "empirical_familywise_p",
    "exposure_averaged_single_transit_decrement",
    "freeze_candidate_campaign_evidence",
    "freeze_candidate_evidence",
    "freeze_candidate_table",
    "inject_physical_single_transit",
    "lightcurve_array_hashes",
    "load_phase10_manifest",
    "physical_single_event_search_durations",
    "physical_single_transit_decrement",
    "require_private_evidence_sink",
    "run_phase10_private_campaign",
    "run_physical_campaign",
    "run_real_lightcurve_campaign",
    "run_surrogate_null_campaign",
    "search_periodic_transits",
    "search_single_transits",
    "summarize_surrogate_calibrated_trials",
    "validate_candidate_campaign_evidence",
    "validate_candidate_evidence",
    "validate_frozen_candidate_table",
    "validate_phase07_gap_summary",
    "validate_phase07_summary",
    "wilson_interval",
    "write_candidate_evidence",
    "write_frozen_candidate_table",
]

__version__ = "0.10.0.dev0"
