import csv
from pathlib import Path


MANIFEST = Path("data/stratified_targets_v0.7.csv")
NULL_AUDIT = Path("data/null_target_audit_v0.7.csv")


def test_v07_manifest_has_balanced_null_policy() -> None:
    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8")))
    assert len(rows) == 6
    assert len({row["target_id"] for row in rows}) == 6

    unmasked = {
        row["target_id"]
        for row in rows
        if row["surrogate_policy"] == "unmasked-null"
    }
    skipped = {
        row["target_id"]
        for row in rows
        if row["surrogate_policy"] == "skip-known-transits"
    }
    assert unmasked == {"hd-10700", "hd-20794", "hd-69830"}
    assert skipped == {"au-mic", "toi-700", "lhs-3844"}
    assert unmasked.isdisjoint(skipped)


def test_v07_protocol_freezes_equal_physical_and_null_trial_counts() -> None:
    targets = 6
    depths = 2
    durations = 2
    impact_parameters = 2
    injection_seeds = 4
    null_targets = 3
    surrogate_seeds = 64

    assert targets * depths * durations * impact_parameters * injection_seeds == 192
    assert null_targets * surrogate_seeds == 192
    assert 1.0 / (surrogate_seeds + 1.0) < 0.05
    assert 1.0 / (surrogate_seeds + 1.0) > 0.01


def test_null_target_audit_matches_manifest_policy() -> None:
    manifest = {
        row["target_id"]: row["surrogate_policy"]
        for row in csv.DictReader(MANIFEST.open(encoding="utf-8"))
    }
    audit = list(csv.DictReader(NULL_AUDIT.open(encoding="utf-8")))
    assert len(audit) == 6
    for row in audit:
        assert row["target_id"] in manifest
        assert row["pilot_surrogate_policy"] == manifest[row["target_id"]]
        if row["confirmed_transiting_system_in_archive"] == "yes":
            assert row["pilot_surrogate_policy"] == "skip-known-transits"
        else:
            assert row["pilot_surrogate_policy"] == "unmasked-null"
