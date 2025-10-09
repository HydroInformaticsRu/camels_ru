"""Converts ERA5 meteorological data from NetCDF format to watershed-aggregated CSV files.

This script processes ERA5-Land NetCDF files, which contain gridded meteorological
data, and aggregates the data for specific watershed geometries. It iterates through
a defined date range, processing each month's data in parallel to enhance performance.

Key Features:
- **Parallel Processing**: Utilizes a `ProcessPoolExecutor` to process multiple
  streamgage watersheds concurrently, significantly reducing processing time.
- **Geospatial Aggregation**: Reads watershed geometries from a GeoPackage file
  and uses them to extract and aggregate the corresponding ERA5 data.
- **Time-Based Iteration**: Processes data month by month over a specified range
  of years, making the workflow manageable and easy to track.
- **Modular Design**: Leverages functions from the `src.meteo` module to perform
  the core data conversion, promoting code reuse and maintainability.

The main function orchestrates the process by loading watershed data, preparing
arguments for each processing task, and managing the parallel execution.

Functions:
    process_gage: A worker function that processes a single watershed for a given dataset.
    main: The main entry point for the script.
"""

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import multiprocessing as mp
from pathlib import Path
import sys

import geopandas as gpd
from tqdm.auto import tqdm
import xarray as xr

sys.path.append(str(Path(__file__).parent.parent))
from src.meteo.era5_land_daily import era5_ws
from src.utils.logger import setup_logger


def process_gage(args: tuple) -> None:
    """Processes a single gage for a given ERA5 dataset.

    This function is designed to be called by a parallel executor. It unpacks
    the arguments and calls the `era5_ws` function to perform the main
    geospatial aggregation and data conversion.

    Args:
        args: A tuple containing the dataset, watershed geometry, gage ID,
              output path, and logger instance.
    """
    ds, ws_geom, gage_id, path_to_results, logger = args
    try:
        era5_ws(
            initial_nc=ds,
            ws_geom=ws_geom,
            gauge_id=gage_id,
            path_to_results=path_to_results,
        )
    except Exception as exc:
        logger.error(f"Failed to process gage {gage_id}: {exc}")


def main() -> None:
    """Main entry point for converting ERA5 data to watershed-aggregated CSVs.

    This function sets up the processing environment, iterates through the
    specified date range, and manages the parallel execution of the `process_gage`
    function.
    """
    logger = setup_logger("MeteoConversion", log_file="logs/era5_to_gauge.log")

    try:
        ws = gpd.read_file("data/Geometry/WatershedGeomCAMELS.gpkg").set_index("gauge_id")
        ws["area"] /= 1e6
    except FileNotFoundError:
        logger.error("Watershed geometry file not found: data/Geometry/WatershedGeomCAMELS.gpkg")
        return

    path_to_era5land = Path("data/MeteoData/CamelsRU/era5_land")
    path_to_era5land.mkdir(parents=True, exist_ok=True)

    date_tags = [
        datetime(year, month, 1).strftime("%Y_%m")
        for year in range(2007, 2026)
        for month in range(1, 13)
    ]

    for date_tag in tqdm(date_tags, desc="Processing Monthly Data"):
        logger.info(f"Processing data for {date_tag}")

        nc_files = list(Path("data/MeteoData/ParsedMonthly").glob(f"*/*{date_tag}*.nc"))
        if not nc_files:
            logger.warning(f"No NetCDF files found for date tag {date_tag}.")
            continue

        with xr.open_mfdataset(nc_files) as ds:
            args_list = [
                (ds, ws_geom, gage_id, path_to_era5land, logger)
                for gage_id, ws_geom in ws["geometry"].items()
            ]

            with ProcessPoolExecutor(max_workers=mp.cpu_count() - 2) as executor:
                list(
                    tqdm(
                        executor.map(process_gage, args_list),
                        total=len(args_list),
                        desc=f"Processing Gages for {date_tag}",
                    )
                )


if __name__ == "__main__":
    main()
