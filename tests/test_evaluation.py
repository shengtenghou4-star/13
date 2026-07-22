from houearth.evaluation import (
    run_single_transit_campaign,
    run_single_transit_trial,
    summarize_trials,
)


def test_strong_single_transit_is_recovered() -> None:
    trial = run_single_transit_trial(
        depth=0.012,
        duration_days=0.20,
        seed=3,
        baseline_days=12.0,
        cadence_minutes=30.0,
    )
    assert trial.recovered
    assert trial.timing_error_days is not None
    assert trial.timing_error_days < 0.15


def test_completeness_summary_is_bounded() -> None:
    trials, cells = run_single_transit_campaign(
        depths=(0.004, 0.012),
        durations_days=(0.12,),
        seeds=range(2),
        baseline_days=10.0,
        cadence_minutes=30.0,
    )
    assert len(trials) == 4
    assert len(cells) == 2
    assert all(0.0 <= cell.completeness <= 1.0 for cell in cells)
    assert cells == summarize_trials(trials)
