#!/usr/bin/env python3
"""Reorganize discharge files by quality grade.

This script:
1. Loads all discharge and level files
2. Runs quality assessment on discharge data
3. Merges discharge and level data
4. Adds per-year grade column
5. Saves to new structure organized by overall grade

Output structure:
    DischargeNew/
    ├── by_grade/{A,B,C,D,F}/{gauge_id}.csv
    ├── all/{gauge_id}.csv  (symlinks)
    ├── grade_mapping.json
    └── assessment_summary.csv
"""

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quality import (
    QualityGrade,
    YearQualityGrader,
    assess_gauge_quality,
    get_gauge_summary,
)


def find_discharge_file(gauge_id: str, discharge_dir: Path) -> Path | None:
    """Find discharge file for a gauge in the nested structure."""
    # Search order: full/decent, full/poor, partial/decent, partial/poor
    search_paths = [
        discharge_dir / "full" / "decent" / f"{gauge_id}.csv",
        discharge_dir / "full" / "poor" / f"{gauge_id}.csv",
        discharge_dir / "partial" / "decent" / f"{gauge_id}.csv",
        discharge_dir / "partial" / "poor" / f"{gauge_id}.csv",
    ]
    for path in search_paths:
        if path.exists():
            return path
    return None


def find_level_file(gauge_id: str, level_dir: Path) -> Path | None:
    """Find level file for a gauge."""
    path = level_dir / f"{gauge_id}.csv"
    return path if path.exists() else None


def load_discharge(path: Path) -> pd.DataFrame:
    """Load discharge CSV file."""
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return df


def load_level(path: Path) -> pd.DataFrame:
    """Load level CSV file."""
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return df


def load_meteo(gauge_id: str, meteo_dir: Path) -> pd.DataFrame | None:
    """Load meteorological data for a gauge."""
    path = meteo_dir / f"{gauge_id}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    return df


def process_gauge(
    gauge_id: str,
    discharge_dir: Path,
    level_dir: Path,
    meteo_dir: Path | None,
    hydro_year_start_month: int = 10,
) -> dict:
    """Process a single gauge: load data, assess quality, merge.

    Returns:
        Dictionary with:
        - gauge_id: Gauge identifier
        - data: Merged DataFrame with grade column (or None if no data)
        - overall_grade: Overall quality grade (A-F or None)
        - year_grades: Dict mapping year to grade
        - has_discharge: Whether discharge data exists
        - has_level: Whether level data exists
        - error: Error message if processing failed
    """
    result = {
        "gauge_id": gauge_id,
        "data": None,
        "overall_grade": None,
        "year_grades": {},
        "has_discharge": False,
        "has_level": False,
        "error": None,
    }

    try:
        # Find and load discharge
        discharge_path = find_discharge_file(gauge_id, discharge_dir)
        discharge_df = None
        if discharge_path:
            discharge_df = load_discharge(discharge_path)
            result["has_discharge"] = True

        # Find and load level
        level_path = find_level_file(gauge_id, level_dir)
        level_df = None
        if level_path:
            level_df = load_level(level_path)
            result["has_level"] = True

        # If neither exists, return early
        if discharge_df is None and level_df is None:
            result["error"] = "No discharge or level data found"
            return result

        # Run quality assessment if we have discharge
        year_grades = {}
        overall_grade = None

        if discharge_df is not None and "q_mm_day" in discharge_df.columns:
            discharge_series = discharge_df["q_mm_day"]
            discharge_series.index = pd.DatetimeIndex(discharge_series.index)

            # Load meteo if available
            precip_series = None
            if meteo_dir:
                meteo_df = load_meteo(gauge_id, meteo_dir)
                if meteo_df is not None:
                    for col in ["prcp", "precipitation", "total_precipitation", "P"]:
                        if col in meteo_df.columns:
                            precip_series = meteo_df[col]
                            precip_series.index = pd.DatetimeIndex(precip_series.index)
                            break

            # Assess quality
            try:
                year_results, summary = assess_gauge_quality(
                    discharge=discharge_series,
                    precipitation=precip_series,
                    gauge_id=gauge_id,
                    hydro_year_start_month=hydro_year_start_month,
                )

                if year_results:
                    overall_grade = summary.overall_grade.name
                    year_grades = {yr.year: yr.grade.name for yr in year_results}
                    result["overall_grade"] = overall_grade
                    result["year_grades"] = year_grades
            except Exception as e:
                # Quality assessment failed, continue without grades
                result["error"] = f"Quality assessment failed: {e}"

        # Merge discharge and level data
        if discharge_df is not None and level_df is not None:
            # Merge on date index
            merged = discharge_df.join(level_df, how="outer")
        elif discharge_df is not None:
            merged = discharge_df.copy()
            merged["lvl_sm"] = np.nan
        else:
            merged = level_df.copy()
            merged["q_cms"] = np.nan
            merged["q_mm_day"] = np.nan

        # Ensure column order
        columns = ["q_cms", "q_mm_day", "lvl_sm"]
        for col in columns:
            if col not in merged.columns:
                merged[col] = np.nan
        merged = merged[columns]

        # Add grade column based on hydrological year
        merged["grade"] = None
        if year_grades:
            for idx in merged.index:
                if pd.isna(idx):
                    continue
                # Determine hydrological year
                if hydro_year_start_month > 1:
                    if idx.month >= hydro_year_start_month:
                        hydro_year = idx.year + 1
                    else:
                        hydro_year = idx.year
                else:
                    hydro_year = idx.year

                if hydro_year in year_grades:
                    merged.loc[idx, "grade"] = year_grades[hydro_year]

        result["data"] = merged

    except Exception as e:
        result["error"] = str(e)

    return result


def save_gauge_data(
    result: dict,
    output_dir: Path,
    create_symlinks: bool = True,
) -> None:
    """Save gauge data to the new directory structure."""
    gauge_id = result["gauge_id"]
    data = result["data"]
    overall_grade = result["overall_grade"]

    if data is None:
        return

    # Determine grade folder (use "ungraded" for gauges without discharge)
    if overall_grade:
        grade_folder = overall_grade
    else:
        grade_folder = "ungraded"

    # Create grade directory
    grade_dir = output_dir / "by_grade" / grade_folder
    grade_dir.mkdir(parents=True, exist_ok=True)

    # Save to grade folder
    grade_path = grade_dir / f"{gauge_id}.csv"
    data.to_csv(grade_path)

    # Create symlink in all/ folder
    if create_symlinks:
        all_dir = output_dir / "all"
        all_dir.mkdir(parents=True, exist_ok=True)
        all_path = all_dir / f"{gauge_id}.csv"

        # Remove existing symlink if present
        if all_path.exists() or all_path.is_symlink():
            all_path.unlink()

        # Create relative symlink
        relative_target = Path("..") / "by_grade" / grade_folder / f"{gauge_id}.csv"
        all_path.symlink_to(relative_target)


def main():
    parser = argparse.ArgumentParser(
        description="Reorganize discharge files by quality grade"
    )
    parser.add_argument(
        "--discharge-dir",
        type=Path,
        default=Path("data/HydroFiles/Discharge"),
        help="Directory containing discharge files",
    )
    parser.add_argument(
        "--level-dir",
        type=Path,
        default=Path("data/HydroFiles/level_full"),
        help="Directory containing level files",
    )
    parser.add_argument(
        "--meteo-dir",
        type=Path,
        default=None,
        help="Directory containing meteorological data (optional)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/HydroFiles/DischargeNew"),
        help="Output directory for reorganized files",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--no-symlinks",
        action="store_true",
        help="Don't create symlinks in all/ folder (copy files instead)",
    )
    parser.add_argument(
        "--gauge-list",
        type=Path,
        default=None,
        help="File with list of gauge IDs to process (one per line)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Resolve paths
    discharge_dir = args.discharge_dir.resolve()
    level_dir = args.level_dir.resolve()
    output_dir = args.output_dir.resolve()
    meteo_dir = args.meteo_dir.resolve() if args.meteo_dir else None

    # Collect all gauge IDs
    print("Collecting gauge IDs...")

    discharge_gauges = set()
    for path in discharge_dir.rglob("*.csv"):
        discharge_gauges.add(path.stem)

    level_gauges = set()
    for path in level_dir.glob("*.csv"):
        level_gauges.add(path.stem)

    all_gauges = discharge_gauges | level_gauges

    # Filter by gauge list if provided
    if args.gauge_list:
        with open(args.gauge_list) as f:
            filter_gauges = set(line.strip() for line in f if line.strip())
        all_gauges = all_gauges & filter_gauges

    print(f"Found {len(all_gauges)} gauges total")
    print(f"  - Discharge only: {len(discharge_gauges - level_gauges)}")
    print(f"  - Level only: {len(level_gauges - discharge_gauges)}")
    print(f"  - Both: {len(discharge_gauges & level_gauges)}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process gauges in parallel
    print(f"\nProcessing {len(all_gauges)} gauges with {args.workers} workers...")

    results = []
    errors = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_gauge,
                gauge_id,
                discharge_dir,
                level_dir,
                meteo_dir,
            ): gauge_id
            for gauge_id in all_gauges
        }

        for i, future in enumerate(as_completed(futures), 1):
            gauge_id = futures[future]
            try:
                result = future.result()
                results.append(result)

                if result["error"] and args.verbose:
                    print(f"  Warning [{gauge_id}]: {result['error']}")

                if i % 100 == 0 or i == len(all_gauges):
                    print(f"  Processed {i}/{len(all_gauges)} gauges...")

            except Exception as e:
                errors.append((gauge_id, str(e)))
                print(f"  Error [{gauge_id}]: {e}")

    # Save results
    print(f"\nSaving {len(results)} gauge files...")

    for result in results:
        save_gauge_data(result, output_dir, create_symlinks=not args.no_symlinks)

    # Create grade mapping
    grade_mapping = {
        "A": [],
        "B": [],
        "C": [],
        "D": [],
        "F": [],
        "ungraded": [],
    }

    for result in results:
        grade = result["overall_grade"] or "ungraded"
        grade_mapping[grade].append(result["gauge_id"])

    # Sort each list
    for grade in grade_mapping:
        grade_mapping[grade] = sorted(grade_mapping[grade])

    # Save grade mapping
    mapping_path = output_dir / "grade_mapping.json"
    with open(mapping_path, "w") as f:
        json.dump(grade_mapping, f, indent=2)
    print(f"Saved grade mapping to {mapping_path}")

    # Create assessment summary
    summary_data = []
    for result in results:
        summary_data.append({
            "gauge_id": result["gauge_id"],
            "overall_grade": result["overall_grade"],
            "has_discharge": result["has_discharge"],
            "has_level": result["has_level"],
            "n_years_graded": len(result["year_grades"]),
            "error": result["error"],
        })

    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values("gauge_id")
    summary_path = output_dir / "assessment_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"Saved assessment summary to {summary_path}")

    # Print statistics
    print("\n" + "=" * 60)
    print("REORGANIZATION COMPLETE")
    print("=" * 60)

    print(f"\nOutput directory: {output_dir}")
    print(f"\nGrade distribution:")
    for grade in ["A", "B", "C", "D", "F", "ungraded"]:
        count = len(grade_mapping[grade])
        pct = 100 * count / len(results) if results else 0
        print(f"  Grade {grade}: {count:5d} ({pct:5.1f}%)")

    print(f"\nFiles created:")
    print(f"  - by_grade/*/{{gauge_id}}.csv: {len(results)} files")
    if not args.no_symlinks:
        print(f"  - all/{{gauge_id}}.csv: {len(results)} symlinks")
    print(f"  - grade_mapping.json")
    print(f"  - assessment_summary.csv")

    if errors:
        print(f"\nErrors: {len(errors)} gauges failed to process")
        for gauge_id, error in errors[:10]:
            print(f"  - {gauge_id}: {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")


if __name__ == "__main__":
    main()
