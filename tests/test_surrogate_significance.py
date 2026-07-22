import pytest

from houearth.physical_evaluation import PhysicalInjectionTrial
from houearth.surrogate_significance import (
    calibrate_physical_trials,
    empirical_familywise_p,
    summarize_surrogate_calibrated_trials,
)
from houearth.surrogates import GAP_AWARE_METHOD, SurrogateTrial


def physical_trial(
    *, snr: float | None, recovered: bool, seed: int = 0
) -> PhysicalInjectionTrial:
    return PhysicalInjectionTrial(
        target="star-a",
        sector_label="1",
        depth=0.0001,
        duration_days=0.08,
        impact_parameter=0.0,
        radius_ratio=0.01,
        limb_u1=0.35,
        limb_u2=0.25,
        exposure_days=2.0 / (24.0 * 60.0),
        supersample=7,
        seed=seed,
        injected_center_days=5.0,
        local_coverage_fraction=1.0,
        recovered=recovered,
        recovered_center_days=5.0 if recovered else None,
        recovered_duration_days=0.08 if recovered else None,
        recovered_snr=snr,
        timing_error_days=0.0 if recovered else None,
        matched_control_duration_days=0.08,
        matched_control_snr=6.0,
        snr_above_matched_control=None if snr is None else snr - 6.0,
        novel_competing_events=0,
    )


def surrogate_trial(seed: int, maximum: float) -> SurrogateTrial:
    return SurrogateTrial(
        target="star-a",
        sector_label="1",
        seed=seed,
        method=GAP_AWARE_METHOD,
        block_days=0.5,
        contiguous_segments=1,
        gap_factor=3.5,
        neutralized_events=0,
        neutralized_points=0,
        dimming_events=int(maximum >= 5.0),
        brightening_events=0,
        maximum_dimming_snr=maximum,
        maximum_brightening_snr=4.0,
        exceeded_dimming_threshold=maximum >= 5.0,
        exceeded_brightening_threshold=False,
    )


def test_empirical_familywise_p_uses_add_one_smoothing() -> None:
    assert empirical_familywise_p(10.0, [4.0, 6.0, 9.0]) == 0.25
    assert empirical_familywise_p(8.0, [4.0, 8.0, 9.0]) == 0.75


def test_calibration_reports_resolution_and_significance() -> None:
    nulls = [surrogate_trial(index, 5.0 + index * 0.1) for index in range(64)]
    rows = calibrate_physical_trials(
        [
            physical_trial(snr=20.0, recovered=True, seed=0),
            physical_trial(snr=6.0, recovered=True, seed=1),
            physical_trial(snr=None, recovered=False, seed=2),
        ],
        nulls,
    )
    assert len(rows) == 3
    assert abs(rows[0].minimum_resolvable_p - 1.0 / 65.0) < 1e-12
    assert rows[0].significance_alpha == 0.05
    assert rows[0].empirical_familywise_p == 1.0 / 65.0
    assert rows[0].significant_at_0_05 is True
    assert rows[1].significant_at_0_05 is False
    assert rows[2].empirical_familywise_p is None


def test_phase07_schema_rejects_a_different_alpha() -> None:
    with pytest.raises(ValueError, match="frozen at alpha=0.05"):
        calibrate_physical_trials(
            [physical_trial(snr=20.0, recovered=True)],
            [surrogate_trial(index, 5.0) for index in range(64)],
            alpha=0.10,
        )


def test_calibrated_summary_distinguishes_recovery_from_significance() -> None:
    nulls = [surrogate_trial(index, 8.0) for index in range(64)]
    rows = calibrate_physical_trials(
        [
            physical_trial(snr=12.0, recovered=True, seed=0),
            physical_trial(snr=7.0, recovered=True, seed=1),
            physical_trial(snr=None, recovered=False, seed=2),
            physical_trial(snr=None, recovered=False, seed=3),
        ],
        nulls,
    )
    cells = summarize_surrogate_calibrated_trials(rows)
    assert len(cells) == 1
    cell = cells[0]
    assert cell.trials == 4
    assert cell.recovered == 2
    assert cell.significance_alpha == 0.05
    assert cell.significant_recoveries_0_05 == 1
    assert cell.significant_completeness_0_05 == 0.25
    assert cell.significant_confidence_low_0_05 < 0.25
    assert cell.significant_confidence_high_0_05 > 0.25
    assert cell.fraction_of_recoveries_significant_0_05 == 0.5
