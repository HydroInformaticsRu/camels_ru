"""Split a single GLEAM NetCDF into monthly files for aggregate_watersheds.py.

Reads the large GLEAM file lazily (one month at a time) and writes
individual YYYY_MM.nc files to the output directory.

Usage:
    pixi run python scripts/split_gleam_monthly.py
"""

from pathlib import Path

from tqdm.auto import tqdm
import xarray as xr

_PROJECT_ROOT = Path(__file__).parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"

GLEAM_PATH = _DATA_DIR / "Russia" / "MeteoData" / "gleam_v4.2a_eurasia_2007_2024.nc"
OUTPUT_DIR = _DATA_DIR / "Russia" / "MeteoData" / "ParsedMonthly" / "gleam"
START_YEAR = 2007
END_YEAR = 2023


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ds = xr.open_dataset(GLEAM_PATH, chunks={"time": 31})

    months = []
    for year in range(START_YEAR, END_YEAR + 1):
        for month in range(1, 13):
            months.append((year, month))

    for year, month in tqdm(months, desc="Splitting GLEAM"):
        out_path = OUTPUT_DIR / f"{year}_{month:02d}.nc"
        if out_path.exists():
            continue

        monthly = ds.sel(time=f"{year}-{month:02d}")
        if monthly.time.size == 0:
            continue

        monthly.load()
        monthly.to_netcdf(out_path)

    ds.close()
    print(f"Done. Files written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
