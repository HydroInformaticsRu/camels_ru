"""Merge discharge and level data into compound per-gauge CSV files.

For each gauge in the watershed file, combines:
- Discharge (q_cms) + derived q_mm_day
- Water level (lvl_sm) + derived lvl_mbs (meters Baltic System)

Level data uses regular AIS levels first, then GTS as fallback (no overlap
between the two networks).
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm.auto import tqdm

DISCHARGE_DIR = Path("data/CAMELS_RU/HydroData/Discharge")
LEVEL_DIR = Path("data/CAMELS_RU/HydroData/Level")
LEVEL_GTS_DIR = Path("data/CAMELS_RU/HydroData/LevelGTS")

WATERSHED_FILE = Path("data/CAMELS_RU/geometry/camels_watersheds.gpkg")
HEIGHTS_FILE = Path("data/CAMELS_RU/AisLevelCsv/gauge_heights.csv")
GTS_HEIGHTS_FILE = Path("data/CAMELS_RU/AisLevelGTSCsv/GTS_heights.csv")

COMPOUND_DIR = Path("data/CAMELS_RU/HydroData/Compound")


def load_heights() -> pd.Series:
    """Load gauge zero elevations (m BS) from regular and GTS sources."""
    parts = []
    if HEIGHTS_FILE.exists():
        regular = pd.read_csv(HEIGHTS_FILE, index_col=0)
        regular.index = regular.index.astype(str)
        parts.append(regular["height"].astype(float))
    if GTS_HEIGHTS_FILE.exists():
        gts = pd.read_csv(GTS_HEIGHTS_FILE, index_col="gauge_id")
        gts.index = gts.index.astype(str)
        parts.append(gts["height"].astype(float))

    if not parts:
        return pd.Series(dtype=float, name="height")
    if len(parts) == 1:
        return parts[0]
    # Regular takes precedence (no actual overlap, but just in case)
    return parts[0].combine_first(parts[1])


def build_compound(gauge_id: str, ws_area: float, gauge_height: float) -> pd.DataFrame | None:
    """Build compound hydro file for a single gauge.

    Returns None if neither discharge nor level data exists.
    """
    frames = []

    # Discharge
    q_file = DISCHARGE_DIR / f"{gauge_id}.csv"
    if q_file.exists():
        q_df = pd.read_csv(q_file, index_col="date", parse_dates=True)
        if ws_area > 0 and not np.isnan(ws_area):
            q_df["q_mm_day"] = (q_df["q_cms"] * 86400) / (ws_area * 1e3)
        frames.append(q_df)

    # Level: regular first, GTS as fallback
    lvl_file = LEVEL_DIR / f"{gauge_id}.csv"
    if not lvl_file.exists():
        lvl_file = LEVEL_GTS_DIR / f"{gauge_id}.csv"
    if lvl_file.exists():
        lvl_df = pd.read_csv(lvl_file, index_col="date", parse_dates=True)
        if not np.isnan(gauge_height):
            lvl_df["lvl_mbs"] = gauge_height + lvl_df["lvl_sm"] / 100.0
        frames.append(lvl_df)

    if not frames:
        return None
    return pd.concat(frames, axis=1)


if __name__ == "__main__":
    COMPOUND_DIR.mkdir(exist_ok=True, parents=True)

    gpd.options.io_engine = "pyogrio"
    ws_file = gpd.read_file(WATERSHED_FILE)
    ws_file.set_index("gauge_id", inplace=True)

    heights = load_heights()

    created = 0
    for gauge_id in tqdm(ws_file.index, desc="Building compound files"):
        gauge_id_str = str(gauge_id)
        ws_area = ws_file.loc[gauge_id, "area_km2"]
        gauge_height = heights.get(gauge_id_str, np.nan)

        compound = build_compound(gauge_id_str, ws_area, gauge_height)
        if compound is not None:
            compound.to_csv(COMPOUND_DIR / f"{gauge_id_str}.csv")
            created += 1

    print(f"Created {created} compound files out of {len(ws_file)} gauges")
