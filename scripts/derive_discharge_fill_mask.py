"""Derive the discharge gap-fill provenance mask for the release flag.

The discharge pipeline (scripts/ParseAisQData.py) interpolates <=6-day gaps in
place (second-order polynomial), overwriting the merged series, so the released
discharge.nc cannot tell an interpolated day from a real observation. This script
recovers that provenance non-destructively:

  1. Reconstruct the PRE-fill merged series per gauge by re-merging the raw
     per-year fragments in ``AisDischargeCsv/`` (combine_first onto the 2008-2023
     daily grid, dedup keep-first -- mirrors src/data_processing/ais.ais_merger,
     which produced the original pre-fill series before interpolation).
  2. A day is gap-filled iff it is MISSING in the pre-fill series but PRESENT in
     the shipped (post-fill) merged series: fill = pre.isna() & filled.notna().
     This needs no assumption about pandas interpolate() edge semantics -- the
     shipped series is ground truth for "present now", the re-merge for "observed".

Writes ``data/CAMELS_RU/HydroData/discharge_fill_mask.nc`` (gauge_id x time int8,
1 = gap-filled), consumed by scripts/package_dataset.py::package_discharge.

Run: pixi run python scripts/derive_discharge_fill_mask.py
"""

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).parent.parent
DATA = PROJECT_ROOT / "data" / "CAMELS_RU"
FRAG_DIR = DATA / "AisDischargeCsv"  # raw per-XLS, per-year fragments (pre-merge, pre-fill)
FILLED_DIR = DATA / "HydroData" / "Discharge"  # merged + interpolated-in-place (shipped source)
OUT = DATA / "HydroData" / "discharge_fill_mask.nc"

PERIOD_START, PERIOD_END = "2008-01-01", "2023-12-31"


def _reconstruct_prefill(frag_files: list[Path], dates: pd.DatetimeIndex) -> pd.Series:
    """Re-merge raw fragments into the pre-fill q_cms series (mirrors ais_merger)."""
    base = pd.DataFrame(index=dates, columns=["q_cms"], dtype=float)
    base.index.name = "date"
    for f in frag_files:
        nd = pd.read_csv(f, index_col="date", parse_dates=True).rename(columns={"discharge": "q_cms"})
        base = base.combine_first(nd)
    base = base[~base.index.duplicated(keep="first")]
    return base["q_cms"].reindex(dates)


def main() -> None:
    """Build and write the per-gauge gap-fill mask NetCDF."""
    dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")

    # Group raw fragments by gauge id (filename stem), as ais_merger does.
    frags: dict[str, list[Path]] = defaultdict(list)
    for f in FRAG_DIR.glob("*/*.csv"):
        frags[f.stem].append(f)
    print(f"raw fragments: {sum(len(v) for v in frags.values()):,} files for {len(frags):,} gauges")

    filled_files = sorted(FILLED_DIR.glob("*.csv"))
    gids = [f.stem for f in filled_files]
    mask = np.zeros((len(gids), len(dates)), dtype=np.int8)

    n_no_frag = 0
    total_fills = 0
    for i, (gid, ffile) in enumerate(zip(gids, filled_files, strict=True)):
        filled = pd.read_csv(ffile, index_col="date", parse_dates=True)
        fcol = "q_cms" if "q_cms" in filled.columns else filled.columns[0]
        fil = filled[fcol].reindex(dates)
        if gid not in frags:
            # No raw fragments -> cannot establish provenance -> flag nothing (safe default).
            n_no_frag += 1
            continue
        pre = _reconstruct_prefill(frags[gid], dates)
        is_fill = (pre.isna() & fil.notna()).to_numpy()
        mask[i] = is_fill.astype(np.int8)
        total_fills += int(is_fill.sum())
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(gids)} gauges processed")

    da = xr.DataArray(
        mask,
        dims=("gauge_id", "time"),
        coords={"gauge_id": gids, "time": dates.to_numpy()},
        name="fill_mask",
        attrs={
            "long_name": "Discharge gap-fill mask",
            "description": (
                "1 = day interpolated in place (<=6-day second-order-polynomial fill, "
                "ParseAisQData.py); 0 = not gap-filled. Reconstructed by re-merging raw "
                "AisDischargeCsv fragments and diffing against the shipped filled series."
            ),
            "flag_values": np.array([0, 1], dtype=np.int8),
            "flag_meanings": "not_filled gap_filled",
        },
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    da.to_dataset().to_netcdf(
        OUT, encoding={"fill_mask": {"dtype": "int8", "zlib": True, "complevel": 4}}
    )

    n_gauges_filled = int((mask.sum(axis=1) > 0).sum())
    print(
        f"\nwrote {OUT.name}: {total_fills:,} gap-filled gauge-days across "
        f"{n_gauges_filled} gauges ({n_no_frag} gauges had no raw fragments -> unflagged)"
    )


if __name__ == "__main__":
    main()
