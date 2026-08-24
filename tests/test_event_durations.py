"""Regression test: high/low-flow event durations must count observed days.

``FlowExtremes._calculate_event_durations`` had two defects that reached the v1.0
release in ``high_flow_dur`` and ``low_flow_dur`` (found in the 2026-08-24 science
review):

1. Event ends were taken at the index where the condition mask went *False* -- one
   day past the end of the event -- and the duration then added another day, so a
   true 3-day event reported 4 days and a true 1-day event reported 2.
2. Durations were measured as calendar spans over a series with missing days already
   dropped, so two separate spells either side of a data gap merged into one long
   event. Two 3-day spells across a 28-day gap reported as a single 34-day event,
   which inflated ``low_flow_dur`` 6.5-fold at the 57 winter-gap gauges that carry
   signatures.

Run: ``pixi run python tests/test_event_durations.py``
Exits 0 on success, non-zero on regression.
"""

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.hydro.flow_extremes import FlowExtremes  # noqa: E402


def durations(mask: pd.Series) -> list[int]:
    """Call the private duration helper without constructing a full FlowExtremes."""
    return FlowExtremes.__new__(FlowExtremes)._calculate_event_durations(mask)


def mask_over(days: int, true_slices: list[slice]) -> pd.Series:
    """Build a daily boolean mask of ``days`` length with the given slices set True."""
    series = pd.Series(False, index=pd.date_range("2020-01-01", periods=days, freq="D"))
    for sl in true_slices:
        series.iloc[sl] = True
    return series


def test_no_off_by_one() -> None:
    """A run of N consecutive days is N days long, not N+1."""
    assert durations(mask_over(20, [slice(5, 8), slice(12, 13)])) == [3, 1]
    assert durations(mask_over(10, [slice(0, 1)])) == [1]


def test_gaps_split_events() -> None:
    """A break in the daily index ends the event; it is not spanned as calendar time."""
    index = pd.DatetimeIndex(
        list(pd.date_range("2020-01-01", periods=3, freq="D"))
        + list(pd.date_range("2020-02-01", periods=3, freq="D"))
    )
    assert durations(pd.Series(True, index=index)) == [3, 3]

    # A single missing day is still a break: 2 + 2, never 5.
    index = pd.DatetimeIndex(
        list(pd.date_range("2020-03-01", periods=2, freq="D"))
        + list(pd.date_range("2020-03-04", periods=2, freq="D"))
    )
    assert durations(pd.Series(True, index=index)) == [2, 2]


def test_boundaries() -> None:
    """Events touching either end of the series are counted, and an empty mask is empty."""
    assert durations(mask_over(20, [slice(0, 2)])) == [2]
    assert durations(mask_over(20, [slice(-3, None)])) == [3]
    assert durations(mask_over(20, [slice(None)])) == [20]
    assert durations(mask_over(20, [])) == []


def test_no_event_exceeds_the_record() -> None:
    """The pre-fix bug let a duration exceed the number of days actually observed."""
    index = pd.DatetimeIndex(
        list(pd.date_range("2020-01-01", periods=3, freq="D"))
        + list(pd.date_range("2020-06-01", periods=3, freq="D"))
    )
    mask = pd.Series(True, index=index)
    assert max(durations(mask)) <= len(index)


if __name__ == "__main__":
    test_no_off_by_one()
    test_gaps_split_events()
    test_boundaries()
    test_no_event_exceeds_the_record()
    print("test_event_durations: all checks passed")
