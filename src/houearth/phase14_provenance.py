from __future__ import annotations

import re
from numbers import Integral
from typing import Mapping

from .provenance import canonical_json_sha256

PHASE14_EXECUTION_AMENDMENT_SCHEMA = (
    "houearth-phase14-execution-provenance-amendment-v0.14.1"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class Phase14ProvenanceError(ValueError):
    pass


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise Phase14ProvenanceError(f"{label} must be a lowercase SHA-256")
    return value


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise Phase14ProvenanceError(f"{label} must be a non-negative integer")
    return int(value)


def build_phase14_execution_amendment(
    *,
    scientific_source_commit: str,
    plan_lock_sha256: str,
    legacy_run_identity_sha256: str,
    legacy_claimed_module_sha256: str,
    exact_public_module_sha256: str,
    corrected_worker_sha256: str,
    exact_maximum_optimizer_sha256: str,
    legacy_chunks: int,
    audited_legacy_chunks: int,
    audit_mismatches: int,
) -> dict[str, object]:
    """Bind the Phase 0.14 execution correction without changing the frozen statistic.

    The original chunk payloads remain usable only as hash-bound numerical evidence.
    A revised candidate table cannot be frozen until every legacy chunk has been
    recomputed under the exact public module (or a separately proved exact optimizer)
    and every recomputed trial hash agrees.
    """

    if not isinstance(scientific_source_commit, str) or _GIT_SHA.fullmatch(
        scientific_source_commit
    ) is None:
        raise Phase14ProvenanceError(
            "scientific_source_commit must be a lowercase Git SHA"
        )
    plan_lock_sha256 = _sha256(plan_lock_sha256, "plan_lock_sha256")
    legacy_run_identity_sha256 = _sha256(
        legacy_run_identity_sha256, "legacy_run_identity_sha256"
    )
    legacy_claimed_module_sha256 = _sha256(
        legacy_claimed_module_sha256, "legacy_claimed_module_sha256"
    )
    exact_public_module_sha256 = _sha256(
        exact_public_module_sha256, "exact_public_module_sha256"
    )
    corrected_worker_sha256 = _sha256(
        corrected_worker_sha256, "corrected_worker_sha256"
    )
    exact_maximum_optimizer_sha256 = _sha256(
        exact_maximum_optimizer_sha256, "exact_maximum_optimizer_sha256"
    )
    legacy_chunks = _count(legacy_chunks, "legacy_chunks")
    audited_legacy_chunks = _count(
        audited_legacy_chunks, "audited_legacy_chunks"
    )
    audit_mismatches = _count(audit_mismatches, "audit_mismatches")
    if audited_legacy_chunks > legacy_chunks:
        raise Phase14ProvenanceError(
            "audited_legacy_chunks cannot exceed legacy_chunks"
        )
    if legacy_claimed_module_sha256 == exact_public_module_sha256:
        raise Phase14ProvenanceError(
            "an execution amendment requires a genuine recorded-module mismatch"
        )

    full_recompute_complete = audited_legacy_chunks == legacy_chunks
    numerical_equivalence_accepted = (
        full_recompute_complete and audit_mismatches == 0
    )
    body = {
        "schema": PHASE14_EXECUTION_AMENDMENT_SCHEMA,
        "scientific_source_commit": scientific_source_commit,
        "plan_lock_sha256": plan_lock_sha256,
        "legacy_run_identity_sha256": legacy_run_identity_sha256,
        "legacy_claimed_module_sha256": legacy_claimed_module_sha256,
        "exact_public_module_sha256": exact_public_module_sha256,
        "corrected_worker_sha256": corrected_worker_sha256,
        "exact_maximum_optimizer_sha256": exact_maximum_optimizer_sha256,
        "legacy_chunks": legacy_chunks,
        "audited_legacy_chunks": audited_legacy_chunks,
        "audit_mismatches": audit_mismatches,
        "full_legacy_recompute_complete": full_recompute_complete,
        "numerical_equivalence_accepted": numerical_equivalence_accepted,
        "candidate_table_freeze_allowed": numerical_equivalence_accepted,
        "thresholds_changed": False,
        "surrogate_seeds_changed": False,
        "search_statistic_changed": False,
        "candidate_details_disclosed": False,
        "astronomical_claim": "none",
    }
    return {**body, "amendment_sha256": canonical_json_sha256(body)}


def validate_phase14_execution_amendment(
    amendment: Mapping[str, object],
) -> dict[str, object]:
    row = dict(amendment)
    digest = row.pop("amendment_sha256", None)
    if digest != canonical_json_sha256(row):
        raise Phase14ProvenanceError("amendment_sha256 does not match")
    if row.get("schema") != PHASE14_EXECUTION_AMENDMENT_SCHEMA:
        raise Phase14ProvenanceError("execution amendment schema is invalid")
    rebuilt = build_phase14_execution_amendment(
        scientific_source_commit=str(row["scientific_source_commit"]),
        plan_lock_sha256=str(row["plan_lock_sha256"]),
        legacy_run_identity_sha256=str(row["legacy_run_identity_sha256"]),
        legacy_claimed_module_sha256=str(row["legacy_claimed_module_sha256"]),
        exact_public_module_sha256=str(row["exact_public_module_sha256"]),
        corrected_worker_sha256=str(row["corrected_worker_sha256"]),
        exact_maximum_optimizer_sha256=str(
            row["exact_maximum_optimizer_sha256"]
        ),
        legacy_chunks=row["legacy_chunks"],
        audited_legacy_chunks=row["audited_legacy_chunks"],
        audit_mismatches=row["audit_mismatches"],
    )
    if rebuilt != {**row, "amendment_sha256": digest}:
        raise Phase14ProvenanceError("execution amendment is not canonical")
    return rebuilt
