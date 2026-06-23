"""Regression test: discharge quality_flag must distinguish gap-filled days.

Adds flag value 1 (gap_filled) so the released discharge.nc separates
observed (0), interpolated (1, the <=6-day second-order-polynomial fills written
in place by scripts/ParseAisQData.py), and missing (3). Previously the
interpolated days shared flag 0 and could not be screened out (2026-06
science-review, Domain Expert finding MAJOR-2).

Run: ``pixi run python tests/test_discharge_fill_flag.py``
Exits 0 on success, non-zero on regression.
"""

from pathlib import Path
import sys

import numpy as np

sys.path.append(str(Path(__file__).parent.parent))
from scripts.package_dataset import _discharge_quality_flags  # noqa: E402


def test_flags_separate_observed_filled_missing() -> None:
    """Present & not-filled -> 0; present & filled -> 1; absent -> 3."""
    present = np.array([True, True, True, False, True])
    filled = np.array([False, True, False, False, True])
    flags = _discharge_quality_flags(present, filled)
    assert flags.tolist() == [0, 1, 0, 3, 1], flags.tolist()
    assert flags.dtype == np.int8


def test_filled_implies_present() -> None:
    """A 'filled' day that is somehow absent must stay missing, never become 1."""
    present = np.array([False, True])
    filled = np.array([True, False])  # filled[0] without present[0] = inconsistent input
    flags = _discharge_quality_flags(present, filled)
    assert flags.tolist() == [3, 0], "an absent day must remain missing (3)"


if __name__ == "__main__":
    test_flags_separate_observed_filled_missing()
    test_filled_implies_present()
    print("PASS: test_discharge_fill_flag")
