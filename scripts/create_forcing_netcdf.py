#!/usr/bin/env python3
"""Create CAMELS-RU meteorological forcing NetCDF file.

This script merges basin-averaged meteorological data (MSWEP precipitation
and ERA5-Land variables) into a single CF-1.8 compliant NetCDF file.

Input data structure:
    data/MeteoData/CamelsRU/
    ├── mswep/
    │   └── {gauge_id}.csv  # date, precipitation (mm/day)
    └── era5_land/
        └── {gauge_id}.csv  # date, prcp, t_mean, t_min, t_max (°C)

Output:
    data/zenodo/forcing/camels_ru_forcing.nc

Author: CAMELS-RU Team
Date: 2024-12-02
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Import project logger
import sys

import numpy as np
import pandas as pd
from tqdm import tqdm
import xarray as xr

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.logger import setup_logger

# Initialize logger
logger = setup_logger("ForcingNetCDF")


def load_gauge_data(
    gauge_id: str,
    mswep_dir: Path,
    era5_dir: Path,
    start_date: str = "2008-01-01",
    end_date: str = "2023-12-31",
) -> dict[str, np.ndarray] | None:
    """Load meteorological data for a single gauge.

    Args:
        gauge_id: Gauge identifier
        mswep_dir: Path to MSWEP CSV directory
        era5_dir: Path to ERA5-Land CSV directory
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dictionary with variable arrays or None if loading fails
    """
    try:
        mswep_file = mswep_dir / f"{gauge_id}.csv"
        era5_file = era5_dir / f"{gauge_id}.csv"

        if not mswep_file.exists() or not era5_file.exists():
            return None

        # Load MSWEP precipitation
        mswep_df = pd.read_csv(mswep_file, parse_dates=["date"], index_col="date")

        # Load ERA5-Land variables
        era5_df = pd.read_csv(era5_file, parse_dates=["date"], index_col="date")

        # Create date range for full period
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")

        # Reindex to full date range (fills missing with NaN)
        mswep_df = mswep_df.reindex(date_range)
        era5_df = era5_df.reindex(date_range)

        # Extract variables
        result = {
            "precip_mswep": mswep_df["precipitation"].values.astype(np.float32),
            "precip_era5": era5_df["prcp"].values.astype(np.float32),
            "tmean": era5_df["t_mean"].values.astype(np.float32),
            "tmin": era5_df["t_min"].values.astype(np.float32),
            "tmax": era5_df["t_max"].values.astype(np.float32),
        }

        # Calculate data availability
        n_total = len(date_range)
        n_valid = np.sum(~np.isnan(result["precip_mswep"]))
        availability = int(np.round(n_valid / n_total * 100))
        result["data_availability"] = availability

        return result

    except Exception as e:
        logger.error(f"Failed to load gauge {gauge_id}: {e}")
        return None


def process_single_gauge(args: tuple[str, Path, Path]) -> tuple[str, dict] | None:
    """Worker function for parallel processing.

    Args:
        args: Tuple of (gauge_id, mswep_dir, era5_dir)

    Returns:
        Tuple of (gauge_id, data_dict) or None
    """
    gauge_id, mswep_dir, era5_dir = args
    data = load_gauge_data(gauge_id, mswep_dir, era5_dir)
    if data is not None:
        return (gauge_id, data)
    return None


def get_gauge_list(mswep_dir: Path, era5_dir: Path) -> list[str]:
    """Get list of gauge IDs with both MSWEP and ERA5-Land data.

    Args:
        mswep_dir: Path to MSWEP directory
        era5_dir: Path to ERA5-Land directory

    Returns:
        Sorted list of gauge IDs
    """
    mswep_files = {f.stem for f in mswep_dir.glob("*.csv")}
    era5_files = {f.stem for f in era5_dir.glob("*.csv")}

    # Keep only gauges with both datasets
    common_gauges = mswep_files & era5_files

    # Remove 'weights' if present
    common_gauges.discard("weights")

    return sorted(common_gauges)


def create_forcing_netcdf(
    gauge_ids: list[str], gauge_data_dict: dict[str, dict], output_path: Path
) -> None:
    """Create NetCDF file from gauge data.

    Args:
        gauge_ids: List of gauge IDs
        gauge_data_dict: Dictionary mapping gauge_id to data arrays
        output_path: Path for output NetCDF file
    """
    logger.info("Assembling forcing arrays...")

    # Create date range
    date_range = pd.date_range(start="2008-01-01", end="2023-12-31", freq="D")
    n_times = len(date_range)
    n_gauges = len(gauge_ids)

    logger.info(f"Array dimensions: {n_gauges} gauges × {n_times} days")

    # Initialize arrays
    precip_mswep = np.full((n_gauges, n_times), np.nan, dtype=np.float32)
    precip_era5 = np.full((n_gauges, n_times), np.nan, dtype=np.float32)
    tmean = np.full((n_gauges, n_times), np.nan, dtype=np.float32)
    tmin = np.full((n_gauges, n_times), np.nan, dtype=np.float32)
    tmax = np.full((n_gauges, n_times), np.nan, dtype=np.float32)
    data_availability = np.zeros(n_gauges, dtype=np.uint8)

    # Fill arrays
    logger.info("Filling arrays...")
    for i, gauge_id in enumerate(tqdm(gauge_ids, desc="Filling arrays")):
        if gauge_id in gauge_data_dict:
            data = gauge_data_dict[gauge_id]
            precip_mswep[i, :] = data["precip_mswep"]
            precip_era5[i, :] = data["precip_era5"]
            tmean[i, :] = data["tmean"]
            tmin[i, :] = data["tmin"]
            tmax[i, :] = data["tmax"]
            data_availability[i] = data["data_availability"]

    # Create xarray Dataset
    logger.info("Creating xarray Dataset...")

    ds = xr.Dataset(
        data_vars={
            "precip_mswep": (
                ["gauge", "time"],
                precip_mswep,
                {
                    "units": "mm day-1",
                    "long_name": "Basin-averaged precipitation from MSWEP v2.8",
                    "standard_name": "precipitation_amount",
                    "source": "MSWEP v2.8 (Beck et al., 2019)",
                    "cell_methods": "area: mean time: mean",
                    "coverage_content_type": "physicalMeasurement",
                    "_FillValue": np.nan,
                    "grid_mapping": "crs",
                },
            ),
            "precip_era5": (
                ["gauge", "time"],
                precip_era5,
                {
                    "units": "mm day-1",
                    "long_name": "Basin-averaged precipitation from ERA5-Land",
                    "standard_name": "precipitation_amount",
                    "source": "ERA5-Land (Muñoz Sabater et al., 2021)",
                    "cell_methods": "area: mean time: mean",
                    "coverage_content_type": "physicalMeasurement",
                    "_FillValue": np.nan,
                    "grid_mapping": "crs",
                },
            ),
            "tmean": (
                ["gauge", "time"],
                tmean,
                {
                    "units": "degC",
                    "long_name": "Basin-averaged daily mean temperature",
                    "standard_name": "air_temperature",
                    "source": "ERA5-Land (Muñoz Sabater et al., 2021)",
                    "cell_methods": "area: mean time: mean",
                    "coverage_content_type": "physicalMeasurement",
                    "_FillValue": np.nan,
                    "grid_mapping": "crs",
                },
            ),
            "tmin": (
                ["gauge", "time"],
                tmin,
                {
                    "units": "degC",
                    "long_name": "Basin-averaged daily minimum temperature",
                    "standard_name": "air_temperature",
                    "source": "ERA5-Land (Muñoz Sabater et al., 2021)",
                    "cell_methods": "area: mean time: minimum",
                    "coverage_content_type": "physicalMeasurement",
                    "_FillValue": np.nan,
                    "grid_mapping": "crs",
                },
            ),
            "tmax": (
                ["gauge", "time"],
                tmax,
                {
                    "units": "degC",
                    "long_name": "Basin-averaged daily maximum temperature",
                    "standard_name": "air_temperature",
                    "source": "ERA5-Land (Muñoz Sabater et al., 2021)",
                    "cell_methods": "area: mean time: maximum",
                    "coverage_content_type": "physicalMeasurement",
                    "_FillValue": np.nan,
                    "grid_mapping": "crs",
                },
            ),
            "data_availability": (
                ["gauge"],
                data_availability,
                {
                    "units": "percent",
                    "long_name": "Percentage of non-missing data for each gauge",
                    "description": "Percentage of days with valid data in the time series",
                },
            ),
        },
        coords={
            "gauge": (
                ["gauge"],
                gauge_ids,
                {
                    "long_name": "Gauge station identifier",
                    "cf_role": "timeseries_id",
                },
            ),
            "time": (
                ["time"],
                date_range,
                {
                    "long_name": "Time",
                    "standard_name": "time",
                },
            ),
        },
        attrs={
            "title": "CAMELS-RU Meteorological Forcing",
            "institution": "Russian Federal Service for Hydrometeorology and Environmental Monitoring",
            "source": "MSWEP v2.8 (precipitation), ERA5-Land (temperature)",
            "history": f"Created on {datetime.now().isoformat()} by create_forcing_netcdf.py",
            "Conventions": "CF-1.8",
            "featureType": "timeSeries",
            "time_coverage_start": "2008-01-01",
            "time_coverage_end": "2023-12-31",
            "geospatial_bounds_crs": "EPSG:4326",
            "processing_level": "Level 3 (basin-averaged)",
            "aggregation_method": "Area-weighted average within catchment boundaries",
            "mswep_version": "v2.8",
            "mswep_reference": "Beck, H. E., et al. (2019). MSWEP V2 global 3-hourly 0.1° precipitation: methodology and quantitative assessment. Bull. Amer. Meteor. Soc., 100(3), 473-500. doi:10.1175/BAMS-D-17-0138.1",
            "era5_land_reference": "Muñoz-Sabater, J., et al. (2021). ERA5-Land: a state-of-the-art global reanalysis dataset for land applications. Earth System Science Data, 13(9), 4349-4383. doi:10.5194/essd-13-4349-2021",
            "contact": "dmbrmv@github.com",
            "project": "CAMELS-RU: Catchment Attributes and Meteorology for Large-sample Studies - Russia",
            "references": "https://github.com/dmbrmv/camels_ru",
        },
    )

    # Set encoding for compression
    encoding = {
        "precip_mswep": {"zlib": True, "complevel": 4, "chunksizes": (100, n_times)},
        "precip_era5": {"zlib": True, "complevel": 4, "chunksizes": (100, n_times)},
        "tmean": {"zlib": True, "complevel": 4, "chunksizes": (100, n_times)},
        "tmin": {"zlib": True, "complevel": 4, "chunksizes": (100, n_times)},
        "tmax": {"zlib": True, "complevel": 4, "chunksizes": (100, n_times)},
        "time": {"units": "days since 2008-01-01", "calendar": "gregorian"},
    }

    # Write to NetCDF
    logger.info(f"Writing forcing NetCDF to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(output_path, format="NETCDF4", encoding=encoding)

    # Get file size
    file_size_mb = output_path.stat().st_size / (1024 * 1024)

    logger.info(f"Forcing NetCDF file created successfully: {output_path}")
    logger.info("Forcing statistics:")
    logger.info(f"  Total gauges: {n_gauges}")
    logger.info(f"  Gauges with data: {np.sum(data_availability > 0)}")
    logger.info(f"  File size: {file_size_mb:.2f} MB")

    ds.close()


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Create CAMELS-RU meteorological forcing NetCDF file")
    parser.add_argument(
        "--mswep-dir",
        type=Path,
        default=Path("../data/MeteoData/CamelsRU/mswep"),
        help="Path to MSWEP CSV directory",
    )
    parser.add_argument(
        "--era5-dir",
        type=Path,
        default=Path("../data/MeteoData/CamelsRU/era5_land"),
        help="Path to ERA5-Land CSV directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("../data/zenodo/forcing"),
        help="Output directory for NetCDF file",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for progress reporting",
    )

    args = parser.parse_args()

    # Resolve paths
    mswep_dir = args.mswep_dir.resolve()
    era5_dir = args.era5_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_path = output_dir / "camels_ru_forcing.nc"

    logger.info("=" * 60)
    logger.info("CAMELS-RU Forcing NetCDF Generation")
    logger.info("=" * 60)
    logger.info(f"MSWEP directory: {mswep_dir}")
    logger.info(f"ERA5-Land directory: {era5_dir}")
    logger.info(f"Output file: {output_path}")
    logger.info(f"Workers: {args.workers}")
    logger.info("=" * 60)

    # Get gauge list
    logger.info("Scanning gauge files...")
    gauge_ids = get_gauge_list(mswep_dir, era5_dir)
    logger.info(f"Found {len(gauge_ids)} gauges with both MSWEP and ERA5-Land data")

    # Process gauges in parallel
    logger.info(f"Processing gauges with {args.workers} workers...")
    gauge_data_dict = {}
    failed_gauges = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Submit tasks
        futures = {
            executor.submit(process_single_gauge, (gauge_id, mswep_dir, era5_dir)): gauge_id
            for gauge_id in gauge_ids
        }

        # Process results with progress bar
        with tqdm(total=len(gauge_ids), desc="Processing gauges", unit="gauge") as pbar:
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    gauge_id, data = result
                    gauge_data_dict[gauge_id] = data
                else:
                    failed_gauges.append(futures[future])
                pbar.update(1)

    logger.info("=" * 60)
    logger.info("Processing complete:")
    logger.info(f"  Successfully processed: {len(gauge_data_dict)} / {len(gauge_ids)} gauges")
    logger.info(f"  Failed: {len(failed_gauges)} gauges")
    if failed_gauges:
        logger.warning(
            f"  Failed gauges: {', '.join(failed_gauges[:10])}{'...' if len(failed_gauges) > 10 else ''}"
        )
    logger.info("=" * 60)

    # Create NetCDF file
    create_forcing_netcdf(gauge_ids, gauge_data_dict, output_path)

    logger.info("=" * 60)
    logger.info("NetCDF generation complete!")
    logger.info(f"Output file: {output_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
