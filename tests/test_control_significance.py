from houearth.control_significance import (
    annotate_trial_rows,
    duration_matched_controls,
    empirical_upper_tail_probability,
    summarize_annotated_rows,
)


def test_duration_matching_prefers_exact_bin() -> None:
    controls = [
        {"duration_days": 0.04, "snr": 5.0},
        {"duration_days": 0.08, "snr": 7.0},
        {"duration_days": 0.08, "snr": 6.0},
    ]
    matched = duration_matched_controls(controls, 0.08)
    assert len(matched) == 2
    assert all(float(row["duration_days"]) == 0.08 for row in matched)


def test_empirical_probability_uses_add_one_smoothing() -> None:
    assert empirical_upper_tail_probability(8.0, [5.0, 7.0, 9.0]) == 0.5
    assert empirical_upper_tail_probability(10.0, [5.0, 7.0, 9.0]) == 0.25
    assert empirical_upper_tail_probability(10.0, []) is None


def test_annotation_and_summary_preserve_recovery() -> None:
    controls = [
        {"duration_days": 0.08, "snr": 6.0},
        {"duration_days": 0.08, "snr": 8.0},
    ]
    trials = [
        {
            "target_id": "star-a",
            "depth": "0.0001",
            "duration_days": "0.08",
            "recovered": "True",
            "recovered_snr": "9.0",
        },
        {
            "target_id": "star-a",
            "depth": "0.0001",
            "duration_days": "0.08",
            "recovered": "False",
            "recovered_snr": "",
        },
    ]
    annotated = annotate_trial_rows(trials, controls)
    assert annotated[0]["snr_above_matched_control"] == 1.0
    assert annotated[0]["brightening_empirical_p"] == 1 / 3
    assert annotated[1]["snr_above_matched_control"] is None

    summary = summarize_annotated_rows(annotated, pool_targets=True)[0]
    assert summary["trials"] == 2
    assert summary["recovered"] == 1
    assert summary["completeness"] == 0.5
    assert summary["fraction_above_matched_control"] == 1.0
