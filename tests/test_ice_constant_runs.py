"""Constant runs inside the ice period must not raise constant_value; open-water runs must."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from quality.anomaly_detection import detect_anomalies_all_years  # noqa: E402
from quality.quality_flags import QualityFlag  # noqa: E402


def _series(constant_months: tuple[int, ...]) -> pd.Series:
    idx = pd.date_range("2010-10-01", "2011-09-30", freq="D")
    rng = np.random.default_rng(0)
    q = pd.Series(10 + rng.normal(0, 0.5, len(idx)), index=idx)
    q[idx.month.isin(constant_months)] = 3.0
    return q


def test_winter_constant_run_is_not_flagged() -> None:
    flags = detect_anomalies_all_years(_series((12, 1, 2)))
    assert QualityFlag.CONSTANT_VALUE not in flags.get(2011, [])


def test_summer_constant_run_is_flagged() -> None:
    flags = detect_anomalies_all_years(_series((6, 7)))
    assert QualityFlag.CONSTANT_VALUE in flags.get(2011, [])


if __name__ == "__main__":
    test_winter_constant_run_is_not_flagged()
    test_summer_constant_run_is_flagged()
    print("ok")
