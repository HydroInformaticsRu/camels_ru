"""Regression test: --resume coverage must treat all-NaN months as uncovered.

Reproduces the 2023 ERA5-Land silent-skip failure mode (2026-06-23 triad
investigation, hardening item 2): ``detect_covered_months`` read only the
``date`` column (``usecols=["date"]``), so a month that is *present but
all-NaN* (the broken-aggregation result) counted as "covered". A ``--resume``
run then samples a handful of healthy CSVs, sees 2023 as covered, and silently
skips re-aggregating 2023 for every gauge -- masking the bug's return.

A month must count as covered only if it carries real (non-NaN) data.

Run: ``pixi run python tests/test_resume_coverage_nan.py``
Exits 0 on success, non-zero on regression.
"""

from pathlib import Path
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from scripts.aggregate_watersheds import detect_covered_months  # noqa: E402


def _write_gauge_csv(path: Path) -> None:
    """A gauge CSV with real 2022 data but a present-yet-all-NaN 2023-01 month."""
    real = pd.date_range("2022-01-01", "2022-02-28", freq="D")
    broken = pd.date_range("2023-01-01", "2023-01-31", freq="D")
    df = pd.DataFrame(
        {
            "date": real.append(broken),
            "t_mean": np.concatenate([np.full(len(real), 1.5), np.full(len(broken), np.nan)]),
            "t_min": np.concatenate([np.full(len(real), -2.0), np.full(len(broken), np.nan)]),
            "t_max": np.concatenate([np.full(len(real), 5.0), np.full(len(broken), np.nan)]),
        }
    )
    df.to_csv(path, index=False)


def test_all_nan_month_is_not_covered() -> None:
    """A present-but-all-NaN month must be excluded from the covered set."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        for gid in ("0001", "0002", "0003"):
            _write_gauge_csv(out_dir / f"{gid}.csv")

        covered = detect_covered_months(out_dir)

    assert (2022, 1) in covered, "real January 2022 data must count as covered"
    assert (2022, 2) in covered, "real February 2022 data must count as covered"
    assert (2023, 1) not in covered, (
        "present-but-all-NaN 2023-01 must NOT count as covered "
        "(a resume run would otherwise silently skip re-aggregating it)"
    )


if __name__ == "__main__":
    test_all_nan_month_is_not_covered()
    print("PASS: test_resume_coverage_nan")
