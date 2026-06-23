"""Re-download ERA5-Land HOURLY total_precipitation for correct de-accumulation.

Context
-------
The existing per-gauge ERA5-Land precipitation (``Russia/MeteoData/CamelsRU/era5_land``)
is over-accumulated: the hourly CDS ``total_precipitation`` accumulates from 00 UTC, and
the daily ``ParsedMonthly`` files were built by *summing* the 24 cumulative hourly values
instead of de-accumulating, inflating totals by ``sum(1..24)/24 = 12.5x`` (source grid
~5900 mm/yr vs MSWEP ~480). The daily files are not recoverable per-day (the inflation
factor varies 1x-24x with rain timing), and the hourly raw is gone -- so we re-download.

The CDS ERA5-Land *daily-statistics* product omits accumulated variables (precip, runoff),
so we must take the HOURLY product and de-accumulate ourselves (see
``deaccumulate_era5_precip.py``, run after this completes).

Scope: precipitation ONLY. ERA5-Land temperature is instantaneous (not accumulated) and is
unaffected; do not re-download it.

Usage
-----
    pixi run python scripts/download_era5_precip_hourly.py            # 2007-2024, default extent
    pixi run python scripts/download_era5_precip_hourly.py --start 2008-01-01 --end 2023-12-31

Requires a configured CDS API key (``~/.cdsapirc``). The download queues on CDS and can take
hours-to-days; run it in a persistent session (tmux/nohup). Output GRIB lands under
``<save-path>/InitialEra5Land/total_precipitation/``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# ERA5-Land lives on the Climate Data Store. The user's ~/.cdsapirc points at the Early
# Warning Data Store (ewds) for other work, so force the CDS endpoint via the env override
# that cdsapi honours -- this keeps the rc key but routes requests to the right store.
# MUST be set before the loader constructs its cdsapi.Client(). Override with --cds-url.
CDS_URL = "https://cds.climate.copernicus.eu/api"

from src.meteo.era5_land_loader import download_era  # noqa: E402

# Catchment bounding box (camels_watersheds.gpkg total_bounds) padded 0.5 deg, as CDS
# area [North, West, South, East].
DEFAULT_EXTENT = [74, 19, 41, 179]
# Default period covers the released 2008-2023 window plus a one-day pad on each side: the
# de-accumulation assigns tp@00:00(D+1) to day D, so closing 2023-12-31 needs 2024-01-01.
DEFAULT_START = "2007-01-01"
DEFAULT_END = "2024-01-01"
DEFAULT_SAVE = PROJECT_ROOT / "data" / "Russia" / "MeteoData" / "DownloadedHourly"


def main() -> None:
    """Parse arguments and launch the hourly precipitation download."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START, help="First date (YYYY-MM-DD)")
    parser.add_argument("--end", default=DEFAULT_END, help="Last date (YYYY-MM-DD)")
    parser.add_argument(
        "--save-path",
        type=Path,
        default=DEFAULT_SAVE,
        help="Base dir for downloads (writes to <save-path>/InitialEra5Land/total_precipitation/)",
    )
    parser.add_argument(
        "--extent",
        type=float,
        nargs=4,
        metavar=("N", "W", "S", "E"),
        default=DEFAULT_EXTENT,
        help="CDS area as North West South East (default: catchment bbox)",
    )
    parser.add_argument("--max-concurrent", type=int, default=6)
    parser.add_argument(
        "--cds-url",
        default=CDS_URL,
        help="CDS API endpoint (set via CDSAPI_URL env so the rc key is reused)",
    )
    args = parser.parse_args()

    # Route cdsapi at the Climate Data Store regardless of the rc's active url (which points
    # at ewds). The key is still read from ~/.cdsapirc.
    os.environ["CDSAPI_URL"] = args.cds_url

    print(f"ERA5-Land HOURLY total_precipitation download: {args.start} -> {args.end}")
    print(f"  extent [N,W,S,E]: {args.extent}")
    print(f"  save path: {args.save_path}")
    print(f"  CDS endpoint: {args.cds_url}")
    print("  variable: total_precipitation ONLY (temperature is unaffected; do not re-download)")
    print("  NOTE: de-accumulate with scripts/deaccumulate_era5_precip.py after this finishes.\n")

    asyncio.run(
        download_era(
            start_date=args.start,
            last_date=args.end,
            save_path=args.save_path,
            meteo_variables=["total_precipitation"],
            data_extent=list(args.extent),
            max_concurrent_downloads=args.max_concurrent,
        )
    )


if __name__ == "__main__":
    main()
