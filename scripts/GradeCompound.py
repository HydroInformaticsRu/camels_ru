"""Grade compound hydro files and organize by quality.

Reads flat compound CSVs from Compound/, runs quality assessment on q_mm_day
(with optional MSWEP precipitation forcing), adds a per-day grade column,
then saves into a by-grade directory structure.

Input:  data/CAMELS_RU/HydroData/Compound/*.csv
Output:
    Compound/
    ├── by_grade/{A,B,C,D,F,ungraded}/{gauge_id}.csv
    ├── grade_mapping.json
    └── quality_summary.csv
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from quality import QualityGrade, assess_gauge_quality

COMPOUND_DIR = Path("data/CAMELS_RU/HydroData/Compound")
MSWEP_DIR = Path("data/CAMELS_RU/parsed_meteo/mswep")
ERA5_LAND_DIR = Path("data/CAMELS_RU/parsed_meteo/era5_land")

HYDRO_YEAR_START_MONTH = 10
MIN_YEARS_FOR_ASSESSMENT = 3
USE_TEMPERATURE_AWARE_RESPONSE = os.getenv("CAMELS_RU_TEMP_AWARE_QC", "0") == "1"


def load_precipitation(gauge_id: str) -> pd.Series | None:
    """Load MSWEP precipitation for a gauge."""
    precip_file = MSWEP_DIR / f"{gauge_id}.csv"
    if not precip_file.exists():
        return None
    df = pd.read_csv(precip_file, index_col="date", parse_dates=True)
    if "precipitation" in df.columns:
        return df["precipitation"]
    return None


def load_temperature(gauge_id: str) -> pd.Series | None:
    """Load ERA5-Land mean temperature for a gauge."""
    temp_file = ERA5_LAND_DIR / f"{gauge_id}.csv"
    if not temp_file.exists():
        return None
    df = pd.read_csv(temp_file, index_col="date", parse_dates=True)
    if "t_mean" in df.columns:
        return df["t_mean"]
    return None


def grade_compound(
    compound: pd.DataFrame,
    gauge_id: str,
    use_temperature_aware_response: bool = USE_TEMPERATURE_AWARE_RESPONSE,
) -> tuple[pd.DataFrame, str | None, dict[int, str]]:
    """Run quality assessment and add a per-day grade column.

    Returns:
        (compound_with_grade, overall_grade_str_or_None, {hydro_year: grade_str}).
    """
    if "q_mm_day" not in compound.columns:
        compound["grade"] = np.nan
        return compound, None, {}

    discharge = compound["q_mm_day"].dropna()
    if len(discharge) < 365 * MIN_YEARS_FOR_ASSESSMENT:
        compound["grade"] = np.nan
        return compound, None, {}

    precipitation = load_precipitation(gauge_id)
    temperature = load_temperature(gauge_id) if use_temperature_aware_response else None

    year_results, summary = assess_gauge_quality(
        discharge=discharge,
        precipitation=precipitation,
        temperature=temperature,
        gauge_id=gauge_id,
        hydro_year_start_month=HYDRO_YEAR_START_MONTH,
        min_years=MIN_YEARS_FOR_ASSESSMENT,
        use_temperature_aware_response=use_temperature_aware_response,
    )

    if not year_results:
        compound["grade"] = np.nan
        return compound, None, {}

    # Vectorized grade assignment by hydrological year
    year_grades = {yr.year: yr.grade.value for yr in year_results}
    months = compound.index.month
    years = compound.index.year
    hydro_years = np.where(months >= HYDRO_YEAR_START_MONTH, years + 1, years)
    compound["grade"] = pd.Series(hydro_years, index=compound.index).map(year_grades)

    overall_grade = summary.overall_grade.value

    # Note: the full-coverage gate (zero missing days in 2008-2023) was removed.
    # The strict Grade A rule in quality_grader.py now handles this: every
    # hydro-year must be individually graded A (≥95% completeness, ≤2 minor flags).
    # The calendar-boundary check was overly restrictive and penalized gauges
    # with perfect hydro-years but partial coverage at the 2008/2023 edges.

    return compound, overall_grade, year_grades


def save_by_grade(
    compound: pd.DataFrame,
    gauge_id: str,
    overall_grade: str | None,
    base_dir: Path,
) -> None:
    """Save compound file into by_grade/{grade}/."""
    grade_folder = overall_grade if overall_grade else "ungraded"

    grade_dir = base_dir / "by_grade" / grade_folder
    grade_dir.mkdir(parents=True, exist_ok=True)
    compound.to_csv(grade_dir / f"{gauge_id}.csv")


if __name__ == "__main__":
    _META_FILES = {"quality_summary.csv", "grade_mapping.json"}
    compound_files = sorted(f for f in COMPOUND_DIR.glob("*.csv") if f.name not in _META_FILES)
    if not compound_files:
        print(f"No compound files found in {COMPOUND_DIR}")
        raise SystemExit(1)

    grade_mapping: dict[str, list[str]] = {g.value: [] for g in QualityGrade}
    grade_mapping["ungraded"] = []
    summary_rows: list[dict] = []

    for csv_path in tqdm(compound_files, desc="Grading compound files"):
        gauge_id = csv_path.stem
        compound = pd.read_csv(csv_path, index_col="date", parse_dates=True)

        compound, overall_grade, year_grades = grade_compound(compound, gauge_id)

        save_by_grade(compound, gauge_id, overall_grade, COMPOUND_DIR)

        grade_key = overall_grade if overall_grade else "ungraded"
        grade_mapping[grade_key].append(gauge_id)
        # Check full discharge coverage for summary
        if "q_mm_day" in compound.columns:
            q_span = compound.loc["2008":"2023", "q_mm_day"]
            has_full_coverage = not q_span.isna().any() and len(q_span) >= 5844
        else:
            has_full_coverage = False

        summary_rows.append(
            {
                "gauge_id": gauge_id,
                "overall_grade": overall_grade,
                "has_discharge": "q_cms" in compound.columns and compound["q_cms"].notna().any(),
                "has_level": "lvl_sm" in compound.columns and compound["lvl_sm"].notna().any(),
                "has_full_coverage": has_full_coverage,
                "n_years_graded": len(year_grades),
            }
        )

    # ── Write metadata ─────────────────────────────────────────────────────
    for grade_list in grade_mapping.values():
        grade_list.sort()

    with open(COMPOUND_DIR / "grade_mapping.json", "w") as f:
        json.dump(grade_mapping, f, indent=2)

    summary_df = pd.DataFrame(summary_rows).sort_values("gauge_id")
    summary_df.to_csv(COMPOUND_DIR / "quality_summary.csv", index=False)

    # ── Summary ────────────────────────────────────────────────────────────
    n = len(compound_files)
    print(f"\nGraded {n} compound files")
    print("\nGrade distribution:")
    for grade in [g.value for g in QualityGrade] + ["ungraded"]:
        count = len(grade_mapping[grade])
        pct = 100 * count / n if n else 0
        print(f"  Grade {grade}: {count:5d} ({pct:5.1f}%)")
