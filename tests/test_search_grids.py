import pytest

from houearth.search_grids import physical_single_event_search_durations


def test_phase07_search_family_is_frozen_and_ordered() -> None:
    durations = physical_single_event_search_durations((0.08, 0.16))
    assert durations == pytest.approx((0.052, 0.08, 0.104, 0.116, 0.16, 0.232))
    assert tuple(sorted(durations)) == durations
    assert len(set(durations)) == 6


def test_search_family_deduplicates_overlapping_scaled_durations() -> None:
    durations = physical_single_event_search_durations((0.08, 0.08))
    assert durations == pytest.approx((0.052, 0.08, 0.116))


@pytest.mark.parametrize("durations", [(), (0.0,), (-0.08,), (0.08, -0.16)])
def test_search_family_rejects_invalid_physical_durations(
    durations: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError):
        physical_single_event_search_durations(durations)
