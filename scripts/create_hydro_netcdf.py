#!/usr/bin/env python3
"""Generate CAMELS-RU discharge and level NetCDF files from CSV time series.

This script consolidates hydrological time series data for all 2,638 CAMELS-RU
gauges into two NetCDF-4 files with comprehensive quality flags derived from:
1. Directory structure (full/partial, decent/poor, flagged categories)
2. Interpolation detection (polynomial order=2, limit=6)
3. Missing data patterns (NaN values)

Quality flags use worst-case precedence: 3 > 2 > 1 > 0
- 0: Good data (full/decent directories, no interpolation)
- 1: Interpolated data (gaps ≤6 days filled)
- 2: Poor quality or flagged directories (poor/negatives/freezing/shifted)
- 3: Missing data (NaN values)

The script uses parallel processing with ProcessPoolExecutor to efficiently
handle 2,638 gauges × 5,844 days of data.

Usage:
    python create_hydro_netcdf.py [--workers N] [--output-dir PATH] [--resume]
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import gc
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from tqdm.auto import tqdm
import xarray as xr

sys.path.append(str(Path(__file__).parent.parent))
from src.utils.logger import setup_logger

log = setup_logger("HydroNetCDF", log_file="../logs/hydro_netcdf_creation.log")

# Constants
START_DATE = "2008-01-01"
END_DATE = "2023-12-31"
N_DAYS = 5844  # 2008-01-01 to 2023-12-31 inclusive
TIME_INDEX = pd.date_range(START_DATE, END_DATE, freq="D")

# Quality flag definitions (worst-case precedence)
FLAG_GOOD = 0
FLAG_INTERPOLATED = 1
FLAG_POOR_FLAGGED = 2
FLAG_MISSING = 3

# Directory quality tiers
TIER_GOOD = ["full/decent", "partial/decent"]
TIER_POOR = ["full/poor", "partial/poor"]
TIER_FLAGGED = [
    "negatives/decent",
    "negatives/poor",
    "freezing/decent",
    "freezing/poor",
    "shifted/decent",
    "shifted/poor",
]


@dataclass
class GaugeData:
    """Container for processed gauge time series and quality flags."""

    gauge_id: str
    discharge_mm: np.ndarray | None  # Shape: (5844,)
    discharge_m3s: np.ndarray | None  # Shape: (5844,)
    level_cm: np.ndarray | None  # Shape: (5844,)
    quality_flag_discharge: np.ndarray | None  # Shape: (5844,)
    quality_flag_level: np.ndarray | None  # Shape: (5844,)
    has_discharge: bool
    has_level: bool
    error: str | None = None


def detect_interpolation(original: pd.Series, interpolation_limit: int = 6) -> np.ndarray:
    """Detect which values would be interpolated with polynomial method.

    Args:
        original: Original time series with NaN gaps
        interpolation_limit: Maximum consecutive NaNs to interpolate

    Returns:
        Boolean array indicating interpolated positions
    """
    # Create interpolated version
    interpolated = original.interpolate(method="polynomial", order=2, limit=interpolation_limit)

    # Values that were NaN in original but filled in interpolated
    was_interpolated = original.isna() & interpolated.notna()

    return was_interpolated.values


def determine_directory_tier(file_path: Path) -> int:
    """Determine base quality tier from directory structure.

    Args:
        file_path: Path to CSV file

    Returns:
        Base quality flag (0=good, 2=poor/flagged)
    """
    path_str = str(file_path)

    # Check flagged directories first (highest priority)
    for tier in TIER_FLAGGED:
        if tier in path_str:
            return FLAG_POOR_FLAGGED

    # Check poor quality
    for tier in TIER_POOR:
        if tier in path_str:
            return FLAG_POOR_FLAGGED

    # Default to good if in decent directories
    for tier in TIER_GOOD:
        if tier in path_str:
            return FLAG_GOOD

    # Fallback: assume poor if unrecognized
    log.warning("Unrecognized directory structure for %s, defaulting to FLAG_POOR", file_path)
    return FLAG_POOR_FLAGGED


def compute_quality_flags(data: pd.Series, file_path: Path, interpolation_limit: int = 6) -> np.ndarray:
    """Compute quality flags with worst-case precedence.

    Args:
        data: Time series data
        file_path: Path to source CSV (for directory tier)
        interpolation_limit: Maximum consecutive NaNs to interpolate

    Returns:
        Quality flag array (int8)
    """
    # Start with directory-based tier
    base_flag = determine_directory_tier(file_path)
    flags = np.full(len(data), base_flag, dtype=np.int8)

    # Override with interpolated flag where applicable
    if base_flag == FLAG_GOOD:
        interpolated_mask = detect_interpolation(data, interpolation_limit)
        flags[interpolated_mask] = FLAG_INTERPOLATED

    # Missing data overrides everything (worst case)
    missing_mask = data.isna().values
    flags[missing_mask] = FLAG_MISSING

    return flags


def find_gauge_file(gauge_id: str, data_type: str, base_dir: Path) -> Path | None:
    """Search for gauge CSV file across all quality tiers.

    Args:
        gauge_id: Gauge identifier
        data_type: "Discharge" or "Levels"
        base_dir: Base data directory

    Returns:
        Path to CSV file if found, None otherwise
    """
    search_dirs = [
        "full/decent",
        "full/poor",
        "partial/decent",
        "partial/poor",
    ]

    if data_type == "Levels":
        search_dirs.extend(
            [
                "negatives/decent",
                "negatives/poor",
                "freezing/decent",
                "freezing/poor",
                "shifted/decent",
                "shifted/poor",
            ]
        )

    for search_dir in search_dirs:
        file_path = base_dir / data_type / search_dir / f"{gauge_id}.csv"
        if file_path.exists():
            return file_path

    return None


def process_single_gauge(
    gauge_id: str, base_dir: Path, drainage_area_km2: float | None = None
) -> GaugeData:
    """Process time series data for a single gauge.

    Args:
        gauge_id: Gauge identifier
        base_dir: Base data directory (contains Discharge/ and Levels/)
        drainage_area_km2: Drainage area for unit conversion (optional)

    Returns:
        GaugeData object with processed arrays
    """
    try:
        # Initialize arrays with NaN
        discharge_mm = np.full(N_DAYS, np.nan, dtype=np.float32)
        discharge_m3s = np.full(N_DAYS, np.nan, dtype=np.float32)
        level_cm = np.full(N_DAYS, np.nan, dtype=np.float32)
        quality_flag_discharge = np.full(N_DAYS, FLAG_MISSING, dtype=np.int8)
        quality_flag_level = np.full(N_DAYS, FLAG_MISSING, dtype=np.int8)

        has_discharge = False
        has_level = False

        # Process discharge data
        discharge_file = find_gauge_file(gauge_id, "Discharge", base_dir)
        if discharge_file:
            try:
                df = pd.read_csv(discharge_file, index_col="date", parse_dates=True)

                # Align to standard time index
                df = df.reindex(TIME_INDEX)

                if "q_mm_day" in df.columns:
                    discharge_mm_series = df["q_mm_day"]
                    # Fill array at matching indices
                    discharge_mm[:] = discharge_mm_series.values
                    quality_flag_discharge = compute_quality_flags(discharge_mm_series, discharge_file)
                    has_discharge = True

                if "q_cms" in df.columns:
                    discharge_m3s_series = df["q_cms"]
                    discharge_m3s[:] = discharge_m3s_series.values
                elif has_discharge and drainage_area_km2:
                    # Convert from mm/day to m³/s if needed
                    discharge_m3s = discharge_mm * drainage_area_km2 * 1e6 / 86400 / 1000

            except Exception as e:
                log.warning("Failed to process discharge for gauge %s: %s", gauge_id, str(e))

        # Process level data
        level_file = find_gauge_file(gauge_id, "Levels", base_dir)
        if level_file:
            try:
                df = pd.read_csv(level_file, index_col="date", parse_dates=True)

                # Align to standard time index
                df = df.reindex(TIME_INDEX)

                if "lvl_sm" in df.columns:
                    level_cm_series = df["lvl_sm"]
                    level_cm[:] = level_cm_series.values
                    quality_flag_level = compute_quality_flags(level_cm_series, level_file)
                    has_level = True

            except Exception as e:
                log.warning("Failed to process level for gauge %s: %s", gauge_id, str(e))

        return GaugeData(
            gauge_id=gauge_id,
            discharge_mm=discharge_mm if has_discharge else None,
            discharge_m3s=discharge_m3s if has_discharge else None,
            level_cm=level_cm if has_level else None,
            quality_flag_discharge=quality_flag_discharge if has_discharge else None,
            quality_flag_level=quality_flag_level if has_level else None,
            has_discharge=has_discharge,
            has_level=has_level,
        )

    except Exception as e:
        log.error("Exception processing gauge %s: %s", gauge_id, str(e))
        return GaugeData(
            gauge_id=gauge_id,
            discharge_mm=None,
            discharge_m3s=None,
            level_cm=None,
            quality_flag_discharge=None,
            quality_flag_level=None,
            has_discharge=False,
            has_level=False,
            error=str(e),
        )


def create_discharge_netcdf(
    gauge_ids: list[str], gauge_data_list: list[GaugeData], output_path: Path
) -> None:
    """Create NetCDF file for discharge data.

    Args:
        gauge_ids: List of all gauge identifiers
        gauge_data_list: List of processed GaugeData objects
        output_path: Output NetCDF file path
    """
    n_gauges = len(gauge_ids)

    # Pre-allocate arrays
    discharge_mm = np.full((n_gauges, N_DAYS), np.nan, dtype=np.float32)
    discharge_m3s = np.full((n_gauges, N_DAYS), np.nan, dtype=np.float32)
    quality_flags = np.full((n_gauges, N_DAYS), FLAG_MISSING, dtype=np.int8)
    data_availability = np.zeros(n_gauges, dtype=np.uint8)

    # Map gauge_id to index
    gauge_id_to_idx = {gid: idx for idx, gid in enumerate(gauge_ids)}

    # Fill arrays
    log.info("Assembling discharge arrays...")
    for gdata in tqdm(gauge_data_list, desc="Filling discharge arrays"):
        idx = gauge_id_to_idx[gdata.gauge_id]

        if gdata.has_discharge and gdata.discharge_mm is not None:
            discharge_mm[idx, :] = gdata.discharge_mm
            discharge_m3s[idx, :] = gdata.discharge_m3s
            quality_flags[idx, :] = gdata.quality_flag_discharge
            data_availability[idx] |= 0b01  # Set bit 0 for discharge

    # Create xarray Dataset
    log.info("Creating xarray Dataset for discharge...")
    ds = xr.Dataset(
        data_vars={
            "discharge": (
                ["gauge", "time"],
                discharge_mm,
                {
                    "units": "mm/day",
                    "long_name": "Daily mean discharge as runoff depth",
                    "standard_name": "runoff_flux",
                    "valid_min": 0.0,
                    "valid_max": 1000.0,
                    "_FillValue": np.nan,
                },
            ),
            "discharge_m3s": (
                ["gauge", "time"],
                discharge_m3s,
                {
                    "units": "m3/s",
                    "long_name": "Daily mean discharge volume",
                    "standard_name": "water_volume_transport_in_river_channel",
                    "valid_min": 0.0,
                    "_FillValue": np.nan,
                },
            ),
            "quality_flag": (
                ["gauge", "time"],
                quality_flags,
                {
                    "long_name": "Data quality flag",
                    "flag_meanings": "good interpolated poor_or_flagged missing",
                    "flag_values": np.array([0, 1, 2, 3], dtype=np.int8),
                    "description": "Quality flag with worst-case precedence: 0=good (full/decent, no interpolation), 1=interpolated (gaps ≤6 days), 2=poor/flagged (poor tier or negatives/freezing/shifted), 3=missing (NaN)",
                },
            ),
            "data_availability": (
                ["gauge"],
                data_availability,
                {
                    "long_name": "Data availability bitmask",
                    "description": "Bit 0: discharge exists, Bit 1: level exists",
                    "flag_masks": np.array([1, 2], dtype=np.uint8),
                },
            ),
        },
        coords={
            "gauge": (["gauge"], gauge_ids, {"long_name": "Gauge identifier"}),
            "time": (
                ["time"],
                TIME_INDEX,
                {"long_name": "Time", "standard_name": "time"},
            ),
        },
        attrs={
            "title": "CAMELS-RU Discharge Time Series",
            "institution": "Russian Federal Service for Hydrometeorology and Environmental Monitoring (Roshydromet)",
            "source": "Gauge observations from Russian hydrological network",
            "history": f"Created on {datetime.now().isoformat()} by create_hydro_netcdf.py",
            "Conventions": "CF-1.8",
            "time_coverage_start": START_DATE,
            "time_coverage_end": END_DATE,
            "geospatial_bounds_crs": "EPSG:4326",
            "processing_level": "Level 2 (quality controlled)",
            "quality_flag_methodology": "Hierarchical flags from directory structure and polynomial interpolation detection (order=2, limit=6)",
            "interpolation_method": "Polynomial order 2, maximum gap 6 days",
            "references": "https://github.com/dmbrmv/camels_ru",
        },
    )

    # Set encoding for compression
    encoding = {
        "discharge": {"zlib": True, "complevel": 4, "chunksizes": (100, N_DAYS)},
        "discharge_m3s": {"zlib": True, "complevel": 4, "chunksizes": (100, N_DAYS)},
        "quality_flag": {"zlib": True, "complevel": 4, "chunksizes": (100, N_DAYS)},
        "data_availability": {"zlib": True, "complevel": 4},
        "time": {"units": f"days since {START_DATE}", "dtype": "int32"},
    }

    # Write to NetCDF
    log.info("Writing discharge NetCDF to %s...", output_path)
    ds.to_netcdf(output_path, encoding=encoding, format="NETCDF4")
    log.info("Discharge NetCDF file created successfully: %s", output_path)

    # Log statistics
    n_with_discharge = (data_availability & 0b01 > 0).sum()
    log.info("Discharge statistics:")
    log.info("  Gauges with discharge data: %d / %d", n_with_discharge, n_gauges)
    log.info("  File size: %.2f MB", output_path.stat().st_size / 1024 / 1024)


def create_level_netcdf(
    gauge_ids: list[str], gauge_data_list: list[GaugeData], output_path: Path
) -> None:
    """Create NetCDF file for water level data.

    Args:
        gauge_ids: List of all gauge identifiers
        gauge_data_list: List of processed GaugeData objects
        output_path: Output NetCDF file path
    """
    n_gauges = len(gauge_ids)

    # Pre-allocate arrays
    level_cm = np.full((n_gauges, N_DAYS), np.nan, dtype=np.float32)
    quality_flags = np.full((n_gauges, N_DAYS), FLAG_MISSING, dtype=np.int8)
    data_availability = np.zeros(n_gauges, dtype=np.uint8)

    # Map gauge_id to index
    gauge_id_to_idx = {gid: idx for idx, gid in enumerate(gauge_ids)}

    # Fill arrays
    log.info("Assembling level arrays...")
    for gdata in tqdm(gauge_data_list, desc="Filling level arrays"):
        idx = gauge_id_to_idx[gdata.gauge_id]

        if gdata.has_level and gdata.level_cm is not None:
            level_cm[idx, :] = gdata.level_cm
            quality_flags[idx, :] = gdata.quality_flag_level
            data_availability[idx] |= 0b10  # Set bit 1 for level

    # Create xarray Dataset
    log.info("Creating xarray Dataset for level...")
    ds = xr.Dataset(
        data_vars={
            "level": (
                ["gauge", "time"],
                level_cm,
                {
                    "units": "cm",
                    "long_name": "Daily mean water level above gauge datum",
                    "standard_name": "water_surface_height_above_reference_datum",
                    "_FillValue": np.nan,
                },
            ),
            "quality_flag": (
                ["gauge", "time"],
                quality_flags,
                {
                    "long_name": "Data quality flag",
                    "flag_meanings": "good interpolated poor_or_flagged missing",
                    "flag_values": np.array([0, 1, 2, 3], dtype=np.int8),
                    "description": "Quality flag with worst-case precedence: 0=good (full/decent, no interpolation), 1=interpolated (gaps ≤6 days), 2=poor/flagged (poor tier or negatives/freezing/shifted), 3=missing (NaN)",
                },
            ),
            "data_availability": (
                ["gauge"],
                data_availability,
                {
                    "long_name": "Data availability bitmask",
                    "description": "Bit 0: discharge exists, Bit 1: level exists",
                    "flag_masks": np.array([1, 2], dtype=np.uint8),
                },
            ),
        },
        coords={
            "gauge": (["gauge"], gauge_ids, {"long_name": "Gauge identifier"}),
            "time": (
                ["time"],
                TIME_INDEX,
                {"long_name": "Time", "standard_name": "time"},
            ),
        },
        attrs={
            "title": "CAMELS-RU Water Level Time Series",
            "institution": "Russian Federal Service for Hydrometeorology and Environmental Monitoring (Roshydromet)",
            "source": "Gauge observations from Russian hydrological network",
            "history": f"Created on {datetime.now().isoformat()} by create_hydro_netcdf.py",
            "Conventions": "CF-1.8",
            "time_coverage_start": START_DATE,
            "time_coverage_end": END_DATE,
            "geospatial_bounds_crs": "EPSG:4326",
            "processing_level": "Level 2 (quality controlled)",
            "quality_flag_methodology": "Hierarchical flags from directory structure and polynomial interpolation detection (order=2, limit=6)",
            "interpolation_method": "Polynomial order 2, maximum gap 6 days",
            "references": "https://github.com/dmbrmv/camels_ru",
        },
    )

    # Set encoding for compression
    encoding = {
        "level": {"zlib": True, "complevel": 4, "chunksizes": (100, N_DAYS)},
        "quality_flag": {"zlib": True, "complevel": 4, "chunksizes": (100, N_DAYS)},
        "data_availability": {"zlib": True, "complevel": 4},
        "time": {"units": f"days since {START_DATE}", "dtype": "int32"},
    }

    # Write to NetCDF
    log.info("Writing level NetCDF to %s...", output_path)
    ds.to_netcdf(output_path, encoding=encoding, format="NETCDF4")
    log.info("Level NetCDF file created successfully: %s", output_path)

    # Log statistics
    n_with_level = (data_availability & 0b10 > 0).sum()
    log.info("Level statistics:")
    log.info("  Gauges with level data: %d / %d", n_with_level, n_gauges)
    log.info("  File size: %.2f MB", output_path.stat().st_size / 1024 / 1024)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Generate CAMELS-RU discharge and level NetCDF files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers (default: 8)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("../data/zenodo/hydrology"),
        help="Output directory for NetCDF files (default: ../data/zenodo/hydrology)",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("../data/HydroFiles"),
        help="Base directory containing Discharge/ and Levels/ folders (default: ../data/HydroFiles)",
    )
    parser.add_argument(
        "--attributes-file",
        type=Path,
        default=Path("../data/zenodo/attributes/camels_ru_attributes.csv"),
        help="Path to attributes CSV with gauge IDs (default: ../data/zenodo/attributes/camels_ru_attributes.csv)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip existing NetCDF files",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of gauges per batch (default: 100)",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load gauge list from attributes file
    log.info("Loading gauge list from %s...", args.attributes_file)
    if not args.attributes_file.exists():
        log.error("Attributes file not found: %s", args.attributes_file)
        sys.exit(1)

    attributes_df = pd.read_csv(args.attributes_file, dtype={"gauge_id": str})
    gauge_ids = attributes_df["gauge_id"].tolist()
    n_gauges = len(gauge_ids)

    log.info("Found %d gauges in attributes file", n_gauges)

    # Check for existing files if resume flag is set
    discharge_path = args.output_dir / "camels_ru_discharge.nc"
    level_path = args.output_dir / "camels_ru_levels.nc"

    if args.resume:
        if discharge_path.exists() and level_path.exists():
            log.info("Both NetCDF files already exist. Exiting.")
            return
        if discharge_path.exists():
            log.info("Discharge NetCDF exists, will skip discharge processing")
        if level_path.exists():
            log.info("Level NetCDF exists, will skip level processing")

    # Get drainage areas for unit conversion (if available)
    drainage_areas = {}
    if "ws_area" in attributes_df.columns:
        drainage_areas = dict(zip(attributes_df["gauge_id"], attributes_df["ws_area"]))
        log.info("Loaded drainage areas for %d gauges", len(drainage_areas))

    # Process gauges in parallel
    log.info("=" * 60)
    log.info("Processing %d gauges with %d workers...", n_gauges, args.workers)

    gauge_data_list = []
    failed_gauges = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Submit tasks in batches
        futures = {}
        for i in range(0, n_gauges, args.batch_size):
            batch_ids = gauge_ids[i : i + args.batch_size]
            for gauge_id in batch_ids:
                drainage_area = drainage_areas.get(gauge_id)
                future = executor.submit(
                    process_single_gauge,
                    gauge_id,
                    args.base_dir,
                    drainage_area,
                )
                futures[future] = gauge_id

        # Collect results with progress bar
        with tqdm(
            total=n_gauges,
            desc="Processing gauges",
            unit="gauge",
        ) as pbar:
            for future in as_completed(futures):
                gauge_id = futures[future]
                try:
                    result = future.result()
                    gauge_data_list.append(result)

                    if result.error:
                        failed_gauges.append(gauge_id)

                    # Update progress bar with statistics
                    n_with_discharge = sum(1 for gd in gauge_data_list if gd.has_discharge)
                    n_with_level = sum(1 for gd in gauge_data_list if gd.has_level)
                    pbar.set_postfix(
                        {
                            "discharge": n_with_discharge,
                            "level": n_with_level,
                            "failed": len(failed_gauges),
                        }
                    )
                    pbar.update(1)

                except Exception as exc:
                    log.error("Gauge %s generated exception: %s", gauge_id, str(exc))
                    failed_gauges.append(gauge_id)
                    pbar.update(1)

        # Periodic garbage collection
        if len(gauge_data_list) % 500 == 0:
            gc.collect()

    log.info("=" * 60)
    log.info("Processing complete:")
    log.info("  Successfully processed: %d / %d gauges", len(gauge_data_list), n_gauges)
    log.info("  Failed: %d gauges", len(failed_gauges))

    n_with_discharge = sum(1 for gd in gauge_data_list if gd.has_discharge)
    n_with_level = sum(1 for gd in gauge_data_list if gd.has_level)
    n_with_both = sum(1 for gd in gauge_data_list if gd.has_discharge and gd.has_level)

    log.info("  Gauges with discharge: %d", n_with_discharge)
    log.info("  Gauges with level: %d", n_with_level)
    log.info("  Gauges with both: %d", n_with_both)

    if failed_gauges:
        log.warning("Failed gauges: %s", ", ".join(failed_gauges[:20]))
        if len(failed_gauges) > 20:
            log.warning("... and %d more", len(failed_gauges) - 20)

    # Create NetCDF files
    log.info("=" * 60)

    if not (args.resume and discharge_path.exists()):
        create_discharge_netcdf(gauge_ids, gauge_data_list, discharge_path)
    else:
        log.info("Skipping discharge NetCDF (already exists)")

    if not (args.resume and level_path.exists()):
        create_level_netcdf(gauge_ids, gauge_data_list, level_path)
    else:
        log.info("Skipping level NetCDF (already exists)")

    log.info("=" * 60)
    log.info("NetCDF generation complete!")
    log.info("Output files:")
    log.info("  Discharge: %s", discharge_path)
    log.info("  Level: %s", level_path)


if __name__ == "__main__":
    main()
