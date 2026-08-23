"""Derive the water-level provenance mask for the release flag.

``scripts/ParseAisHData.interpolate_level`` alters the merged stage series in place:
zero readings are replaced by the day-of-year median, and gaps are then interpolated
with ``interpolate(limit=6)`` (15 for reservoir gauges). The shipped per-gauge CSVs in
``HydroData/Level`` and ``HydroData/LevelGTS`` therefore cannot tell an observation
from an altered value. This script recovers that provenance the same way as
``derive_discharge_fill_mask.py``:

  1. Re-merge the raw per-year fragments (``AisLevelCsv/``, ``AisLevelGTSCsv/``) onto the
     2008-2023 daily grid (combine_first, dedup keep-first -- mirrors ``ais_merger``).
  2. A day is interpolated iff it is MISSING in the re-merge but PRESENT in the shipped
     series; it is zero-replaced iff the re-merge holds exactly 0 and the shipped series
     holds a value.

Writes ``data/CAMELS_RU/HydroData/water_level_fill_mask.nc`` (gauge_id x time int8,
0 = untouched, 1 = interpolated, 2 = zero-replaced), consumed by
``scripts/package_dataset.py::package_water_level``.

Run: pixi run python scripts/derive_water_level_fill_mask.py
"""

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).parent.parent
DATA = PROJECT_ROOT / "data" / "CAMELS_RU"
SOURCES = {  # shipped (post-fill) directory -> raw fragment directory
    DATA / "HydroData" / "Level": DATA / "AisLevelCsv",
    DATA / "HydroData" / "LevelGTS": DATA / "AisLevelGTSCsv",
}
OUT = DATA / "HydroData" / "water_level_fill_mask.nc"
COLUMN = "lvl_sm"
PERIOD_START, PERIOD_END = "2008-01-01", "2023-12-31"


def _reconstruct_prefill(frag_files: list[Path], dates: pd.DatetimeIndex) -> pd.Series:
    """Re-merge raw fragments into the pre-fill stage series (mirrors ais_merger)."""
    base = pd.DataFrame(index=dates, columns=[COLUMN], dtype=float)
    base.index.name = "date"
    for f in frag_files:
        nd = pd.read_csv(f, index_col="date", parse_dates=True).rename(columns={"level": COLUMN})
        base = base.combine_first(nd)
    base = base[~base.index.duplicated(keep="first")]
    return base[COLUMN].reindex(dates)


def main() -> None:
    """Build and write the per-gauge water-level provenance mask NetCDF."""
    dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
    rows: dict[str, np.ndarray] = {}
    n_no_frag = 0
    for shipped_dir, frag_dir in SOURCES.items():
        frags: dict[str, list[Path]] = defaultdict(list)
        for f in frag_dir.glob("*/*.csv"):
            frags[f.stem].append(f)
        shipped_files = sorted(shipped_dir.glob("*.csv"))
        print(f"{shipped_dir.name}: {len(shipped_files)} gauges, raw fragments for {len(frags)}")
        for sfile in shipped_files:
            gid = sfile.stem
            if gid in rows:  # river file takes precedence, as in package_water_level
                continue
            shipped = pd.read_csv(sfile, index_col="date", parse_dates=True)[COLUMN].reindex(dates)
            mask = np.zeros(len(dates), dtype=np.int8)
            if gid not in frags:
                n_no_frag += 1  # provenance unknown -> flag nothing (safe default)
            else:
                pre = _reconstruct_prefill(frags[gid], dates)
                mask[(pre.isna() & shipped.notna()).to_numpy()] = 1
                mask[((pre == 0) & shipped.notna()).to_numpy()] = 2
            rows[gid] = mask

    gids = sorted(rows)
    mask = np.stack([rows[g] for g in gids])
    da = xr.DataArray(
        mask,
        dims=("gauge_id", "time"),
        coords={"gauge_id": gids, "time": dates.to_numpy()},
        name="fill_mask",
        attrs={
            "long_name": "Water-level provenance mask",
            "description": (
                "1 = day interpolated in place (interpolate(limit=6), 15 for reservoir gauges, "
                "ParseAisHData.py); 2 = zero reading replaced by the day-of-year median; "
                "0 = untouched. Reconstructed by re-merging raw AisLevelCsv/AisLevelGTSCsv "
                "fragments and diffing against the shipped series."
            ),
            "flag_values": np.array([0, 1, 2], dtype=np.int8),
            "flag_meanings": "untouched interpolated zero_replaced",
        },
    )
    da.to_dataset().to_netcdf(
        OUT, encoding={"fill_mask": {"dtype": "int8", "zlib": True, "complevel": 4}}
    )
    n_interp, n_zero = int((mask == 1).sum()), int((mask == 2).sum())
    print(
        f"\nwrote {OUT.name}: {n_interp:,} interpolated and {n_zero:,} zero-replaced gauge-days "
        f"across {len(gids)} gauges ({n_no_frag} gauges had no raw fragments -> unflagged)"
    )


if __name__ == "__main__":
    main()
