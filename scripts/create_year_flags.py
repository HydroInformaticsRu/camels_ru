"""Per-year quality flags for the release: camels_ru_year_flags.csv.

Re-runs the release-default grader over the RELEASED files alone
(``camels_ru_discharge.nc`` discharge_mm + ``camels_ru_forcing.nc`` precip_mswep)
for every gauge of ``camels_ru_year_grades.csv`` and writes one row per assessed
gauge-year: gauge_id, hydro_year, grade, flag_codes (comma-separated).

The run doubles as a full-network reproduction gate and refuses to write unless
BOTH hold:
  1. every re-derived grade equals the released year_grades.csv cell, and
  2. the aggregated per-flag counts equal paper/tables/flag_frequencies.csv.

Note: run this BEFORE any masking of discharge_mm — the grader reads it.

Run: pixi run python scripts/create_year_flags.py
"""

from pathlib import Path
import sys

import pandas as pd
from tqdm.auto import tqdm
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from quality import assess_gauge_quality  # noqa: E402

RELEASE = REPO / "release" / "CAMELS_RU_v1.0"
CENSUS = REPO / "paper" / "tables" / "flag_frequencies.csv"
OUT = RELEASE / "camels_ru_year_flags.csv"

HYDRO_YEAR_START_MONTH = 10
MIN_YEARS = 3


def main(limit: int | None = None) -> None:
    """Assess every graded gauge from the release and write the flags CSV."""
    yg = pd.read_csv(RELEASE / "camels_ru_year_grades.csv", dtype={"gauge_id": str})
    year_cols = [c for c in yg.columns if c.isdigit()]
    yg = yg.set_index("gauge_id")

    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as dds:
        q = dds["discharge_mm"].sel(gauge_id=list(yg.index)).to_pandas()
    with xr.open_dataset(RELEASE / "camels_ru_forcing.nc") as fds:
        p = fds["precip_mswep"].sel(gauge_id=list(yg.index)).to_pandas()
    if q.shape[0] != len(yg.index):  # to_pandas orients (gauge_id, time) rows-first
        q, p = q.T, p.T

    gauges = list(yg.index) if limit is None else list(yg.index)[:limit]
    rows: list[dict[str, str | int]] = []
    n_grade_mismatch = 0
    for gid in tqdm(gauges, desc="Re-assessing from release"):
        year_results, _ = assess_gauge_quality(
            discharge=q.loc[gid].dropna(),
            precipitation=p.loc[gid],
            temperature=None,
            gauge_id=gid,
            hydro_year_start_month=HYDRO_YEAR_START_MONTH,
            min_years=MIN_YEARS,
            use_temperature_aware_response=False,
        )
        for yr in year_results:
            released = yg.at[gid, str(yr.year)] if str(yr.year) in year_cols else None
            if not isinstance(released, str) or released != yr.grade.value:
                n_grade_mismatch += 1
            rows.append(
                {
                    "gauge_id": gid,
                    "hydro_year": yr.year,
                    "grade": yr.grade.value,
                    # grade_year() takes flags AND completeness (70/85/95% caps),
                    # so both must ship or the grade cannot be audited from the row
                    "completeness": round(yr.data_completeness, 4),
                    "flag_codes": ",".join(f.value for f in yr.flags),
                }
            )

    df = pd.DataFrame(rows)
    print(f"assessed gauge-years: {len(df)}  grade mismatches vs year_grades.csv: {n_grade_mismatch}")

    # Informational comparison against the committed census (full runs only; the
    # census is regenerated FROM this file by scripts/flag_frequencies.py, so a
    # drift here means the census needs regenerating, not that this file is wrong).
    if limit is None and CENSUS.exists():
        census = pd.read_csv(CENSUS)
        counts = df["flag_codes"].str.split(",").explode()
        counts = counts[counts != ""].value_counts()
        for _, row in census.iterrows():
            got = int(counts.get(row["flag"], 0))
            if got != int(row["n_years"]):
                print(f"  census drift {row['flag']}: got {got}, census {row['n_years']}")

    # Hard gate: the external truth is year_grades.csv — every assessed
    # gauge-year must exist there with the identical grade, cell for cell.
    expected_years = int(yg[year_cols].notna().sum().sum())
    if limit is not None:
        print(f"(dry run over {limit} gauges — nothing written)")
        return
    if n_grade_mismatch or len(df) != expected_years:
        print(f"REFUSING to write: {n_grade_mismatch} grade mismatches or {len(df)} != {expected_years}")
        raise SystemExit(1)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(df)} rows, {len(gauges)} gauges)")


if __name__ == "__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
