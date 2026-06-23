r"""Drain loop for ERA5-Land hourly precip: de-accumulate -> aggregate -> delete GRIB.

Why
---
The hourly ``total_precipitation`` re-download (``download_era5_precip_hourly.py``) lands
~0.9 GB per month, ~175 GB for the full 2007-2024 archive -- too large to keep all at once.
This drains it incrementally: as each month finishes downloading, de-accumulate it to a
corrected daily ``ParsedMonthly`` NetCDF, aggregate that month to per-gauge CSVs, and (once
safe) delete the raw GRIB so disk stays bounded to a handful of months.

Boundary-healing (verified empirically)
---------------------------------------
A monthly GRIB carries ``step=24`` (the full-day total) for days 1..(N-1) of its month, but
the **last day is all-NaN** -- its ``step=24`` lives in the *next* month's file (as that
file's redundant leading ``time`` entry). So month M is only *finalizable* once month M+1 is
also on disk: we de-accumulate both, ``groupby('time').max()`` heals M's last day, then we
slice to month M and write one complete ``YYYY_MM.nc``. Each written NetCDF is self-contained.

Safe deletion
-------------
GRIB month X is needed only for (a) finalizing X (needs X and X+1) and (b) supplying X-1's
last day (X-1 finalization needs X-1 and X). So X's GRIB is disposable once **both X and X-1
are finalized**. The newest ``--keep-recent`` months are always retained as a safety margin.
Deletion is OFF unless ``--delete`` is passed.

Re-download safety
------------------
The downloader builds its work-list once at startup and never re-scans, so deleting a
finished GRIB will not trigger a re-download in the running process. A finalized month's
``YYYY_MM.nc`` is the durable manifest: if the downloader is ever restarted, only months
without an nc need re-fetching.

Usage
-----
    # one validation cycle, no deletion (default)
    pixi run python scripts/drain_era5_precip.py --once

    # continuous drain with deletion, every 10 min
    pixi run python scripts/drain_era5_precip.py --loop --interval 600 --delete
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import xarray as xr

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "scripts"))

from deaccumulate_era5_precip import deaccumulate_grib  # noqa: E402  reuse validated logic

GRIB_DIR_DEFAULT = (
    PROJECT_ROOT
    / "data"
    / "Russia"
    / "MeteoData"
    / "DownloadedHourly"
    / "InitialEra5Land"
    / "total_precipitation"
)
NC_DIR_DEFAULT = PROJECT_ROOT / "data" / "Russia" / "MeteoData" / "ParsedMonthly" / "era5land_tp_new"
CSV_DIR_DEFAULT = PROJECT_ROOT / "data" / "Russia" / "MeteoData" / "CamelsRU" / "era5land_tp_new"
WATERSHEDS_DEFAULT = PROJECT_ROOT / "data" / "CAMELS_RU" / "geometry" / "camels_watersheds.gpkg"

# First month of the archive; its predecessor (2006-12) is outside the dataset, so a finalized
# 2007-01 GRIB is fully consumed even though 2006-12 never finalizes.
START_MONTH = (2007, 1)
GRIB_END_MARKER = b"7777"  # valid GRIB messages end with this
MIN_GRIB_BYTES = 1024
# A GRIB streams to its final path message-by-message and each message ends in 7777, so a file
# still downloading can transiently pass the marker check at a message boundary. Require the file
# to be quiescent (mtime older than this) before trusting it -- a finished file is never rewritten.
MIN_QUIESCENT_SECONDS = 120


def is_grib_complete(path: Path, min_age: float = MIN_QUIESCENT_SECONDS) -> bool:
    """Return True if a GRIB is fully written: size + trailing 7777 + quiescent for ``min_age`` s.

    The mtime guard prevents racing the downloader, which appends GRIB messages (each ending in
    7777) to the final path -- so an in-flight file can momentarily look complete at a boundary.
    """
    try:
        st = path.stat()
        if st.st_size < MIN_GRIB_BYTES:
            return False
        if min_age and (time.time() - st.st_mtime) < min_age:
            return False  # still being written
        with open(path, "rb") as f:
            f.seek(-8, 2)
            return GRIB_END_MARKER in f.read(8)
    except OSError:
        return False


def month_of(path: Path) -> tuple[int, int] | None:
    """Parse (year, month) from ``era5_land_totalprecipitation_2007_07_days_31.grib``."""
    parts = path.stem.split("_")
    for i in range(len(parts) - 1):
        if len(parts[i]) == 4 and parts[i].isdigit() and parts[i + 1].isdigit():
            year = int(parts[i])
            if 2000 <= year <= 2100:
                return (year, int(parts[i + 1]))
    return None


def succ(ym: tuple[int, int]) -> tuple[int, int]:
    """Month after ``ym``."""
    y, m = ym
    return (y + 1, 1) if m == 12 else (y, m + 1)


def pred(ym: tuple[int, int]) -> tuple[int, int]:
    """Month before ``ym``."""
    y, m = ym
    return (y - 1, 12) if m == 1 else (y, m - 1)


def list_complete_gribs(grib_dir: Path) -> dict[tuple[int, int], Path]:
    """Map (year, month) -> GRIB path for every complete file in ``grib_dir``."""
    out: dict[tuple[int, int], Path] = {}
    for p in sorted(grib_dir.glob("*.grib")):
        ym = month_of(p)
        if ym is not None and is_grib_complete(p):
            out[ym] = p
    return out


def finalized_months(nc_dir: Path) -> set[tuple[int, int]]:
    """Set of (year, month) already written as ``YYYY_MM.nc``."""
    done: set[tuple[int, int]] = set()
    for p in nc_dir.glob("*.nc"):
        try:
            y, m = p.stem.split("_")
            done.add((int(y), int(m)))
        except ValueError:
            continue
    return done


def finalize_month(grib_m: Path, grib_s: Path, ym: tuple[int, int]) -> xr.DataArray:
    """De-accumulate month M (+ its successor for the last day) into one complete daily slice.

    Args:
        grib_m: GRIB for month M (days 1..N-1 finite, last day NaN).
        grib_s: GRIB for month M+1 (its leading ``time`` entry is M's last day, finite).
        ym: (year, month) of M.

    Returns:
        DataArray ``prcp`` (metres) for every day of month M, NaN-healed.
    """
    y, m = ym
    da_m = deaccumulate_grib(grib_m)
    da_s = deaccumulate_grib(grib_s)
    healed = xr.concat([da_m, da_s], dim="time").groupby("time").max(skipna=True).sortby("time")
    month = healed.sel(time=(healed["time"].dt.year == y) & (healed["time"].dt.month == m))
    month.attrs["units"] = "m"
    month.attrs["long_name"] = "total_precipitation_daily_deaccumulated"
    return month


def write_month_nc(month: xr.DataArray, ym: tuple[int, int], nc_dir: Path) -> Path:
    """Write one month's daily series as a ParsedMonthly-style ``YYYY_MM.nc``."""
    y, m = ym
    nc_dir.mkdir(parents=True, exist_ok=True)
    out = nc_dir / f"{y}_{m:02d}.nc"
    ds = month.to_dataset(name="prcp")
    ds["prcp"].attrs["units"] = "m"
    ds.to_netcdf(out)
    return out


def healthy_month(month: xr.DataArray, ym: tuple[int, int]) -> bool:
    """Warn and return False if any day in the month is entirely NaN (heal failure)."""
    land_frac = np.isfinite(month.values).reshape(month.sizes["time"], -1).mean(axis=1)
    dead = int((land_frac == 0).sum())
    if dead:
        print(f"  WARN {ym[0]}_{ym[1]:02d}: {dead} all-NaN day(s) -- heal incomplete, skipping write")
        return False
    return True


def run_aggregation(nc_dir: Path, csv_dir: Path, watersheds: Path, workers: int) -> None:
    """Aggregate every not-yet-covered month in ``nc_dir`` to per-gauge CSVs (combine_first)."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "aggregate_watersheds.py"),
        "--dataset",
        "era5_land",
        "--watersheds",
        str(watersheds),
        "--input-dir",
        str(nc_dir),
        "--output-dir",
        str(csv_dir),
        "--variables",
        "prcp",
        "--resume",
        "--workers",
        str(workers),
    ]
    n_nc = len(list(nc_dir.glob("*.nc")))
    print(f"  aggregating {n_nc} nc -> {csv_dir.name} (see logs/aggregate_watersheds.log)")
    # Silence tqdm/stdout flood -- aggregate_watersheds.py keeps its own logs/aggregate_watersheds.log.
    subprocess.run(  # noqa: S603  args are our own constants, no untrusted input
        cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def delete_consumed(
    gribs: dict[tuple[int, int], Path], done: set[tuple[int, int]], keep_recent: int
) -> int:
    """Delete GRIBs fully consumed (X and X-1 finalized), keeping the newest ``keep_recent``."""
    keep = set(sorted(gribs)[-keep_recent:]) if keep_recent else set()
    removed = 0
    for ym in sorted(gribs):
        if ym in keep:
            continue
        pred_done = pred(ym) in done or pred(ym) < START_MONTH
        if ym in done and pred_done:
            gribs[ym].unlink()
            print(f"  deleted GRIB {ym[0]}_{ym[1]:02d} ({gribs[ym].name})")
            removed += 1
    return removed


def drain_cycle(args: argparse.Namespace) -> tuple[int, int]:
    """Run one drain cycle. Returns (months_finalized, gribs_deleted)."""
    gribs = list_complete_gribs(args.grib_dir)
    done = finalized_months(args.nc_dir)
    pending = sorted(ym for ym in gribs if ym not in done and succ(ym) in gribs)
    print(f"cycle: {len(gribs)} complete GRIBs, {len(done)} finalized, {len(pending)} newly finalizable")

    finalized = 0
    for ym in pending:
        month = finalize_month(gribs[ym], gribs[succ(ym)], ym)
        if not healthy_month(month, ym):
            continue
        out = write_month_nc(month, ym, args.nc_dir)
        print(f"  finalized {ym[0]}_{ym[1]:02d} -> {out.name}")
        done.add(ym)
        finalized += 1

    if done and not args.no_aggregate:
        run_aggregation(args.nc_dir, args.csv_dir, args.watersheds, args.workers)

    deleted = 0
    if args.delete:
        deleted = delete_consumed(gribs, done, args.keep_recent)
    return finalized, deleted


def main() -> None:
    """Parse args and run one or many drain cycles."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--grib-dir", type=Path, default=GRIB_DIR_DEFAULT)
    ap.add_argument("--nc-dir", type=Path, default=NC_DIR_DEFAULT)
    ap.add_argument("--csv-dir", type=Path, default=CSV_DIR_DEFAULT)
    ap.add_argument("--watersheds", type=Path, default=WATERSHEDS_DEFAULT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--keep-recent", type=int, default=2, help="Newest GRIB months never deleted")
    ap.add_argument("--delete", action="store_true", help="Delete fully-consumed GRIBs (default off)")
    ap.add_argument("--no-aggregate", action="store_true", help="De-accumulate only, skip aggregation")
    ap.add_argument("--loop", action="store_true", help="Run continuously")
    ap.add_argument("--once", action="store_true", help="Run a single cycle (default)")
    ap.add_argument("--interval", type=int, default=600, help="Seconds between loop cycles")
    ap.add_argument("--max-cycles", type=int, default=0, help="Stop after N loop cycles (0 = unlimited)")
    args = ap.parse_args()

    if not args.loop:
        fin, deleted = drain_cycle(args)
        print(f"done: {fin} finalized, {deleted} deleted")
        return

    cycle = 0
    while True:
        cycle += 1
        print(f"\n===== drain cycle {cycle} =====")
        try:
            drain_cycle(args)
        except Exception as exc:  # noqa: BLE001  keep the loop alive across transient errors
            print(f"  cycle error (continuing): {exc!r}")
        if args.max_cycles and cycle >= args.max_cycles:
            print(f"reached max-cycles={args.max_cycles}, stopping")
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
