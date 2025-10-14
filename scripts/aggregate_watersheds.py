#!/usr/bin/env python3
r"""Command-line tool for aggregating meteorological data to watersheds.

This script processes gridded meteorological datasets (ERA5-Land, MSWEP, GPCP, GLEAM)
and aggregates them over watershed geometries. Supports parallel processing and
automatic caching of spatial weights.

Examples:
    # Process ERA5-Land data for all watersheds
    python aggregate_watersheds.py \\
        --dataset era5_land \\
        --input-dir data/raw/era5_land \\
        --watersheds data/Geometry/WatershedGeomCAMELS.gpkg \\
        --output-dir data/processed/era5_land

    # Process GPCP with custom grid resolution
    python aggregate_watersheds.py \\
        --dataset gpcp \\
        --input-dir data/raw/gpcp \\
        --watersheds data/Geometry/WatershedGeomCAMELS.gpkg \\
        --output-dir data/processed/gpcp \\
        --grid-res 1.0

    # Single file with specific gauge IDs
    python aggregate_watersheds.py \\
        --dataset era5_land \\
        --input-file data/raw/era5_land/2020_01.nc \\
        --watersheds data/Geometry/WatershedGeomCAMELS.gpkg \\
        --output-dir data/processed/era5_land \\
        --gauge-ids 1217 1081

Author: Refactored 2025-10
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import geopandas as gpd
from tqdm.auto import tqdm

# Adjust path for imports
sys.path.append(str(Path(__file__).parent.parent))
from src.meteo.aggregation import aggregate_watershed
from src.utils.logger import setup_logger

logger = setup_logger(
    "AggregateWatersheds", log_file="logs/aggregate_watersheds.log"
)


def filter_files_by_date(
    files: list[Path],
    start_year: int | None,
    end_year: int | None,
    start_month: int,
    end_month: int,
    logger,
) -> list[Path]:
    """Filter NetCDF files by date range based on filename patterns.

    Args:
        files: List of file paths to filter.
        start_year: Start year (inclusive), or None for no lower bound.
        end_year: End year (inclusive), or None for no upper bound.
        start_month: Start month (1-12).
        end_month: End month (1-12).
        logger: Logger instance.

    Returns:
        Filtered list of files.
    """
    if start_year is None and end_year is None:
        return files

    filtered = []
    start_yr = start_year or 1900
    end_yr = end_year or 2100

    for nc_file in files:
        stem = nc_file.stem
        try:
            # Look for 4-digit year in filename
            for i in range(len(stem) - 3):
                if stem[i : i + 4].isdigit():
                    year = int(stem[i : i + 4])
                    month = None

                    # Try to find month (formats: YYYY_MM or YYYY-MM)
                    if i + 4 < len(stem) and stem[i + 4] in ("_", "-"):
                        month_str = stem[i + 5 : i + 7]
                        if month_str.isdigit():
                            month = int(month_str)

                    # Check if in range
                    if start_yr <= year <= end_yr:
                        if month is not None:
                            # Monthly file - check month range
                            in_range = (
                                year > start_yr or month >= start_month
                            ) and (year < end_yr or month <= end_month)
                            if in_range:
                                filtered.append(nc_file)
                                break
                        else:
                            # Annual file - include if year in range
                            filtered.append(nc_file)
                            break
        except (ValueError, IndexError):
            # Can't parse date, include file
            logger.warning(
                f"Could not parse date from {nc_file.name}, including anyway"
            )
            filtered.append(nc_file)

    logger.info(
        f"Filtered {len(files)} files to {len(filtered)} "
        f"(years {start_yr}-{end_yr}, months {start_month}-{end_month})"
    )
    return filtered


def process_single_watershed(
    nc_file: Path,
    gauge_id: str,
    ws_geom,
    dataset_type: str,
    output_dir: Path,
    grid_res: float,
    small_threshold: float,
) -> tuple[str, bool, str]:
    """Process one watershed for one NetCDF file.

    Returns:
        Tuple of (gauge_id, success, message).
    """
    try:
        df = aggregate_watershed(
            dataset_path=nc_file,
            watershed_geom=ws_geom,
            gauge_id=gauge_id,
            dataset_type=dataset_type,
            grid_resolution=grid_res,
            small_ws_threshold=small_threshold,
            cache_dir=output_dir,
        )

        # Save to CSV (merge with existing)
        out_csv = output_dir / f"{gauge_id}.csv"
        if out_csv.exists():
            import pandas as pd

            existing = pd.read_csv(out_csv, index_col="date", parse_dates=True)
            df = df.combine_first(existing).sort_index()

        df.to_csv(out_csv)
        return (gauge_id, True, f"Saved to {out_csv}")

    except Exception as exc:
        return (gauge_id, False, f"Error: {exc!r}")


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Aggregate meteorological data to watersheds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Required arguments
    parser.add_argument(
        "--dataset",
        required=True,
        choices=["era5_land", "mswep", "gpcp", "gleam"],
        help="Dataset type (determines unit conversion)",
    )
    parser.add_argument(
        "--watersheds",
        required=True,
        type=Path,
        help="GeoPackage with watershed geometries (must have 'gauge_id' column)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory for CSV files",
    )

    # Input: either directory or single file
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input-dir",
        type=Path,
        help="Directory with NetCDF files (processes all)",
    )
    input_group.add_argument(
        "--input-file", type=Path, help="Single NetCDF file to process"
    )

    # Optional arguments - Date range filtering
    date_group = parser.add_argument_group("date range options")
    date_group.add_argument(
        "--start-year",
        type=int,
        help="Start year for filtering files (e.g., 2007)",
    )
    date_group.add_argument(
        "--end-year",
        type=int,
        help="End year for filtering files (e.g., 2023)",
    )
    date_group.add_argument(
        "--start-month",
        type=int,
        default=1,
        help="Start month (1-12, default: 1)",
    )
    date_group.add_argument(
        "--end-month",
        type=int,
        default=12,
        help="End month (1-12, default: 12)",
    )

    # File pattern and selection
    parser.add_argument(
        "--pattern",
        default="*.nc",
        help="Glob pattern for input files (default: *.nc)",
    )
    parser.add_argument(
        "--gauge-ids",
        nargs="+",
        help="Specific gauge IDs to process (default: all in GeoPackage)",
    )

    # Processing options
    parser.add_argument(
        "--grid-res",
        type=float,
        default=0.10,
        help="Grid resolution in degrees (default: 0.10)",
    )
    parser.add_argument(
        "--small-threshold",
        type=float,
        default=5.0,
        help="Small watershed threshold in km² (default: 5.0)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )

    args = parser.parse_args()

    # Load watersheds
    logger.info(f"Loading watersheds from {args.watersheds}")
    ws_gdf = gpd.read_file(args.watersheds)

    if "gauge_id" not in ws_gdf.columns:
        logger.error("GeoPackage must have 'gauge_id' column")
        sys.exit(1)

    ws_gdf.set_index("gauge_id", inplace=True)

    # Filter gauge IDs if specified
    if args.gauge_ids:
        ws_gdf = ws_gdf.loc[args.gauge_ids]
        logger.info(f"Processing {len(ws_gdf)} specified gauge IDs")
    else:
        logger.info(f"Processing all {len(ws_gdf)} watersheds")

    # Get input files
    if args.input_file:
        nc_files = [args.input_file]
    else:
        # Get all files matching pattern
        all_files = sorted(args.input_dir.glob(args.pattern))

        # Filter by date range if specified
        nc_files = filter_files_by_date(
            all_files,
            args.start_year,
            args.end_year,
            args.start_month,
            args.end_month,
            logger,
        )

    if not nc_files:
        logger.error(
            f"No NetCDF files found matching pattern '{args.pattern}' and date range"
        )
        sys.exit(1)

    logger.info(f"Processing {len(nc_files)} NetCDF files")

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Process files sequentially, parallelize gauges within each file
    # This keeps memory usage bounded (only 1 NetCDF in memory at once)
    total_files = len(nc_files)
    total_gauges = len(ws_gdf)
    logger.info(f"Processing {total_files} files × {total_gauges} gauges")

    successes = 0
    failures = 0

    # Outer loop: iterate over NetCDF files (sequential)
    for file_idx, nc_file in enumerate(nc_files, 1):
        logger.info(
            f"[{file_idx}/{total_files}] Processing file: {nc_file.name}"
        )

        # Build tasks for all gauges for this file
        tasks = []
        for gauge_id, row in ws_gdf.iterrows():
            tasks.append(
                (
                    nc_file,
                    str(gauge_id),
                    row.geometry,
                    args.dataset,
                    args.output_dir,
                    args.grid_res,
                    args.small_threshold,
                )
            )

        # Inner loop: parallelize across gauges (bounded memory)
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_single_watershed, *task): task
                for task in tasks
            }

            with tqdm(
                total=total_gauges,
                desc=f"File {file_idx}/{total_files}",
                leave=False,
            ) as pbar:
                for future in as_completed(futures):
                    gauge_id, success, message = future.result()
                    if success:
                        successes += 1
                        logger.debug(message)
                    else:
                        failures += 1
                        logger.error(f"Gauge {gauge_id}: {message}")
                    pbar.update(1)

    # Summary
    logger.info(f"Complete: {successes} successes, {failures} failures")
    if failures > 0:
        logger.warning(f"Check logs for {failures} failed tasks")


if __name__ == "__main__":
    main()
