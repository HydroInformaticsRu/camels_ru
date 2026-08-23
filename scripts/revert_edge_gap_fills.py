"""Revert extrapolated gap fills in the pipeline discharge CSVs (one-time repair, 2026-08-23).

``ParseAisQData.interpolate_discharge`` used ``interpolate(limit=6)``, which filled the
first six days of *every* gap; 14 172 of the 15 863 filled days were polynomial
extrapolations into longer gaps rather than bridges. ``scripts/package_dataset.py``
already reverts them when building ``camels_ru_discharge.nc``; this script applies the
same rule to the pipeline inputs so that grading (``scripts/GradeCompound.py``) sees the
released series:

- ``data/CAMELS_RU/HydroData/Compound/<gauge>.csv``   (``q_cms``, ``q_mm_day``)
- ``data/CAMELS_RU/HydroData/Discharge/<gauge>.csv``  (``q_cms``)

Edge days come from the pre-repair fill mask (``discharge_fill_mask.nc``) and
``package_dataset._edge_fills``. Every modified file is copied first to
``data/CAMELS_RU/HydroData/_pre_edge_revert_2026-08-23/``. Re-running after the mask has
been re-derived (``scripts/derive_discharge_fill_mask.py``) finds no edge days and is a no-op.

Run: ``pixi run python scripts/revert_edge_gap_fills.py``
"""

from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_dataset import _edge_fills  # noqa: E402

HYDRO = ROOT / "data" / "CAMELS_RU" / "HydroData"
MASK = HYDRO / "discharge_fill_mask.nc"
BACKUP = HYDRO / "_pre_edge_revert_2026-08-23"
TARGETS = {"Compound": ["q_cms", "q_mm_day"], "Discharge": ["q_cms"]}


def _edge_days_per_gauge() -> dict[str, pd.DatetimeIndex]:
    """Dates whose fill does not bridge two observed days, keyed by gauge id."""
    with xr.open_dataset(MASK) as ds:
        filled = ds["fill_mask"].values.astype(bool)
        gauges = [str(g) for g in ds["gauge_id"].values]
        dates = pd.DatetimeIndex(ds["time"].values)
    present = np.zeros_like(filled)
    for i, gauge in enumerate(gauges):
        path = HYDRO / "Discharge" / f"{gauge}.csv"
        if not path.exists():
            continue
        q = pd.read_csv(path, index_col="date", parse_dates=True)["q_cms"].reindex(dates)
        present[i] = q.notna().to_numpy()
    edge = _edge_fills(present, filled)
    return {g: dates[edge[i]] for i, g in enumerate(gauges) if edge[i].any()}


def main() -> None:
    """Blank the edge-fill days in both pipeline directories."""
    edge_days = _edge_days_per_gauge()
    n_days = sum(len(d) for d in edge_days.values())
    print(f"{n_days:,} extrapolated fill days at {len(edge_days)} gauges")
    if not edge_days:
        return
    n_files = 0
    for folder, columns in TARGETS.items():
        for gauge, days in edge_days.items():
            path = HYDRO / folder / f"{gauge}.csv"
            if not path.exists():
                continue
            backup = BACKUP / folder / path.name
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
            df = pd.read_csv(path, index_col="date", parse_dates=True)
            hit = df.index.isin(days)
            for col in columns:
                if col in df.columns:
                    df.loc[hit, col] = np.nan
            df.to_csv(path)
            n_files += 1
    print(f"rewrote {n_files} files; backups in {BACKUP.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
