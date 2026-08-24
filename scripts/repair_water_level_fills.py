"""Revert out-of-range water-level fills to missing (Sect. 4.1.3).

``ParseAisHData.interpolate_level`` replaces a reported stage of exactly 0 cm with
the gauge's day-of-year median of non-zero observations, then interpolates short
gaps. Sect. 4.1.3 documents exactly that. But the day-of-year median series is
itself gap-filled before the substitution, so for a day-of-year at which a gauge has
*no* observation the "median" is an extrapolation rather than a median. At gauge
6164 this produced a runaway ramp of -54 to -434 cm, repeating identically across
years, at a gauge whose lowest observation is +0.5 cm.

Network-wide this left 991 negative stages (979 of them flag 2) and 3420 altered
values outside their own gauge's observed range -- 2.05 % of all altered values --
which is physically impossible for a stage measured above a fixed zero-post.

This reverts those out-of-range values to missing (``quality_flag = 3``) and leaves
every in-range fill in place, so the documented rule and the shipped data agree.
Observed values (``quality_flag == 0``) are never touched.

Run: ``pixi run python scripts/repair_water_level_fills.py [--dry-run]``
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "release" / "CAMELS_RU_v1.0" / "camels_ru_water_level.nc"

OBSERVED, FILLED, ZERO_REPLACED, MISSING = 0, 1, 2, 3


def out_of_range_mask(stage: np.ndarray, flag: np.ndarray) -> np.ndarray:
    """True where an altered value falls outside its own gauge's observed range."""
    observed = np.where(flag == OBSERVED, stage, np.nan)
    altered = np.isin(flag, (FILLED, ZERO_REPLACED)) & np.isfinite(stage)

    with np.errstate(invalid="ignore"):
        # A gauge with no observations at all has an all-NaN slice; nanmin/nanmax warn
        # and return NaN, and every comparison against NaN is False, so such gauges are
        # left alone rather than wholesale reverted. That is the intended behaviour.
        all_nan = np.isnan(observed).all(axis=1)
        lo = np.full(observed.shape[0], np.nan)
        hi = np.full(observed.shape[0], np.nan)
        lo[~all_nan] = np.nanmin(observed[~all_nan], axis=1)
        hi[~all_nan] = np.nanmax(observed[~all_nan], axis=1)
        return altered & ((stage < lo[:, None]) | (stage > hi[:, None]))


def main() -> None:
    """Revert out-of-range altered water-level values to missing, in place."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    ds = xr.load_dataset(TARGET)
    stage = ds["water_level_cm"].values.astype(float)
    flag = ds["quality_flag"].values

    bad = out_of_range_mask(stage, flag)
    n_bad = int(bad.sum())
    n_gauges = int(bad.any(axis=1).sum())
    n_neg = int((np.isfinite(stage) & (stage < 0)).sum())
    print(f"altered values outside their gauge's observed range: {n_bad} at {n_gauges} gauges")
    print(f"  of which flag 1 (gap-filled)   : {int((bad & (flag == FILLED)).sum())}")
    print(f"  of which flag 2 (zero-replaced): {int((bad & (flag == ZERO_REPLACED)).sum())}")
    print(f"negative stages before: {n_neg}")

    if args.dry_run:
        print("dry run — nothing written")
        return

    stage[bad] = np.nan
    flag = np.where(bad, MISSING, flag).astype(np.int8)
    ds["water_level_cm"] = (
        ds["water_level_cm"].dims,
        stage.astype(np.float32),
        ds["water_level_cm"].attrs,
    )
    ds["quality_flag"] = (ds["quality_flag"].dims, flag, ds["quality_flag"].attrs)
    # water_level_mbs = gauge_zero_m + water_level_cm/100; keep that identity exact.
    zero_m = ds["gauge_zero_m"].values.astype(float)[:, None]
    ds["water_level_mbs"] = (
        ds["water_level_mbs"].dims,
        (zero_m + stage / 100.0).astype(np.float32),
        ds["water_level_mbs"].attrs,
    )

    encoding = {
        "water_level_cm": {"dtype": "float32", "zlib": True, "complevel": 4},
        "water_level_mbs": {"dtype": "float32", "zlib": True, "complevel": 4},
        "gauge_zero_m": {"dtype": "float32", "zlib": True, "complevel": 4},
        "quality_flag": {"dtype": "int8", "zlib": True, "complevel": 4},
        "gauge_type": {"dtype": "int8", "zlib": True, "complevel": 4},
        "stage_discharge_screen": {"dtype": "int8", "zlib": True, "complevel": 4},
    }
    tmp = TARGET.with_suffix(".nc.tmp")
    ds.to_netcdf(tmp, encoding=encoding)
    tmp.replace(TARGET)

    with xr.open_dataset(TARGET) as check:
        s = check["water_level_cm"].values
        f = check["quality_flag"].values
        print("\nafter:")
        print(f"  negative stages : {int((np.isfinite(s) & (s < 0)).sum())}")
        print(f"  stage range     : {np.nanmin(s):.2f} to {np.nanmax(s):.2f} cm")
        print(f"  still out of range: {int(out_of_range_mask(s.astype(float), f).sum())}")
        for code, label in [(0, "observed"), (1, "gap-filled"), (2, "zero-replaced"), (3, "missing")]:
            print(f"  flag {code} ({label:13s}): {int((f == code).sum())}")


if __name__ == "__main__":
    main()
