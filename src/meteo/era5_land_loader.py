"""Module to download ERA5-Land data from the Copernicus Data Store.

Contains functions to download ERA5-Land data with retry logic and a
function to instantiate the CDS API client.

"""

import asyncio
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys

import cdsapi

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from src.utils.logger import setup_logger


class Era5LandDownloader:
    """ERA5-Land data downloader with asynchronous capabilities."""

    DEFAULT_VARIABLES = ["2m_temperature", "total_precipitation"]
    DEFAULT_EXTENT = [50, -125, 24, -66]  # [N, W, S, E] for continental USA
    DATASET_NAME = "reanalysis-era5-land"
    MIN_FILE_SIZE_BYTES = 1024  # Minimum size for a valid GRIB file (1KB)

    def __init__(
        self,
        save_path: str | Path,
        max_concurrent_downloads: int = 4,
        max_retries: int = 3,
    ):
        """Initialize the ERA5-Land downloader.

        Args:
            save_path: Base directory for storing downloaded files
            max_concurrent_downloads: Maximum number of simultaneous downloads
            max_retries: Maximum number of retry attempts for failed downloads

        Raises:
            ValueError: If max_concurrent_downloads < 1 or max_retries < 1
            OSError: If save_path cannot be created

        """
        if max_concurrent_downloads < 1:
            raise ValueError(f"max_concurrent_downloads must be >= 1, got: {max_concurrent_downloads}")
        if max_retries < 1:
            raise ValueError(f"max_retries must be >= 1, got: {max_retries}")

        self.save_path = Path(save_path)
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_retries = max_retries
        self.logger = setup_logger(
            "ERA5Loader",  # function/task context
            log_file="logs/era5_loader.log",  # dedicated log file for this script
        )
        self._client = None

        # Create base directory
        try:
            self.save_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError(f"Cannot create save path {save_path}: {e}") from e

    def _get_cdsapi_client(self) -> cdsapi.Client:
        """Get or create CDS API client instance.

        Returns:
            Configured CDS API client

        """
        if self._client is None:
            self._client = cdsapi.Client()
        return self._client

    def _is_file_complete(self, file_path: Path) -> bool:
        """Check if a file is completely downloaded and valid.

        Args:
            file_path: Path to the file to check

        Returns:
            True if file exists, has valid size, and appears complete

        """
        if not file_path.exists():
            return False

        try:
            # Check file size
            file_size = file_path.stat().st_size
            if file_size < self.MIN_FILE_SIZE_BYTES:
                self.logger.warning(
                    f"File {file_path.name} is too small ({file_size} bytes), marking as incomplete"
                )
                return False

            # For GRIB files, check if file ends properly
            # GRIB files should end with specific byte patterns
            with open(file_path, "rb") as f:
                # Check if we can read the file without errors
                f.seek(-8, 2)  # Go to last 8 bytes
                last_bytes = f.read(8)

                # GRIB files typically end with '7777' pattern
                if b"7777" not in last_bytes:
                    self.logger.warning(f"File {file_path.name} doesn't end with expected GRIB pattern")
                    return False

            return True

        except OSError as e:
            self.logger.error(f"Error checking file {file_path.name}: {e}")
            return False

    def _remove_incomplete_file(self, file_path: Path) -> None:
        """Remove an incomplete or corrupted file.

        Args:
            file_path: Path to the file to remove

        """
        try:
            if file_path.exists():
                file_size = file_path.stat().st_size
                file_path.unlink()
                self.logger.info(f"🗑️  Removed incomplete file {file_path.name} ({file_size:,} bytes)")
        except OSError as e:
            self.logger.error(f"Failed to remove incomplete file {file_path.name}: {e}")

    def _validate_dates(
        self, start_date: str | datetime, last_date: str | datetime
    ) -> tuple[datetime, datetime]:
        """Validate and convert input dates to datetime objects.

        Args:
            start_date: Start date as string or datetime
            last_date: End date as string or datetime

        Returns:
            Tuple of validated datetime objects

        Raises:
            ValueError: If date formats are invalid or start_date > last_date

        """
        # Convert string dates to datetime objects
        if isinstance(start_date, str):
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError as e:
                raise ValueError(
                    f"Invalid start_date format. Expected 'YYYY-MM-DD', got: {start_date}"
                ) from e

        if isinstance(last_date, str):
            try:
                last_date = datetime.strptime(last_date, "%Y-%m-%d")
            except ValueError as e:
                raise ValueError(
                    f"Invalid last_date format. Expected 'YYYY-MM-DD', got: {last_date}"
                ) from e

        # Validate date range
        if start_date > last_date:
            raise ValueError(
                f"start_date ({start_date.date()}) cannot be after last_date ({last_date.date()})"
            )

        return start_date, last_date

    def _validate_variables(self, variables: list[str] | None) -> list[str]:
        """Validate and return meteorological variables list.

        Args:
            variables: List of meteorological variables or None

        Returns:
            Validated list of variables

        Raises:
            ValueError: If variables list is empty

        """
        if variables is None:
            return self.DEFAULT_VARIABLES.copy()

        if not variables:
            raise ValueError("meteo_variables cannot be an empty list")

        return variables

    def _validate_extent(self, extent: list[float] | list[int] | None) -> list[float] | list[int]:
        """Validate spatial extent parameters.

        Args:
            extent: Spatial extent [N, W, S, E] or None

        Returns:
            Validated extent list

        Raises:
            ValueError: If extent format is invalid

        """
        if extent is None:
            return self.DEFAULT_EXTENT.copy()

        if len(extent) != 4:
            raise ValueError(f"data_extent must have 4 values [N, W, S, E], got: {len(extent)}")

        north, west, south, east = extent
        if not (-90 <= south <= north <= 90):
            raise ValueError(f"Invalid latitude bounds: South={south}, North={north}")
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            raise ValueError(f"Invalid longitude bounds: West={west}, East={east}")

        return extent

    def _generate_date_range(self, start: datetime, end: datetime) -> list[tuple[str, str, str]]:
        """Generate list of dates between start and end dates.

        Args:
            start: Start date
            end: End date

        Returns:
            List of date tuples (year, month, day) as strings

        """
        dates = []
        current_date = start
        while current_date <= end:
            dates.append((str(current_date.year), f"{current_date.month:02d}", str(current_date.day)))
            current_date += timedelta(days=1)
        return dates

    def _build_request(
        self, variable: str, year: str, month: str, days: list[str], data_extent: list[float]
    ) -> dict:
        """Build request dictionary for ERA5-Land data.

        Args:
            variable: Meteorological variable to download
            year: Year for the request
            month: Month for the request
            days: List of days for the request
            data_extent: Spatial extent [N, W, S, E]

        Returns:
            Request dictionary for ERA5-Land data

        """
        return {
            "variable": [variable],
            "year": year,
            "month": month,
            "day": days,
            "time": [f"{i:02d}:00" for i in range(24)],
            "data_format": "grib",
            "download_format": "unarchived",
            "area": data_extent,
        }

    async def _download_file_with_retry(
        self,
        client: cdsapi.Client,
        request: dict,
        output_file: Path,
    ) -> bool:
        """Download a single file with retry logic and integrity checks.

        Args:
            client: CDS API client instance
            request: Request parameters for the download
            output_file: Path where the file will be saved

        Returns:
            True if download successful, False otherwise

        """
        for attempt in range(self.max_retries):
            try:
                # Remove incomplete file if it exists
                if output_file.exists() and not self._is_file_complete(output_file):
                    self._remove_incomplete_file(output_file)

                self.logger.info(f"📥 Downloading: {output_file.name} (Attempt {attempt + 1})")

                # Perform the download
                await asyncio.to_thread(client.retrieve, self.DATASET_NAME, request, str(output_file))

                # Verify download completion
                if self._is_file_complete(output_file):
                    self.logger.info(f"✅ Successfully downloaded and verified: {output_file.name}")
                    return True
                else:
                    self.logger.error(f"❌ Downloaded file {output_file.name} failed integrity check")
                    self._remove_incomplete_file(output_file)
                    raise Exception("File integrity check failed")

            except Exception as e:
                self.logger.error(f"❌ Error on attempt {attempt + 1} for {output_file.name}: {e}")

                # Clean up any partial download
                if output_file.exists():
                    self._remove_incomplete_file(output_file)

                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    self.logger.info(
                        f"🔄 Retrying {output_file.name} in {wait_time}s (Attempt {attempt + 2})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(
                        f"💥 Download failed for {output_file.name} after {self.max_retries} attempts"
                    )

        return False

    async def _download_variable_batch(
        self,
        variable: str,
        dates: list[tuple[str, str, str]],
        data_extent: list[float] | list[int] | None,
    ) -> list[asyncio.Task]:
        """Prepare download tasks for a single variable.

        Args:
            variable: Meteorological variable to download
            dates: List of date tuples (year, month, day)
            data_extent: Spatial extent for the downloads

        Returns:
            List of download tasks

        """
        # Create variable-specific storage path
        storage_path = self.save_path / "InitialEra5Land" / variable
        storage_path.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"📁 Files for '{variable}' will be saved to: {storage_path}")

        client = self._get_cdsapi_client()

        # Group dates by year and month
        date_groups = {}
        for year, month, day in dates:
            date_groups.setdefault((year, month), []).append(f"{int(day):02d}")

        download_tasks = []
        for (year, month), days in date_groups.items():
            request = self._build_request(variable, year, month, days, data_extent)

            # Create filename
            var_clean = variable.replace("_", "")
            output_file = storage_path / f"era5_land_{var_clean}_{year}_{month}_days_{len(days)}.grib"

            # Check if file exists and is complete
            if output_file.exists():
                if self._is_file_complete(output_file):
                    # self.logger.info(f"⏭️  Skipping {output_file.name}, already exists and is complete")
                    continue
                else:
                    self.logger.info(
                        f"🔄 File {output_file.name} exists but is incomplete, will re-download"
                    )
                    self._remove_incomplete_file(output_file)

            task = self._download_file_with_retry(client, request, output_file)
            download_tasks.append(task)

        if download_tasks:
            self.logger.info(f"🚀 Prepared {len(download_tasks)} download tasks for '{variable}'")
        else:
            self.logger.info(
                f"✨ No new files to download for '{variable}' - all files already exist and are complete"
            )

        return download_tasks

    async def download_era5_land_data(
        self,
        start_date: str | datetime,
        last_date: str | datetime,
        meteo_variables: list[str] | None = None,
        data_extent: list[float] | list[int] | None = None,
    ) -> None:
        """Download ERA5-Land data asynchronously for a specified date range.

        Args:
            start_date: First date to download (format: 'YYYY-MM-DD' or datetime object)
            last_date: Last date to download (format: 'YYYY-MM-DD' or datetime object)
            meteo_variables: List of meteorological variables to download
            data_extent: Spatial extent [N, W, S, E]

        Raises:
            ValueError: If parameters are invalid
            OSError: If file operations fail

        """
        # Validate inputs
        start_date, last_date = self._validate_dates(start_date, last_date)
        meteo_variables = self._validate_variables(meteo_variables)
        data_extent = self._validate_extent(data_extent)

        self.logger.info(f"\n{'=' * 60}")
        self.logger.info(f"Starting ERA5-Land download from {start_date.date()} to {last_date.date()}")
        self.logger.info(f"Variables to download: {meteo_variables}")
        self.logger.info(f"Max concurrent downloads: {self.max_concurrent_downloads}")
        self.logger.info(f"{'=' * 60}\n")

        # Generate date range
        dates_to_download = self._generate_date_range(start_date, last_date)

        if not dates_to_download:
            self.logger.info("ℹ️  No dates to download")
            return

        self.logger.info(f"📅 Generated {len(dates_to_download)} dates to download")

        # Collect all download tasks for all variables
        all_download_tasks = []
        for variable in meteo_variables:
            self.logger.info(f"🔧 Preparing downloads for variable: '{variable}'")
            variable_tasks = await self._download_variable_batch(
                variable, dates_to_download, data_extent
            )
            all_download_tasks.extend(variable_tasks)

        if not all_download_tasks:
            self.logger.info("✨ No new files to download - all files already exist and are complete")
            return

        self.logger.info(f"\n{'=' * 50}")
        self.logger.info(f"🎯 Executing {len(all_download_tasks)} total download tasks")
        self.logger.info(f"{'=' * 50}\n")

        # Execute downloads with concurrency limit
        semaphore = asyncio.Semaphore(self.max_concurrent_downloads)

        async def limited_download(task):
            """Limit concurrent downloads using semaphore."""
            async with semaphore:
                return await task

        # Execute all downloads
        results = await asyncio.gather(
            *[limited_download(task) for task in all_download_tasks], return_exceptions=True
        )

        # Count successful downloads
        successful_downloads = sum(1 for result in results if result is True)
        failed_downloads = len(results) - successful_downloads

        self.logger.info(f"\n{'=' * 50}")
        self.logger.info("🎉 Download process completed!")
        self.logger.info(f"✅ Successful downloads: {successful_downloads}")
        if failed_downloads > 0:
            self.logger.warning(f"❌ Failed downloads: {failed_downloads}")
        self.logger.info(f"{'=' * 50}\n")


# Convenience function to maintain backward compatibility
async def download_era(
    start_date: str | datetime,
    last_date: str | datetime,
    save_path: str | Path,
    meteo_variables: list[str] | None = None,
    data_extent: list[float] | None = None,
    max_concurrent_downloads: int = 4,
) -> None:
    """Download ERA5-Land data asynchronously for a specified date range.

    This is a convenience wrapper around the Era5LandDownloader class.

    Args:
        start_date: First date to download (format: 'YYYY-MM-DD' or datetime object)
        last_date: Last date to download (format: 'YYYY-MM-DD' or datetime object)
        save_path: Path where downloaded files will be stored
        meteo_variables: List of meteorological variables to download
        data_extent: Spatial extent [N, W, S, E]
        max_concurrent_downloads: Maximum number of simultaneous download requests

    Raises:
        ValueError: If date formats are invalid or parameters are out of range
        OSError: If save_path cannot be created

    """
    downloader = Era5LandDownloader(
        save_path=save_path,
        max_concurrent_downloads=max_concurrent_downloads,
    )

    await downloader.download_era5_land_data(
        start_date=start_date,
        last_date=last_date,
        meteo_variables=meteo_variables,
        data_extent=data_extent,
    )
