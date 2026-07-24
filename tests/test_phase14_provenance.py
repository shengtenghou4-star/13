from __future__ import annotations

import pytest

from houearth.phase14_provenance import (
    Phase14ProvenanceError,
    build_phase14_execution_amendment,
    validate_phase14_execution_amendment,
)


BASE = {
    "scientific_source_commit": "2" * 40,
    "plan_lock_sha256": "1" * 64,
    "legacy_run_identity_sha256": "2" * 64,
    "legacy_claimed_module_sha256": "3" * 64,
    "exact_public_module_sha256": "4" * 64,
    "corrected_worker_sha256": "5" * 64,
    "exact_maximum_optimizer_sha256": "6" * 64,
    "legacy_chunks": 199,
}


def test_pending_legacy_audit_forbids_candidate_freeze() -> None:
    amendment = build_phase14_execution_amendment(
        **BASE,
        audited_legacy_chunks=32,
        audit_mismatches=0,
    )
    assert amendment["full_legacy_recompute_complete"] is False
    assert amendment["numerical_equivalence_accepted"] is False
    assert amendment["candidate_table_freeze_allowed"] is False
    validate_phase14_execution_amendment(amendment)


def test_complete_exact_recompute_restores_execution_acceptance() -> None:
    amendment = build_phase14_execution_amendment(
        **BASE,
        audited_legacy_chunks=199,
        audit_mismatches=0,
    )
    assert amendment["full_legacy_recompute_complete"] is True
    assert amendment["numerical_equivalence_accepted"] is True
    assert amendment["candidate_table_freeze_allowed"] is True
    assert amendment["thresholds_changed"] is False
    assert amendment["search_statistic_changed"] is False
    validate_phase14_execution_amendment(amendment)


def test_any_recompute_mismatch_keeps_freeze_closed() -> None:
    amendment = build_phase14_execution_amendment(
        **BASE,
        audited_legacy_chunks=199,
        audit_mismatches=1,
    )
    assert amendment["full_legacy_recompute_complete"] is True
    assert amendment["numerical_equivalence_accepted"] is False
    assert amendment["candidate_table_freeze_allowed"] is False


def test_audited_count_cannot_exceed_legacy_count() -> None:
    with pytest.raises(Phase14ProvenanceError, match="cannot exceed"):
        build_phase14_execution_amendment(
            **BASE,
            audited_legacy_chunks=200,
            audit_mismatches=0,
        )


def test_amendment_rejects_a_fake_mismatch() -> None:
    values = dict(BASE)
    values["exact_public_module_sha256"] = values[
        "legacy_claimed_module_sha256"
    ]
    with pytest.raises(Phase14ProvenanceError, match="genuine"):
        build_phase14_execution_amendment(
            **values,
            audited_legacy_chunks=199,
            audit_mismatches=0,
        )
