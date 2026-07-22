from houearth.real_evaluation import RealInjectionTrial
from houearth.real_reporting import pool_real_trials


def trial(
    target: str,
    recovered: bool,
    snr: float | None,
    margin: float | None,
) -> RealInjectionTrial:
    return RealInjectionTrial(
        target=target,
        sector_label="1",
        depth=0.004,
        duration_days=0.16,
        seed=0,
        injected_center_days=5.0,
        local_coverage_fraction=1.0,
        recovered=recovered,
        recovered_center_days=5.0 if recovered else None,
        recovered_snr=snr,
        timing_error_days=0.0 if recovered else None,
        background_event_count=0,
        background_brightening_event_count=1,
        control_maximum_snr=5.5,
        snr_above_control=margin,
        novel_competing_events=0,
    )


def test_pool_real_trials_counts_targets_and_interval() -> None:
    cells = pool_real_trials(
        [
            trial("star-a", True, 9.0, 3.5),
            trial("star-a", False, None, None),
            trial("star-b", True, 7.0, 1.5),
            trial("star-b", True, 8.0, 2.5),
        ]
    )
    assert len(cells) == 1
    cell = cells[0]
    assert cell.targets == 2
    assert cell.trials == 4
    assert cell.recovered == 3
    assert cell.completeness == 0.75
    assert cell.median_snr_above_control == 2.5
    assert cell.confidence_low < cell.completeness < cell.confidence_high
