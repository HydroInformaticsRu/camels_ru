"""Reference implementation of the ERA5-Land hourly-to-daily temperature reduction.

The released pipeline starts from daily ERA5-Land fields; the hourly-to-daily
reduction was performed once at retrieval time (Sect. 4.3 of the manuscript).
This script documents that step so the full forcing chain is reproducible for
users who retrieve the hourly fields themselves: daily mean, minimum, and
maximum 2 m air temperature over UTC calendar days, in degrees Celsius.

Usage:
    pixi run python scripts/era5_hourly_to_daily.py hourly_t2m.nc daily_t2m.nc

The input must carry an hourly ``t2m`` variable (Kelvin, as distributed by the
Copernicus Climate Data Store) on a ``time`` coordinate; any spatial dimensions
are preserved unchanged.
"""

import argparse

import xarray as xr


def reduce_hourly(ds: xr.Dataset) -> xr.Dataset:
    """Reduce hourly t2m (K) to daily mean/min/max t2m (degC) over UTC days."""
    celsius = ds["t2m"] - 273.15
    daily = celsius.resample(time="1D")
    return xr.Dataset(
        {
            "t_mean": daily.mean(),
            "t_min": daily.min(),
            "t_max": daily.max(),
        }
    ).assign_attrs(note="Daily statistics over UTC calendar days, degC (Sect. 4.3)")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hourly", help="hourly ERA5-Land NetCDF with a t2m variable (K)")
    parser.add_argument("daily", help="output NetCDF with t_mean/t_min/t_max (degC)")
    args = parser.parse_args()

    with xr.open_dataset(args.hourly) as ds:
        reduce_hourly(ds).to_netcdf(args.daily)
    print(f"Wrote {args.daily}")


if __name__ == "__main__":
    main()
