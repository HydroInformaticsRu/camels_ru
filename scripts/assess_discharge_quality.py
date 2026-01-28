#!/usr/bin/env python3
"""Assess discharge data quality for CAMELS-RU gauges.

This script performs automated quality assessment on discharge time series,
evaluating data at the year level using statistical analysis against
climatological patterns and meteorological forcing.

Output files:
- quality_assessment.csv: Per-year quality grades and metrics
- gauge_quality_summary.csv: Per-gauge summary with recommendations

Usage:
    # Full assessment (all gauges) - reports only
    python assess_discharge_quality.py \\
        --discharge-dir data/HydroFiles/Discharge \\
        --meteo-dir data/MeteoData/CamelsRU \\
        --output-dir output/quality_assessment \\
        --workers 8

    # With file reorganization
    python assess_discharge_quality.py \\
        --discharge-dir data/HydroFiles/Discharge \\
        --meteo-dir data/MeteoData/CamelsRU \\
        --output-dir output/quality_assessment \\
        --reorganize \\
        --backup-dir output/backup \\
        --workers 8

    # Dry-run (show what would be moved)
    python assess_discharge_quality.py \\
        --discharge-dir data/HydroFiles/Discharge \\
        --reorganize --dry-run

    # Single gauge (debugging)
    python assess_discharge_quality.py \\
        --gauge-id 19135 \\
        --verbose --plot

    # Reassess specific gauges
    python assess_discharge_quality.py \\
        --gauge-list problematic_gauges.txt
"""

import argparse
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quality import assess_gauge_quality, QualityGrade
from src.quality.quality_grader import results_to_dataframe, GaugeQualitySummary
from src.utils.logger import setup_logger

logger = setup_logger("QualityAssessment", log_file="logs/quality_assessment.log")

# Constants
START_DATE = "2008-01-01"
END_DATE = "2023-12-31"
TIME_INDEX = pd.date_range(START_DATE, END_DATE, freq="D")
MIN_YEARS_FOR_ASSESSMENT = 3


def load_discharge_series(gauge_id: str, base_dir: Path) -> pd.Series | None:
    """Load discharge time series for a gauge from CSV files.

    Args:
        gauge_id: Gauge identifier.
        base_dir: Base directory containing Discharge/ folders.

    Returns:
        Discharge series with datetime index (mm/day) or None if not found.
    """
    # Search directories in order of preference
    search_dirs = [
        "full/decent",
        "partial/decent",
        "full/poor",
        "partial/poor",
    ]

    for search_dir in search_dirs:
        csv_path = base_dir / search_dir / f"{gauge_id}.csv"
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
                # Try different column names
                for col in ["q_mm_day", "discharge_mm", "discharge"]:
                    if col in df.columns:
                        series = df[col]
                        series = series.reindex(TIME_INDEX)
                        return series
                logger.warning(f"No discharge column found in {csv_path}")
                return None
            except Exception as e:
                logger.error(f"Error loading {csv_path}: {e}")
                return None

    return None


def get_discharge_file_path(gauge_id: str, base_dir: Path) -> Path | None:
    """Get the path to the discharge file for a gauge.

    Args:
        gauge_id: Gauge identifier.
        base_dir: Base directory containing Discharge/ folders.

    Returns:
        Path to the discharge file or None if not found.
    """
    search_dirs = [
        "full/decent",
        "partial/decent",
        "full/poor",
        "partial/poor",
    ]

    for search_dir in search_dirs:
        csv_path = base_dir / search_dir / f"{gauge_id}.csv"
        if csv_path.exists():
            return csv_path

    return None


def load_precipitation_series(gauge_id: str, meteo_dir: Path) -> pd.Series | None:
    """Load precipitation time series for a gauge.

    Args:
        gauge_id: Gauge identifier.
        meteo_dir: Directory containing precipitation CSV files.

    Returns:
        Precipitation series (mm/day) or None if not found.
    """
    # Try different subdirectories
    subdirs = ["era5", "mswep", ""]

    for subdir in subdirs:
        if subdir:
            csv_path = meteo_dir / subdir / f"{gauge_id}.csv"
        else:
            csv_path = meteo_dir / f"{gauge_id}.csv"

        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
                # Try different column names
                for col in ["prcp", "precipitation", "total_precipitation", "P"]:
                    if col in df.columns:
                        series = df[col]
                        series = series.reindex(TIME_INDEX)
                        return series
            except Exception as e:
                logger.debug(f"Error loading precipitation {csv_path}: {e}")
                continue

    return None


def process_single_gauge(
    gauge_id: str,
    discharge_dir: Path,
    meteo_dir: Path | None,
    hydro_year_start_month: int = 10,
) -> tuple[str, list[dict], dict | None]:
    """Process a single gauge and return quality assessment results.

    Args:
        gauge_id: Gauge identifier.
        discharge_dir: Base directory for discharge data.
        meteo_dir: Directory for meteorological data.
        hydro_year_start_month: Start month of hydrological year.

    Returns:
        Tuple of (gauge_id, list of year result dicts, summary dict or None).
    """
    try:
        # Load discharge
        discharge = load_discharge_series(gauge_id, discharge_dir)
        if discharge is None:
            return gauge_id, [], None

        # Check if enough data
        valid_data = discharge.dropna()
        if len(valid_data) < 365 * MIN_YEARS_FOR_ASSESSMENT:
            logger.debug(f"Gauge {gauge_id}: insufficient data for assessment")
            return gauge_id, [], None

        # Load precipitation (optional)
        precipitation = None
        if meteo_dir is not None:
            precipitation = load_precipitation_series(gauge_id, meteo_dir)

        # Perform assessment
        year_results, summary = assess_gauge_quality(
            discharge,
            precipitation=precipitation,
            gauge_id=gauge_id,
            hydro_year_start_month=hydro_year_start_month,
            min_years=MIN_YEARS_FOR_ASSESSMENT,
        )

        # Convert to dicts for serialization
        year_dicts = [r.to_dict() for r in year_results]
        for d in year_dicts:
            d["gauge_id"] = gauge_id

        summary_dict = summary.to_dict() if summary else None

        return gauge_id, year_dicts, summary_dict

    except Exception as e:
        logger.error(f"Error processing gauge {gauge_id}: {e}")
        return gauge_id, [], None


def scan_for_gauges(discharge_dir: Path) -> list[str]:
    """Scan discharge directories for available gauge IDs.

    Args:
        discharge_dir: Base directory containing Discharge/ folders.

    Returns:
        Sorted list of gauge IDs.
    """
    gauge_ids = set()
    search_dirs = [
        "full/decent",
        "partial/decent",
        "full/poor",
        "partial/poor",
    ]

    for search_dir in search_dirs:
        dir_path = discharge_dir / search_dir
        if dir_path.exists():
            for csv_file in dir_path.glob("*.csv"):
                gauge_ids.add(csv_file.stem)

    return sorted(list(gauge_ids))


def reorganize_files(
    discharge_dir: Path,
    summaries: list[dict],
    backup_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """Reorganize discharge files based on quality assessment.

    Args:
        discharge_dir: Base directory for discharge data.
        summaries: List of gauge summary dicts.
        backup_dir: Directory for backups (optional).
        dry_run: If True, only report what would be done.

    Returns:
        Dict mapping action to list of gauge_ids.
    """
    actions = {
        "moved_to_decent": [],
        "moved_to_poor": [],
        "unchanged": [],
        "not_found": [],
    }

    for summary in summaries:
        gauge_id = summary["gauge_id"]
        new_tier = summary["new_tier"]

        # Find current file
        current_path = get_discharge_file_path(gauge_id, discharge_dir)
        if current_path is None:
            actions["not_found"].append(gauge_id)
            continue

        # Determine current tier
        current_tier = "decent" if "/decent/" in str(current_path) else "poor"
        current_coverage = "full" if "/full/" in str(current_path) else "partial"

        # Skip if already in correct tier
        if current_tier == new_tier:
            actions["unchanged"].append(gauge_id)
            continue

        # Determine new path
        new_dir = discharge_dir / current_coverage / new_tier
        new_path = new_dir / f"{gauge_id}.csv"

        if dry_run:
            logger.info(f"[DRY-RUN] Would move {current_path} -> {new_path}")
        else:
            # Create backup if requested
            if backup_dir is not None:
                backup_path = backup_dir / current_coverage / current_tier / f"{gauge_id}.csv"
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(current_path, backup_path)
                logger.debug(f"Backed up {current_path} to {backup_path}")

            # Move file
            new_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current_path), str(new_path))
            logger.info(f"Moved {current_path} -> {new_path}")

        if new_tier == "decent":
            actions["moved_to_decent"].append(gauge_id)
        else:
            actions["moved_to_poor"].append(gauge_id)

    return actions


def create_quality_report(
    output_dir: Path,
    year_df: pd.DataFrame,
    summary_df: pd.DataFrame,
) -> None:
    """Create a text summary report of quality assessment.

    Args:
        output_dir: Output directory.
        year_df: DataFrame with per-year results.
        summary_df: DataFrame with gauge summaries.
    """
    report_path = output_dir / "quality_report.txt"

    with open(report_path, "w") as f:
        f.write("CAMELS-RU Discharge Quality Assessment Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Generated: {pd.Timestamp.now()}\n")
        f.write(f"Period: {START_DATE} to {END_DATE}\n")
        f.write(f"Minimum years for assessment: {MIN_YEARS_FOR_ASSESSMENT}\n\n")

        # Overall statistics
        f.write("OVERALL STATISTICS\n")
        f.write("-" * 60 + "\n")
        f.write(f"Total gauges assessed: {len(summary_df)}\n")
        f.write(f"Total year-gauge observations: {len(year_df)}\n\n")

        # Grade distribution (gauges)
        f.write("Gauge-level grade distribution:\n")
        gauge_grades = summary_df["overall_grade"].value_counts().sort_index()
        for grade, count in gauge_grades.items():
            pct = count / len(summary_df) * 100
            f.write(f"  Grade {grade}: {count:4d} ({pct:5.1f}%)\n")
        f.write("\n")

        # Grade distribution (years)
        f.write("Year-level grade distribution:\n")
        year_grades = year_df["grade"].value_counts().sort_index()
        for grade, count in year_grades.items():
            pct = count / len(year_df) * 100
            f.write(f"  Grade {grade}: {count:5d} ({pct:5.1f}%)\n")
        f.write("\n")

        # Recommendation distribution
        f.write("Recommendation distribution:\n")
        recs = summary_df["recommendation"].value_counts()
        for rec, count in recs.items():
            pct = count / len(summary_df) * 100
            f.write(f"  {rec}: {count:4d} ({pct:5.1f}%)\n")
        f.write("\n")

        # Most common flags
        f.write("Most common quality flags:\n")
        all_flags = []
        for flags_str in year_df["flag_codes"].dropna():
            if flags_str:
                all_flags.extend(flags_str.split(","))
        if all_flags:
            flag_counts = pd.Series(all_flags).value_counts().head(10)
            for flag, count in flag_counts.items():
                f.write(f"  {flag}: {count}\n")
        f.write("\n")

        # Metrics summary
        f.write("Quality metrics summary (year-level):\n")
        f.write("-" * 60 + "\n")
        metrics = [
            "clim_correlation",
            "event_response_rate",
            "flashiness_index",
            "data_completeness",
        ]
        for metric in metrics:
            if metric in year_df.columns:
                valid = year_df[metric].dropna()
                if len(valid) > 0:
                    f.write(f"\n{metric}:\n")
                    f.write(f"  Mean: {valid.mean():.3f}\n")
                    f.write(f"  Median: {valid.median():.3f}\n")
                    f.write(f"  Std: {valid.std():.3f}\n")
                    f.write(f"  Range: [{valid.min():.3f}, {valid.max():.3f}]\n")

        # Problematic gauges
        f.write("\n" + "=" * 60 + "\n")
        f.write("PROBLEMATIC GAUGES (Overall Grade F)\n")
        f.write("-" * 60 + "\n")
        problem_gauges = summary_df[summary_df["overall_grade"] == "F"]
        if len(problem_gauges) > 0:
            for _, row in problem_gauges.head(50).iterrows():
                f.write(f"  {row['gauge_id']}: {row['n_years_fail']} failed years\n")
            if len(problem_gauges) > 50:
                f.write(f"  ... and {len(problem_gauges) - 50} more\n")
        else:
            f.write("  None\n")

    logger.info(f"Report saved to {report_path}")


def plot_gauge_quality(
    gauge_id: str,
    discharge: pd.Series,
    year_results: list[dict],
    precipitation: pd.Series | None = None,
    output_dir: Path | None = None,
) -> None:
    """Create diagnostic plots for a single gauge.

    Args:
        gauge_id: Gauge identifier.
        discharge: Discharge time series.
        year_results: List of year result dicts.
        precipitation: Optional precipitation time series.
        output_dir: Directory to save plots (or show if None).
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        logger.warning("matplotlib not available for plotting")
        return

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Plot 1: Discharge time series with quality colors
    ax1 = axes[0]
    ax1.plot(discharge.index, discharge.values, "b-", alpha=0.5, linewidth=0.5)

    # Color background by year grade
    grade_colors = {
        "A": "#2ecc71",  # Green
        "B": "#3498db",  # Blue
        "C": "#f1c40f",  # Yellow
        "D": "#e67e22",  # Orange
        "F": "#e74c3c",  # Red
    }

    for result in year_results:
        year = result["year"]
        grade = result["grade"]
        start = pd.Timestamp(year=year - 1, month=10, day=1)
        end = pd.Timestamp(year=year, month=9, day=30)
        ax1.axvspan(start, end, alpha=0.2, color=grade_colors.get(grade, "gray"))

    ax1.set_ylabel("Discharge (mm/day)")
    ax1.set_title(f"Gauge {gauge_id} - Discharge Quality Assessment")

    # Add legend
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor=color, alpha=0.3, label=f"Grade {grade}")
        for grade, color in grade_colors.items()
    ]
    ax1.legend(handles=legend_elements, loc="upper right", ncol=5)

    # Plot 2: Quality metrics
    ax2 = axes[1]
    years = [r["year"] for r in year_results]
    corr = [r["clim_correlation"] for r in year_results]
    response = [r["event_response_rate"] for r in year_results]

    ax2.bar(
        [y - 0.2 for y in years],
        corr,
        width=0.4,
        label="Clim. Correlation",
        alpha=0.7,
    )
    ax2.bar(
        [y + 0.2 for y in years],
        response,
        width=0.4,
        label="Event Response",
        alpha=0.7,
    )
    ax2.axhline(y=0.5, color="r", linestyle="--", alpha=0.5, label="Threshold")
    ax2.set_ylabel("Metric Value")
    ax2.legend(loc="upper right")
    ax2.set_ylim(0, 1.1)

    # Plot 3: Precipitation if available
    ax3 = axes[2]
    if precipitation is not None:
        ax3.bar(
            precipitation.index,
            precipitation.values,
            width=1,
            color="blue",
            alpha=0.5,
        )
        ax3.set_ylabel("Precipitation (mm/day)")
    else:
        ax3.text(
            0.5,
            0.5,
            "Precipitation data not available",
            ha="center",
            va="center",
            transform=ax3.transAxes,
        )
        ax3.set_ylabel("Precipitation")

    ax3.set_xlabel("Date")
    ax3.xaxis.set_major_locator(mdates.YearLocator())
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.tight_layout()

    if output_dir is not None:
        plot_path = output_dir / f"gauge_{gauge_id}_quality.png"
        plt.savefig(plot_path, dpi=150, bbox_inches="tight")
        plt.close()
        logger.info(f"Plot saved to {plot_path}")
    else:
        plt.show()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Assess discharge data quality for CAMELS-RU gauges",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input/output paths
    parser.add_argument(
        "--discharge-dir",
        type=Path,
        default=Path("data/HydroFiles/Discharge"),
        help="Base directory containing Discharge/ folders",
    )
    parser.add_argument(
        "--meteo-dir",
        type=Path,
        default=None,
        help="Directory for meteorological data (optional)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/quality_assessment"),
        help="Output directory for results",
    )

    # Processing options
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--gauge-id",
        type=str,
        help="Process a single gauge (for debugging)",
    )
    parser.add_argument(
        "--gauge-list",
        type=Path,
        help="File with gauge IDs to process (one per line)",
    )

    # Reorganization options
    parser.add_argument(
        "--reorganize",
        action="store_true",
        help="Reorganize files based on quality assessment",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="Directory for backups before reorganization",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    # Output options
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate diagnostic plots (single gauge mode only)",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Get gauge list
    if args.gauge_id:
        gauge_ids = [args.gauge_id]
    elif args.gauge_list and args.gauge_list.exists():
        with open(args.gauge_list) as f:
            gauge_ids = [line.strip() for line in f if line.strip()]
    else:
        logger.info("Scanning for available gauges...")
        gauge_ids = scan_for_gauges(args.discharge_dir)

    n_gauges = len(gauge_ids)
    logger.info(f"Processing {n_gauges} gauges with {args.workers} workers")

    # Single gauge mode
    if args.gauge_id:
        gauge_id, year_results, summary = process_single_gauge(
            args.gauge_id,
            args.discharge_dir,
            args.meteo_dir,
        )

        if not year_results:
            logger.error(f"No results for gauge {args.gauge_id}")
            return

        # Print results
        print(f"\nGauge: {gauge_id}")
        print("-" * 60)
        if summary:
            print(f"Overall Grade: {summary['overall_grade']}")
            print(f"Recommendation: {summary['recommendation']}")
            print(f"Usable years: {summary['n_years_usable']} / {summary['n_years_total']}")
            if summary["excluded_years"]:
                print(f"Excluded years: {summary['excluded_years']}")

        print("\nPer-year results:")
        for r in year_results:
            flags_str = r["flag_codes"] if r["flag_codes"] else "none"
            print(
                f"  {r['year']}: Grade {r['grade']} | "
                f"Corr={r['clim_correlation']:.2f} | "
                f"Response={r['event_response_rate']:.2f} | "
                f"Flags: {flags_str}"
            )

        # Generate plot if requested
        if args.plot:
            discharge = load_discharge_series(args.gauge_id, args.discharge_dir)
            precipitation = None
            if args.meteo_dir:
                precipitation = load_precipitation_series(args.gauge_id, args.meteo_dir)

            plot_gauge_quality(
                args.gauge_id,
                discharge,
                year_results,
                precipitation,
                args.output_dir if not args.dry_run else None,
            )

        return

    # Batch processing mode
    all_year_results = []
    all_summaries = []
    failed_gauges = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_single_gauge,
                gauge_id,
                args.discharge_dir,
                args.meteo_dir,
            ): gauge_id
            for gauge_id in gauge_ids
        }

        for future in tqdm(
            as_completed(futures),
            total=n_gauges,
            desc="Assessing quality",
        ):
            gauge_id = futures[future]
            try:
                _, year_results, summary = future.result()
                if year_results:
                    all_year_results.extend(year_results)
                if summary:
                    all_summaries.append(summary)
                else:
                    failed_gauges.append(gauge_id)
            except Exception as e:
                logger.error(f"Exception for gauge {gauge_id}: {e}")
                failed_gauges.append(gauge_id)

    logger.info(f"Successfully processed {len(all_summaries)} / {n_gauges} gauges")
    logger.info(f"Failed or insufficient data: {len(failed_gauges)} gauges")

    if not all_year_results:
        logger.error("No valid results to save!")
        return

    # Create DataFrames
    year_df = pd.DataFrame(all_year_results)
    summary_df = pd.DataFrame(all_summaries)

    # Sort
    year_df = year_df.sort_values(["gauge_id", "year"]).reset_index(drop=True)
    summary_df = summary_df.sort_values("gauge_id").reset_index(drop=True)

    # Save results
    year_path = args.output_dir / "quality_assessment.csv"
    summary_path = args.output_dir / "gauge_quality_summary.csv"

    year_df.to_csv(year_path, index=False)
    summary_df.to_csv(summary_path, index=False)

    logger.info(f"Year-level results saved to {year_path}")
    logger.info(f"Gauge summaries saved to {summary_path}")

    # Create report
    create_quality_report(args.output_dir, year_df, summary_df)

    # Reorganize files if requested
    if args.reorganize:
        logger.info("Reorganizing files based on quality assessment...")
        actions = reorganize_files(
            args.discharge_dir,
            all_summaries,
            backup_dir=args.backup_dir,
            dry_run=args.dry_run,
        )

        print("\nReorganization summary:")
        print(f"  Moved to decent: {len(actions['moved_to_decent'])}")
        print(f"  Moved to poor: {len(actions['moved_to_poor'])}")
        print(f"  Unchanged: {len(actions['unchanged'])}")
        print(f"  Not found: {len(actions['not_found'])}")

    # Print summary
    print("\n" + "=" * 60)
    print("QUALITY ASSESSMENT COMPLETE")
    print("=" * 60)
    print(f"Gauges assessed: {len(summary_df)}")
    print(f"Year observations: {len(year_df)}")
    print("\nGauge-level grade distribution:")
    for grade in ["A", "B", "C", "D", "F"]:
        count = (summary_df["overall_grade"] == grade).sum()
        pct = count / len(summary_df) * 100
        print(f"  Grade {grade}: {count:4d} ({pct:5.1f}%)")

    print("\nRecommendation distribution:")
    for rec in summary_df["recommendation"].unique():
        count = (summary_df["recommendation"] == rec).sum()
        pct = count / len(summary_df) * 100
        print(f"  {rec}: {count:4d} ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
