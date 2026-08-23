"""Per-flag share of assessed hydrological years (Table 3 column).

Re-runs the release-default grader (same inputs and settings as ``GradeCompound.py``)
over the graded compound files and counts, for every quality flag, the share of assessed
gauge-years on which it fired. ``GradeCompound.py`` persists grades but not flags, so this
is the only place the flag census is materialised.

Writes ``paper/tables/flag_frequencies.csv`` (flag, n_years, share_pct), read by
``scripts/verify_macros.py`` and rendered in ``tables/quality_flags.tex``.

Run: PYTHONPATH=src pixi run python scripts/flag_frequencies.py
"""

from collections import Counter
from pathlib import Path
import sys

import pandas as pd
from tqdm.auto import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from GradeCompound import (  # noqa: E402
    COMPOUND_DIR,
    HYDRO_YEAR_START_MONTH,
    MIN_YEARS_FOR_ASSESSMENT,
    load_precipitation,
)

from quality import assess_gauge_quality  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "paper" / "tables" / "flag_frequencies.csv"


def main() -> None:
    """Count flag occurrences over all assessed years of the graded gauges."""
    files = sorted(p for g in "ABCDF" for p in (COMPOUND_DIR / "by_grade" / g).glob("*.csv"))
    counts: Counter[str] = Counter()
    n_years = 0
    for path in tqdm(files, desc="Re-assessing graded gauges"):
        gid = path.stem
        discharge = pd.read_csv(path, index_col="date", parse_dates=True)["q_mm_day"].dropna()
        year_results, _ = assess_gauge_quality(
            discharge=discharge,
            precipitation=load_precipitation(gid),
            temperature=None,
            gauge_id=gid,
            hydro_year_start_month=HYDRO_YEAR_START_MONTH,
            min_years=MIN_YEARS_FOR_ASSESSMENT,
            use_temperature_aware_response=False,
        )
        n_years += len(year_results)
        for yr in year_results:
            counts.update(flag.value for flag in yr.flags)
    rows = [
        {"flag": flag, "n_years": n, "share_pct": 100.0 * n / n_years}
        for flag, n in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    df = pd.DataFrame(rows)
    df.attrs["n_assessed_years"] = n_years
    df.insert(1, "n_assessed_years", n_years)
    df.to_csv(OUT, index=False)
    print(f"{len(files)} gauges, {n_years} assessed years")
    print(df.to_string(index=False))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
