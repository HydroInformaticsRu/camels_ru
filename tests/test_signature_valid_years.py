"""Regression test: n_valid_periods must count periods that met the completeness rule.

It used to be len(period_metrics), i.e. every hydrological year on the grid including
all-NaN ones, so the released n_valid_years read 17 for a 15-year record (2026-08 review).

Run: ``pixi run python tests/test_signature_valid_years.py``
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hydro.period_based_metrics import calculate_comprehensive_metrics  # noqa: E402


def test_partial_years_are_not_counted_as_valid():
    idx = pd.date_range("2008-10-01", "2023-09-30", freq="D")
    q = pd.Series(np.ones(len(idx)), index=idx)
    q[idx < "2015-10-01"] = np.nan  # 7 empty years, 8 complete ones
    q[(idx >= "2015-10-01") & (idx < "2016-08-01")] = np.nan  # HY2016 at ~17 % coverage
    m = calculate_comprehensive_metrics(q, min_data_fraction=0.7, min_periods=5)
    assert m["n_valid_periods"] == 7, m["n_valid_periods"]
    assert np.isfinite(m["mean_discharge"])


if __name__ == "__main__":
    test_partial_years_are_not_counted_as_valid()
    print("PASS: test_signature_valid_years")
