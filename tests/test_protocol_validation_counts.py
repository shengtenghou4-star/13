import pytest

from houearth.protocol_validation import (
    ProtocolValidationError,
    validate_phase07_summary,
)
from houearth.provenance import HASH_SCHEMA
from houearth.search_grids import physical_single_event_search_durations


SEARCH_DURATIONS = physical_single_event_search_durations((0.08, 0.16))
VALID_STRATUM = {
    "campaign_input_hash_schema": HASH_SCHEMA,
    "campaign_input_combined_sha256": "a" * 64,
    "product_provenance_sha256": "b" * 64,
    "query_provenance_sha256": "c" * 64,
}


def summary_fixture() -> dict[str, object]:
    targets = []
    for target_id in ("a", "b", "c"):
        targets.append(
            {
                "target_id": target_id,
                "status": "completed",
                "surrogate_policy": "unmasked-null",
                "stratum": dict(VALID_STRATUM),
                "physical_trials": 32,
                "surrogate_trials": 64,
                "surrogate_summary": {
                    "status": "completed",
                    "search_durations_days": SEARCH_DURATIONS,
                },
            }
        )
    for target_id in ("d", "e", "f"):
        targets.append(
            {
                "target_id": target_id,
                "status": "completed",
                "surrogate_policy": "skip-known-transits",
                "stratum": dict(VALID_STRATUM),
                "physical_trials": 32,
                "surrogate_trials": 0,
                "surrogate_summary": {"status": "skipped"},
            }
        )
    return {
        "targets": targets,
        "search_durations_days": SEARCH_DURATIONS,
        "total_physical_trials": 192,
        "total_surrogate_trials": 192,
        "minimum_resolvable_surrogate_p": 1.0 / 65.0,
    }


@pytest.mark.parametrize("bad_count", [32.9, True, "32", float("nan")])
def test_target_trial_counts_must_be_exact_json_integers(bad_count: object) -> None:
    summary = summary_fixture()
    summary["targets"][0]["physical_trials"] = bad_count
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    assert any(
        "physical trial count is not an exact integer" in error
        for error in captured.value.report.errors
    )


@pytest.mark.parametrize("field", ["total_physical_trials", "total_surrogate_trials"])
def test_reported_totals_reject_fractional_values(field: str) -> None:
    summary = summary_fixture()
    summary[field] = 192.5
    with pytest.raises(ProtocolValidationError) as captured:
        validate_phase07_summary(summary)
    assert any("total is not an exact integer" in error for error in captured.value.report.errors)
