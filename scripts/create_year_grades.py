#!/usr/bin/env python3
"""Generate per-year quality grade matrix for CAMELS-RU release.

Reads the GradeCompound output (by_grade/ directories with per-day grade column)
and produces:
  1. camels_ru_year_grades.csv  — gauge_id × hydro_year matrix with letter grades
  2. camels_ru_gauge_summary.csv — per-gauge overall grade + year counts + recommendation

The year_grades CSV enables modelers to filter bad years before calibration/validation,
preventing the common problem where a D/F year in the validation window silently
corrupts model performance metrics.

Usage:
    python create_year_grades.py [--compound-dir PATH] [--output-dir PATH]
"""

import argparse
from pathlib import Path
import sys

import pandas as pd
from tqdm.auto import tqdm

sys.path.append(str(Path(__file__).parent.parent))

# Grade encoding for numeric operations (lower = better)
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
HYDRO_YEAR_START_MONTH = 10


def extract_year_grades(compound_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract per-year grades from graded compound CSVs.

    Reads CSVs from by_grade/{A,B,C,D,F}/ directories, extracts the per-day
    grade column, and aggregates to hydro-year level (mode of daily grades
    within each hydro-year).

    Args:
        compound_dir: Directory containing by_grade/ subdirectories.

    Returns:
        Tuple of (year_grades_df, gauge_summary_df).
    """
    by_grade_dir = compound_dir / "by_grade"
    if not by_grade_dir.exists():
        raise FileNotFoundError(f"by_grade/ directory not found in {compound_dir}")

    # Collect all graded CSVs
    grade_dirs = ["A", "B", "C", "D", "F"]
    all_files: list[tuple[str, Path]] = []
    for grade_letter in grade_dirs:
        grade_path = by_grade_dir / grade_letter
        if grade_path.exists():
            for csv_file in sorted(grade_path.glob("*.csv")):
                all_files.append((csv_file.stem, csv_file))

    # Also check ungraded
    ungraded_path = by_grade_dir / "ungraded"
    if ungraded_path.exists():
        for csv_file in sorted(ungraded_path.glob("*.csv")):
            all_files.append((csv_file.stem, csv_file))

    if not all_files:
        raise FileNotFoundError(f"No CSV files found in {by_grade_dir}")

    # Extract year grades from each gauge
    rows: list[dict[str, str]] = []

    for gauge_id, csv_path in tqdm(all_files, desc="Extracting year grades"):
        df = pd.read_csv(csv_path, index_col="date", parse_dates=True)

        if "grade" not in df.columns:
            continue

        # Assign hydro-year
        months = df.index.month
        years = df.index.year
        df["hydro_year"] = years.where(months < HYDRO_YEAR_START_MONTH, years + 1)

        # Get dominant grade per hydro-year (mode)
        for hy, group in df.groupby("hydro_year"):
            year_grades = group["grade"].dropna()
            if len(year_grades) == 0:
                continue
            # Mode = most common grade in this hydro-year
            mode_grade = year_grades.mode()
            if len(mode_grade) > 0:
                rows.append(
                    {
                        "gauge_id": gauge_id,
                        "hydro_year": int(hy),
                        "grade": str(mode_grade.iloc[0]),
                    }
                )

    if not rows:
        raise ValueError("No year grades extracted from any gauge")

    # Pivot to gauge × year matrix
    # Deduplicate: a gauge may appear in multiple by_grade/ dirs (old + new).
    grades_long = pd.DataFrame(rows)
    grades_long = grades_long.drop_duplicates(subset=["gauge_id", "hydro_year"], keep="last")
    year_grades_df = grades_long.pivot(index="gauge_id", columns="hydro_year", values="grade")
    year_grades_df.columns = [str(int(c)) for c in year_grades_df.columns]
    year_grades_df = year_grades_df.sort_index()

    # Create gauge summary
    summary_rows = []
    for gauge_id in year_grades_df.index:
        row = year_grades_df.loc[gauge_id]
        grades = row.dropna().tolist()
        n_total = len(grades)

        if n_total == 0:
            summary_rows.append(
                {
                    "gauge_id": gauge_id,
                    "overall_grade": "F",
                    "n_years": 0,
                    "n_A": 0,
                    "n_B": 0,
                    "n_C": 0,
                    "n_D": 0,
                    "n_F": 0,
                    "worst_grade": "F",
                    "recommendation": "Exclude",
                }
            )
            continue

        n_a = grades.count("A")
        n_b = grades.count("B")
        n_c = grades.count("C")
        n_d = grades.count("D")
        n_f = grades.count("F")

        # Strict Grade A: every year must be A
        if all(g == "A" for g in grades):
            overall = "A"
        else:
            # Mode of non-F grades, capped at B
            usable = [g for g in grades if g != "F"]
            if usable:
                from collections import Counter

                freq = Counter(usable)
                mode_grade = freq.most_common(1)[0][0]
                overall = mode_grade if mode_grade != "A" else "B"
            else:
                overall = "F"

            # Apply coverage caps
            usable_frac = len([g for g in grades if g in ("A", "B", "C")]) / n_total
            fail_frac = n_f / n_total

            if usable_frac < 0.5:
                overall = max(overall, "D", key=lambda g: GRADE_ORDER.get(g, 99))
            elif usable_frac < 0.7:
                overall = max(overall, "C", key=lambda g: GRADE_ORDER.get(g, 99))
            elif fail_frac > 0.3:
                overall = max(overall, "B", key=lambda g: GRADE_ORDER.get(g, 99))

        worst = max(grades, key=lambda g: GRADE_ORDER.get(g, 99))

        if overall in ("A", "B") and (n_a + n_b + n_c) / n_total >= 0.8:
            rec = "Include"
        elif overall == "C" or (n_a + n_b + n_c) / n_total >= 0.5:
            rec = "Use with caution"
        else:
            rec = "Exclude"

        summary_rows.append(
            {
                "gauge_id": gauge_id,
                "overall_grade": overall,
                "n_years": n_total,
                "n_A": n_a,
                "n_B": n_b,
                "n_C": n_c,
                "n_D": n_d,
                "n_F": n_f,
                "worst_grade": worst,
                "recommendation": rec,
            }
        )

    gauge_summary_df = pd.DataFrame(summary_rows).set_index("gauge_id").sort_index()

    return year_grades_df, gauge_summary_df


def main() -> None:
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Generate per-year quality grade matrix for CAMELS-RU",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--compound-dir",
        type=Path,
        default=Path("data/CAMELS_RU/HydroData/Compound"),
        help="Directory containing by_grade/ subdirectories",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("release/CAMELS_RU_v1.0"),
        help="Output directory for CSV files",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading graded data from {args.compound_dir}")
    year_grades_df, gauge_summary_df = extract_year_grades(args.compound_dir)

    # Save year grades matrix
    year_grades_path = args.output_dir / "camels_ru_year_grades.csv"
    year_grades_df.to_csv(year_grades_path)
    print(f"Year grades matrix: {year_grades_path}")
    print(f"  Shape: {year_grades_df.shape[0]} gauges × {year_grades_df.shape[1]} years")

    # Save gauge summary
    summary_path = args.output_dir / "camels_ru_gauge_summary.csv"
    gauge_summary_df.to_csv(summary_path)
    print(f"Gauge summary: {summary_path}")

    # Print grade distribution
    print("\nOverall grade distribution (strict Grade A):")
    grade_counts = gauge_summary_df["overall_grade"].value_counts().sort_index()
    n_total = len(gauge_summary_df)
    for grade, count in grade_counts.items():
        pct = 100 * count / n_total
        print(f"  Grade {grade}: {count:5d} ({pct:5.1f}%)")

    # Print recommendation distribution
    print("\nRecommendation distribution:")
    rec_counts = gauge_summary_df["recommendation"].value_counts()
    for rec, count in rec_counts.items():
        pct = 100 * count / n_total
        print(f"  {rec}: {count:5d} ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
