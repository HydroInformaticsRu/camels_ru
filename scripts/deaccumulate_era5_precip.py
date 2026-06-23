r"""De-accumulate ERA5-Land hourly total_precipitation into correct daily totals.

Why
---
ERA5-Land ``total_precipitation`` (``tp``) is accumulated since 00 UTC and reset each day.
The CDS GRIB is organised as ``(time=day, step=1..24h)`` where ``tp`` rises monotonically
within a day and ``step=24`` (== the next-midnight value) is the **full-day total**. The
old ``ParsedMonthly`` files summed the 24 cumulative steps instead of taking the last one,
inflating totals by up to ``sum(1..24)/24 = 12.5x`` (timing-dependent, hence unrecoverable
from the daily files). Convention verified empirically on a 2010-07 probe: a cell raining
only in the last 3 h showed step 24 = 0.0101 mm (correct) vs sum = 0.014 mm.

What this does
--------------
For each monthly hourly GRIB, take ``tp`` at ``step=24h`` -> one daily total per day, in
**metres** (left unconverted so the existing ``aggregation.py`` applies its m->mm x1000).
Month boundaries heal automatically: the last day of month M has its ``step=24`` in month
M+1's file (as ``time = last-day-of-M``), so concatenating all files and taking the per-date
max (skipping NaN) recovers every day. Output mirrors ``ParsedMonthly``: monthly
``YYYY_MM.nc``, var ``prcp`` (units ``m``), dims ``(time, latitude, longitude)``, daily
00 UTC stamps -- a drop-in corrected replacement for the aggregation step.

Usage
-----
    # validate the logic on the probe (no full download needed)
    pixi run python scripts/deaccumulate_era5_precip.py \\
        --input-file .tmp/era5_test_extract/data.grib --validate

    # full run after the download finishes (defaults to ParsedMonthly/era5land_tp_new)
    pixi run python scripts/deaccumulate_era5_precip.py \\
        --input-dir data/Russia/MeteoData/DownloadedHourly/InitialEra5Land/total_precipitation \\
        --write
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

DAILY_STEP_HOURS = 24  # ERA5-Land accumulation step that holds the full-day total

# Corrected daily gridded output: a fresh, clearly-named sibling of the broken
# ParsedMonthly/era5_land, so a clean re-aggregation can read from it without touching old data.
DEFAULT_OUTPUT = (
    Path(__file__).parent.parent / "data" / "Russia" / "MeteoData" / "ParsedMonthly" / "era5land_tp_new"
)


def deaccumulate_grib(grib_path: Path) -> xr.DataArray:
    """Return correct daily precip totals (metres) from one hourly ERA5-Land GRIB.

    Args:
        grib_path: Path to a monthly hourly ``total_precipitation`` GRIB.

    Returns:
        DataArray ``prcp`` with dims ``(time, latitude, longitude)`` in metres, where each
        ``time`` is the calendar day the accumulation belongs to. Days whose ``step=24`` is
        absent in this file (the month's last day) come back as NaN and are healed at concat.
    """
    # indexpath='' stops cfgrib writing a sidecar .idx that pollutes later globs.
    ds = xr.open_dataset(grib_path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    tp = ds["tp"]
    step_hours = (ds["step"].values / np.timedelta64(1, "h")).astype(int)
    if DAILY_STEP_HOURS in step_hours:
        daily = tp.isel(step=int(np.where(step_hours == DAILY_STEP_HOURS)[0][0]))
    else:
        # Fallback: the largest available step (still the day's running max accumulation).
        daily = tp.isel(step=-1)
    daily = daily.drop_vars(["step", "valid_time", "number", "surface"], errors="ignore")
    return daily.rename("prcp")


def build_daily(paths: list[Path]) -> xr.DataArray:
    """De-accumulate every GRIB and stitch into one gap-free daily series (metres)."""
    slices = []
    for p in paths:
        try:
            slices.append(deaccumulate_grib(p))
        except Exception as exc:  # noqa: BLE001 - report and skip a bad file, don't abort
            print(f"  WARN: skipping {p.name}: {exc}")
    if not slices:
        raise RuntimeError("no GRIB files produced daily slices")
    combined = xr.concat(slices, dim="time")
    # A date can appear twice (NaN from its own month, value from the next month's file).
    # Per-date max with skipna keeps the real total.
    healed = combined.groupby("time").max(skipna=True)
    healed.attrs["units"] = "m"
    healed.attrs["long_name"] = "total_precipitation_daily_deaccumulated"
    return healed.sortby("time")


def validate(daily: xr.DataArray) -> None:
    """Print sanity diagnostics: a correct daily series is mm-scale, not 12x inflated."""
    mm = daily * 1000.0
    vals = mm.values
    finite = vals[np.isfinite(vals)]
    print("\n=== de-accumulation sanity ===")
    print(
        f"  days: {daily.sizes['time']}  grid: "
        f"{daily.sizes.get('latitude')}x{daily.sizes.get('longitude')}"
    )
    print(
        f"  daily total (mm): mean={np.nanmean(finite):.3f}  max={np.nanmax(finite):.3f}  "
        f"p99={np.nanpercentile(finite, 99):.3f}"
    )
    print("  (correct ERA5-Land daily max is ~50-100 mm; the buggy summed series ran to 332)")
    # Per-cell annualised estimate from this sample
    daily_mean_mm = float(np.nanmean(finite))
    print(
        f"  annualised ~= {daily_mean_mm * 365:.0f} mm/yr at this sample "
        "(European-Russia lowland truth ~500-700; old grid was ~5900)"
    )


def write_monthly(daily: xr.DataArray, out_dir: Path) -> int:
    """Write the daily series as ParsedMonthly-style ``YYYY_MM.nc`` files. Returns count."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ds = daily.to_dataset(name="prcp") if isinstance(daily, xr.DataArray) else daily
    years = ds["time"].dt.year.values
    months = ds["time"].dt.month.values
    written = 0
    for ym in sorted(set(zip(years.tolist(), months.tolist(), strict=True))):
        y, m = ym
        sel = ds.sel(time=(ds["time"].dt.year == y) & (ds["time"].dt.month == m))
        sel.to_netcdf(out_dir / f"{y}_{m:02d}.nc")
        written += 1
    return written


def main() -> None:
    """Parse args, de-accumulate, validate, and optionally write monthly NetCDF."""
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input-dir", type=Path, help="Dir of monthly hourly GRIBs")
    src.add_argument("--input-file", type=Path, help="Single GRIB (for probe validation)")
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write YYYY_MM.nc (default: ParsedMonthly/era5land_tp_new)",
    )
    ap.add_argument("--write", action="store_true", help="Actually write output NetCDF")
    ap.add_argument("--validate", action="store_true", help="Print sanity diagnostics")
    args = ap.parse_args()

    if args.input_file:
        paths = [args.input_file]
    else:
        paths = sorted(args.input_dir.glob("*.grib"))
    print(f"de-accumulating {len(paths)} GRIB file(s)...")

    daily = build_daily(paths)

    if args.validate:
        validate(daily)

    if args.write:
        if not args.output_dir:
            raise SystemExit("--write requires --output-dir")
        n = write_monthly(daily, args.output_dir)
        print(f"\nwrote {n} monthly NetCDF file(s) to {args.output_dir}")
    else:
        print("\n(dry run -- pass --write --output-dir to persist)")


if __name__ == "__main__":
    main()
