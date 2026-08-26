"""Derive the per-gauge provenance of the water-level out-of-range reversion (Sect. 4.1.3).

``scripts/repair_water_level_fills.py`` reverted every altered stage value lying outside
its own gauge's observed range to missing, in place, on the released NetCDF. Reverted
cells now carry ``quality_flag == 3`` and are indistinguishable from never-observed
cells, so the manuscript's 3420 / 89 / 991 claim group had no recomputation path
(round-7 consistency review, M1).

This script re-derives the reverted set exactly, with the same code the pipeline ran:

  1. Rebuild the packaging-time stage grid from the shipped per-gauge CSVs
     (``HydroData/Level``, ``HydroData/LevelGTS``), as ``package_dataset.package_water_level``
     does.
  2. Apply the same edge-fill cleanup (``_edge_fills``) with the same provenance mask.
  3. Apply ``repair_water_level_fills.out_of_range_mask`` to that pre-repair state.

It refuses to write unless the reconstruction is certified against both the recorded
repair-time counts (3420 values, 89 gauges, 991 negatives) and the released file
(cell-for-cell flag parity, value parity on surviving cells).

Writes ``paper/tables/water_level_reversion.csv`` (one row per affected gauge).
Requires the external data drive (``data/`` symlink) to be mounted.

Run: pixi run python scripts/derive_water_level_reversion.py
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package_dataset import (  # noqa: E402
    GEOM_DIR,
    LEVEL_DIR,
    LEVEL_GTS_DIR,
    PERIOD_END,
    PERIOD_START,
    WATER_LEVEL_FILL_MASK,
    _discharge_quality_flags,
    _edge_fills,
    _load_fill_mask,
)
from repair_water_level_fills import out_of_range_mask  # noqa: E402

RELEASE_NC = ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_water_level.nc"
OUT = ROOT / "paper" / "tables" / "water_level_reversion.csv"

# Recorded by the repair run itself (docstring + printout of repair_water_level_fills.py).
EXPECTED_REVERTED = 3420
EXPECTED_GAUGES = 89
EXPECTED_NEGATIVES = 991


def build_prerepair_grid() -> tuple[np.ndarray, np.ndarray, list[str], pd.DatetimeIndex]:
    """Rebuild the packaging-time (pre-repair) stage grid and quality flags."""
    import geopandas as gpd

    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws_ids = sorted(ws.gauge_id.astype(str).unique())
    dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")

    lvl_cm = np.full((len(ws_ids), len(dates)), np.nan, dtype=np.float32)
    for i, gid in enumerate(ws_ids):
        src = LEVEL_DIR / f"{gid}.csv"
        if not src.exists():
            src = LEVEL_GTS_DIR / f"{gid}.csv"
            if not src.exists():
                continue
        df = pd.read_csv(src, index_col="date", parse_dates=True)
        if "lvl_sm" in df.columns:
            sub = df["lvl_sm"].reindex(dates)
            valid = sub.notna()
            lvl_cm[i, valid.values] = sub[valid].values.astype(np.float32)

    mask = _load_fill_mask(ws_ids, dates, WATER_LEVEL_FILL_MASK)
    present = ~np.isnan(lvl_cm)
    filled = (mask == 1) & present
    edge = _edge_fills(present, filled)
    lvl_cm[edge] = np.nan
    present[edge] = False
    filled[edge] = False
    flag = _discharge_quality_flags(present, filled)
    flag[present & (mask == 2)] = 2
    return lvl_cm, flag, ws_ids, dates


def main() -> None:
    """Reconstruct the reverted set, certify it, and write the per-gauge CSV."""
    lvl_cm, flag, ws_ids, _ = build_prerepair_grid()
    stage = lvl_cm.astype(float)

    reverted = out_of_range_mask(stage, flag)
    n_rev = int(reverted.sum())
    gauge_mask = reverted.any(axis=1)
    n_gauges = int(gauge_mask.sum())
    negatives = np.isfinite(stage) & (stage < 0)
    n_neg = int(negatives.sum())
    print(f"reconstructed reverted set: {n_rev} values at {n_gauges} gauges")
    all_in = bool((negatives <= reverted).all())
    print(f"pre-repair negative stages: {n_neg} (all within the reverted set: {all_in})")

    errors = []
    if n_rev != EXPECTED_REVERTED:
        errors.append(f"reverted count {n_rev} != recorded {EXPECTED_REVERTED}")
    if n_gauges != EXPECTED_GAUGES:
        errors.append(f"gauge count {n_gauges} != recorded {EXPECTED_GAUGES}")
    if n_neg != EXPECTED_NEGATIVES:
        errors.append(f"negative count {n_neg} != recorded {EXPECTED_NEGATIVES}")
    if not (negatives <= reverted).all():
        errors.append("a pre-repair negative stage falls outside the reverted set")

    # Certify against the released file: applying the reversion must reproduce the
    # shipped flags cell for cell, and the shipped values on every surviving cell.
    post_flag = np.where(reverted, 3, flag).astype(np.int8)
    with xr.open_dataset(RELEASE_NC) as rel:
        rel_ids = [str(g) for g in rel["gauge_id"].values]
        if rel_ids != ws_ids:
            errors.append("gauge order differs from the release grid")
        else:
            rel_flag = rel["quality_flag"].values
            if not (post_flag == rel_flag).all():
                errors.append(f"flag parity fails on {int((post_flag != rel_flag).sum())} cells")
            rel_stage = rel["water_level_cm"].values
            keep = post_flag != 3
            if not np.allclose(stage[keep], rel_stage[keep], equal_nan=False):
                errors.append("value parity fails on surviving cells")

    if errors:
        for e in errors:
            print("GATE FAILED:", e)
        raise SystemExit(1)

    ids = np.array(ws_ids)
    rows = pd.DataFrame(
        {
            "gauge_id": ids[gauge_mask],
            "n_reverted": reverted[gauge_mask].sum(axis=1),
            "n_from_gap_fill": (reverted & (flag == 1))[gauge_mask].sum(axis=1),
            "n_from_zero_replacement": (reverted & (flag == 2))[gauge_mask].sum(axis=1),
            "n_negative": (reverted & negatives)[gauge_mask].sum(axis=1),
        }
    ).sort_values("gauge_id")
    rows.to_csv(OUT, index=False)
    print(f"all gates passed; wrote {OUT.relative_to(ROOT)} ({len(rows)} gauges)")


if __name__ == "__main__":
    main()
