#!/usr/bin/env python3
r"""Aggregate gridded meteorological data to watershed-scale CSV files.

This script processes gridded meteorological datasets (ERA5-Land, GPCP, MSWEP, GLEAM)
and aggregates them to watershed geometries. It supports both weighted aggregation
for small watersheds and simple spatial aggregation for large watersheds.

Features:
- Multi-dataset support with configurable scaling coefficients
- Parallel processing for multiple watersheds
- Automatic detection of small vs. large watersheds
- Cached weight computation for efficiency
- CSV output with incremental merge capability
- Comprehensive logging and error handling

Usage Examples:
    # Basic usage with ERA5-Land data
    python aggregate_meteo_to_watersheds.py \
        --dataset era5_land \
        --input-dir /path/to/era5/monthly \
        --geometry-file data/Geometry/WatershedGeomCAMELS.gpkg \
        --output-dir data/MeteoData/CamelsRU/era5_land

    # GPCP data with custom date range
    python aggregate_meteo_to_watersheds.py \
        --dataset gpcp \
        --input-dir /path/to/gpcp \
        --geometry-file data/Geometry/WatershedGeomCAMELS.gpkg \
        --output-dir data/MeteoData/CamelsRU/gpcp \
        --start-year 2010 \
        --end-year 2020

    # Custom scaling coefficients and threshold
    python aggregate_meteo_to_watersheds.py \
        --dataset custom \
        --input-dir /path/to/data \
        --geometry-file data/Geometry/WatershedGeomCAMELS.gpkg \
        --output-dir data/MeteoData/output \
        --precip-coeff 1.5 \
        --area-coeff 1000 \
        --small-ws-threshold 10000

    # Single month processing with specific grid resolution
    python aggregate_meteo_to_watersheds.py \
        --dataset era5_land \
        --input-dir /path/to/era5 \
        --geometry-file data/Geometry/WatershedGeomCAMELS.gpkg \
        --output-dir data/MeteoData/output \
        --grid-res 0.25 \
        --pattern "*2020_01*.nc"
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import logging
import multiprocessing as mp
from pathlib import Path
import sys

import geopandas as gpd
from tqdm.auto import tqdm
import xarray as xr

sys.path.append(str(Path(__file__).parent.parent))
from src.meteo.processing import aggregate_to_watershed
from src.utils.logger import setup_logger


def process_watershed(args: tuple) -> None:
    """Worker function to process a single watershed.

    Args:
        args: Tuple containing (ds, ws_geom, gage_id, output_path, config, logger).
    """
    ds, ws_geom, gage_id, output_path, config, logger = args
    try:
        aggregate_to_watershed(
            nc=ds,
            ws_geom=ws_geom,
            gauge_id=gage_id,
            output_path=output_path,
            dataset=config["dataset"],
            grid_res=config["grid_res"],
            small_ws_threshold=config["small_ws_threshold"],
            precip_col=config["precip_col"],
            precip_coeff=config.get("precip_coeff"),
            area_coeff=config.get("area_coeff"),
        )
    except Exception as exc:
        logger.error(f"Failed to process gage {gage_id}: {exc!r}")


def build_argument_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser with all CLI options."""
    parser = argparse.ArgumentParser(
        description="Aggregate gridded meteorological data to watersheds.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Required arguments
    required = parser.add_argument_group("required arguments")
    required.add_argument(
        "--dataset",
        required=True,
        choices=["era5_land", "mswep", "gpcp", "gleam", "custom"],
        help=(
            "Dataset type. Determines default scaling coefficients:\n"
            "  era5_land: precip=1e2, area=1e4 (m to mm conversion)\n"
            "  mswep: precip=1e0, area=1e2 (already in mm)\n"
            "  gpcp: precip=1e1, area=1e3 (mm/hr to mm/day)\n"
            "  gleam: precip=1e0, area=1e4 (ET in mm)\n"
            "  custom: requires --precip-coeff and --area-coeff"
        ),
    )
    required.add_argument(
        "--input-dir",
        required=True,
        type=Path,
        help="Directory containing input NetCDF files.",
    )
    required.add_argument(
        "--geometry-file",
        required=True,
        type=Path,
        help="GeoPackage file with watershed geometries (must have 'gauge_id' column).",
    )
    required.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory for aggregated CSV files.",
    )

    # Date range arguments
    date_group = parser.add_argument_group("date range options")
    date_group.add_argument(
        "--start-year",
        type=int,
        default=2007,
        help="Start year for processing (default: 2007).",
    )
    date_group.add_argument(
        "--end-year",
        type=int,
        default=2025,
        help="End year for processing (default: 2025).",
    )
    date_group.add_argument(
        "--start-month",
        type=int,
        default=1,
        help="Start month (1-12, default: 1).",
    )
    date_group.add_argument(
        "--end-month",
        type=int,
        default=12,
        help="End month (1-12, default: 12).",
    )
    date_group.add_argument(
        "--pattern",
        type=str,
        help=('Custom file pattern (overrides date range). Example: "*2020_*.nc" or "era5_*.nc"'),
    )

    # Processing options
    proc_group = parser.add_argument_group("processing options")
    proc_group.add_argument(
        "--grid-res",
        type=float,
        default=0.10,
        help=(
            "Grid resolution in decimal degrees (default: 0.10). "
            "Common values: ERA5-Land=0.10, GPCP=1.0, MSWEP=0.10"
        ),
    )
    proc_group.add_argument(
        "--small-ws-threshold",
        type=float,
        default=5000,
        help=(
            "Threshold for small watershed in m² (default: 5000). "
            "Watersheds below this use weighted aggregation, above use spatial mean/sum."
        ),
    )
    proc_group.add_argument(
        "--precip-col",
        type=str,
        default="precip",
        help='Precipitation column name for clipping (default: "precip").',
    )
    proc_group.add_argument(
        "--workers",
        type=int,
        default=None,
        help=(
            "Number of parallel workers (default: CPU count - 2). Set to 1 for sequential processing."
        ),
    )

    # Scaling coefficients
    coeff_group = parser.add_argument_group("scaling coefficients (advanced)")
    coeff_group.add_argument(
        "--precip-coeff",
        type=float,
        help=(
            "Precipitation scaling coefficient (overrides dataset default). "
            "Multiplies weighted sum for accumulation variables."
        ),
    )
    coeff_group.add_argument(
        "--area-coeff",
        type=float,
        help=(
            "Area scaling coefficient (overrides dataset default). "
            "Used with watershed area to convert spatial sum to depth."
        ),
    )

    # Logging
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs/meteo_aggregation.log"),
        help='Log file path (default: "logs/meteo_aggregation.log").',
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    return parser


def validate_args(args: argparse.Namespace) -> None:
    """Validate command-line arguments.

    Args:
        args: Parsed arguments.

    Raises:
        ValueError: If arguments are invalid.
    """
    if not args.input_dir.exists():
        raise ValueError(f"Input directory not found: {args.input_dir}")

    if not args.geometry_file.exists():
        raise ValueError(f"Geometry file not found: {args.geometry_file}")

    if args.dataset == "custom" and (args.precip_coeff is None or args.area_coeff is None):
        raise ValueError("Custom dataset requires --precip-coeff and --area-coeff")

    if args.start_month < 1 or args.start_month > 12:
        raise ValueError(f"Invalid start month: {args.start_month}")

    if args.end_month < 1 or args.end_month > 12:
        raise ValueError(f"Invalid end month: {args.end_month}")


def determine_file_groups(
    args: argparse.Namespace, logger: logging.Logger
) -> list[tuple[str, list[Path]]]:
    """Determine file groups to process based on pattern or date range.

    Args:
        args: Parsed command-line arguments.
        logger: Logger instance.

    Returns:
        List of (tag, file_list) tuples.
    """
    if args.pattern:
        nc_files = sorted(args.input_dir.glob(args.pattern))
        logger.info(f"Using custom pattern '{args.pattern}': {len(nc_files)} files")
        return [("custom", nc_files)]

    # Build monthly date tags
    date_tags = [
        datetime(year, month, 1).strftime("%Y_%m")
        for year in range(args.start_year, args.end_year + 1)
        for month in range(1, 13)
        if args.start_year <= year <= args.end_year
        and (year != args.start_year or month >= args.start_month)
        and (year != args.end_year or month <= args.end_month)
    ]
    logger.info(f"Processing {len(date_tags)} months ({date_tags[0]} to {date_tags[-1]})")
    return [(tag, list(args.input_dir.rglob(f"*{tag}*.nc"))) for tag in date_tags]


def process_time_period(
    tag: str,
    nc_files: list[Path],
    ws: gpd.GeoDataFrame,
    output_dir: Path,
    config: dict,
    n_workers: int,
    logger: logging.Logger,
) -> None:
    """Process a single time period (month or custom group).

    Args:
        tag: Time period identifier.
        nc_files: List of NetCDF files for this period.
        ws: GeoDataFrame with watershed geometries.
        output_dir: Output directory path.
        config: Processing configuration dictionary.
        n_workers: Number of parallel workers.
        logger: Logger instance.
    """
    if not nc_files:
        logger.warning(f"No NetCDF files found for {tag}")
        return

    logger.info(f"Processing {tag}: {len(nc_files)} files")

    try:
        with xr.open_mfdataset(nc_files, combine="by_coords") as ds:
            args_list = [
                (ds, ws_geom, gage_id, output_dir, config, logger)
                for gage_id, ws_geom in ws["geometry"].items()
            ]

            if n_workers == 1:
                # Sequential processing
                for task_args in tqdm(args_list, desc=f"Watersheds ({tag})", leave=False):
                    process_watershed(task_args)
            else:
                # Parallel processing
                with ProcessPoolExecutor(max_workers=n_workers) as executor:
                    list(
                        tqdm(
                            executor.map(process_watershed, args_list),
                            total=len(args_list),
                            desc=f"Watersheds ({tag})",
                            leave=False,
                        )
                    )
    except Exception as exc:
        logger.error(f"Failed to process {tag}: {exc!r}")


def main() -> None:
    """Main entry point for meteorological data aggregation."""
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))
        return

    # Setup logging
    logger = setup_logger("MeteoAggregation", log_file=str(args.log_file))

    # Load watershed geometries
    try:
        ws = gpd.read_file(args.geometry_file).set_index("gauge_id")
        logger.info(f"Loaded {len(ws)} watersheds from {args.geometry_file}")
    except Exception as exc:
        logger.error(f"Failed to load geometries: {exc!r}")
        return

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Build processing configuration
    config = {
        "dataset": args.dataset,
        "grid_res": args.grid_res,
        "small_ws_threshold": args.small_ws_threshold,
        "precip_col": args.precip_col,
    }
    if args.precip_coeff is not None:
        config["precip_coeff"] = args.precip_coeff
    if args.area_coeff is not None:
        config["area_coeff"] = args.area_coeff

    # Determine file groups
    file_groups = determine_file_groups(args, logger)

    # Determine worker count
    n_workers = max(1, mp.cpu_count() - 2) if args.workers is None else args.workers
    logger.info(f"Using {n_workers} parallel workers")

    # Process each time period
    for tag, nc_files in tqdm(file_groups, desc="Processing time periods"):
        process_time_period(tag, nc_files, ws, args.output_dir, config, n_workers, logger)

    logger.info("Processing completed successfully")


if __name__ == "__main__":
    main()
