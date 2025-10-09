"""Downloads ERA5-Land meteorological data using asynchronous processing.

This script initiates the download of ERA5-Land data for a specified date range,
geographical extent, and set of meteorological variables. It leverages asynchronous
requests to efficiently download multiple data files concurrently, which is
particularly useful for large datasets.

The core functionality is handled by the `download_era` function from the
`src.meteo.era5_land_loader` module. This script serves as a simple entry point
to configure and run the download process.

Key Configuration Parameters:
- **Date Range**: `start_date` and `last_date` define the temporal extent of the data.
- **Geographical Extent**: `data_extent` specifies the bounding box for the data
  in the format [North, West, South, East].
- **Meteorological Variables**: A list of variables to be downloaded (e.g.,
  'total_precipitation', '2m_temperature').
- **Concurrency**: `max_concurrent_downloads` controls how many files are
  downloaded in parallel.

Functions:
    main: The main asynchronous function that configures and initiates the download.
"""

import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(".").resolve()))
from src.meteo.era5_land_loader import download_era

from src.utils.logger import setup_logger

# --- Logger Setup ---
logger = setup_logger("ERA5Loader", log_file="logs/era5_loader.log")


async def main() -> None:
    """Configures and initiates the download of ERA5-Land data."""
    try:
        await download_era(
            start_date="2006-01-01",
            last_date="2025-07-31",
            save_path="data/MeteoData",
            meteo_variables=[
                "total_precipitation",
                "2m_temperature",
            ],
            data_extent=[50, -125, 24, -66],  # [N, W, S, E]
            max_concurrent_downloads=6,
        )
        logger.info("ERA5-Land data download completed successfully.")
    except Exception as e:
        logger.error(f"Failed to download ERA5-Land data: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
