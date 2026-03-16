"""Package CAMELS-RU dataset for Zenodo release.

Creates the release directory structure described in Table 4 of the ESSD paper:
  - camels_ru_boundaries.gpkg    Watershed boundaries (GeoPackage)
  - camels_ru_discharge.nc       Daily discharge time series (NetCDF-4)
  - camels_ru_forcing.nc         Meteorological forcing (NetCDF-4)
  - camels_ru_attributes.csv     HydroATLAS physiographic attributes
  - camels_ru_signatures.csv     Hydrological signatures
  - camels_ru_water_level/       Daily water level CSVs

Usage:
    pixi run python scripts/package_dataset.py
"""

from __future__ import annotations

from pathlib import Path
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
OUTPUT_DIR = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0"

# Source directories
GEOM_DIR = DATA_DIR / "geometry"
DISCHARGE_DIR = DATA_DIR / "HydroData" / "Discharge"
COMPOUND_DIR = DATA_DIR / "HydroData" / "Compound"
LEVEL_DIR = DATA_DIR / "HydroData" / "Level"
LEVEL_GTS_DIR = DATA_DIR / "HydroData" / "LevelGTS"
ERA5_DIR = DATA_DIR / "parsed_meteo" / "era5_land"
MSWEP_DIR = DATA_DIR / "parsed_meteo" / "mswep"
ATTRS_FILE = DATA_DIR / "attributes" / "hydro_atlas_cis_camels.csv"

PERIOD_START = "2008-01-01"
PERIOD_END = "2023-12-31"


def package_boundaries() -> None:
    """Copy watershed boundaries GeoPackage."""
    print("Packaging boundaries...")
    src = GEOM_DIR / "camels_watersheds.gpkg"
    dst = OUTPUT_DIR / "camels_ru_boundaries.gpkg"

    ws = gpd.read_file(src)
    # Keep essential columns only
    keep_cols = ["gauge_id", "name", "area_km2", "area_roshydromet", "area_diff_perc", "geometry"]
    ws = ws[[c for c in keep_cols if c in ws.columns]]
    ws.to_file(dst, driver="GPKG")
    print(f"  {len(ws)} catchments -> {dst.name}")


def package_discharge() -> None:
    """Build discharge NetCDF from per-gauge CSVs."""
    print("Packaging discharge...")

    # Get gauge list from geometry
    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws_ids = sorted(ws.gauge_id.astype(str).unique())

    dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
    n_dates = len(dates)
    n_gauges = len(ws_ids)

    # Initialize arrays
    q_mm = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    q_m3s = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    q_flag = np.full((n_gauges, n_dates), 3, dtype=np.int8)  # 3 = missing

    for i, gid in enumerate(ws_ids):
        # Try Compound first (has q_mm_day), then raw Discharge
        compound_file = COMPOUND_DIR / f"{gid}.csv"
        discharge_file = DISCHARGE_DIR / f"{gid}.csv"

        if compound_file.exists():
            df = pd.read_csv(compound_file, index_col="date", parse_dates=True)
            if "q_mm_day" in df.columns:
                sub = df["q_mm_day"].reindex(dates)
                valid = sub.notna()
                q_mm[i, valid.values] = sub[valid].values.astype(np.float32)
                q_flag[i, valid.values] = 0  # observed
            if "q_cms" in df.columns:
                sub = df["q_cms"].reindex(dates)
                valid = sub.notna()
                q_m3s[i, valid.values] = sub[valid].values.astype(np.float32)
        elif discharge_file.exists():
            df = pd.read_csv(discharge_file, index_col="date", parse_dates=True)
            col = [c for c in df.columns if "q" in c.lower() or "discharge" in c.lower()]
            if col:
                sub = df[col[0]].reindex(dates)
                valid = sub.notna()
                q_m3s[i, valid.values] = sub[valid].values.astype(np.float32)
                q_flag[i, valid.values] = 0

    ds = xr.Dataset(
        {
            "discharge_mm": (["gauge", "time"], q_mm),
            "discharge_m3s": (["gauge", "time"], q_m3s),
            "quality_flag": (["gauge", "time"], q_flag),
        },
        coords={
            "gauge": ws_ids,
            "time": dates,
        },
        attrs={
            "title": "CAMELS-RU daily discharge",
            "source": "AIS GMVO / Roshydromet",
            "period": f"{PERIOD_START} to {PERIOD_END}",
            "quality_flag_values": "0=observed, 1=interpolated (<=6 days), 2=suspect, 3=missing",
            "units_mm": "mm/day",
            "units_m3s": "m3/s",
        },
    )
    out = OUTPUT_DIR / "camels_ru_discharge.nc"
    ds.to_netcdf(
        out,
        encoding={
            "discharge_mm": {"dtype": "float32", "zlib": True, "complevel": 4},
            "discharge_m3s": {"dtype": "float32", "zlib": True, "complevel": 4},
            "quality_flag": {"dtype": "int8", "zlib": True, "complevel": 4},
        },
    )
    n_with_data = int((q_flag != 3).any(axis=1).sum())
    print(f"  {n_with_data}/{n_gauges} gauges with data -> {out.name}")


def package_forcing() -> None:
    """Build meteorological forcing NetCDF."""
    print("Packaging forcing...")

    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws_ids = sorted(ws.gauge_id.astype(str).unique())
    dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
    n_dates = len(dates)
    n_gauges = len(ws_ids)

    # Variables: MSWEP precip, ERA5-Land temp (mean, min, max), PET
    precip = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_mean = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_min = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_max = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    pet = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)

    for i, gid in enumerate(ws_ids):
        # MSWEP precipitation
        mswep_file = MSWEP_DIR / f"{gid}.csv"
        if mswep_file.exists():
            df = pd.read_csv(mswep_file, index_col="date", parse_dates=True)
            if "precipitation" in df.columns:
                sub = df["precipitation"].reindex(dates)
                valid = sub.notna()
                precip[i, valid.values] = sub[valid].values.astype(np.float32)

        # ERA5-Land temperature + PET
        era5_file = ERA5_DIR / f"{gid}.csv"
        if era5_file.exists():
            df = pd.read_csv(era5_file, index_col="date", parse_dates=True)
            for var, arr in [("t_mean", t_mean), ("t_min", t_min), ("t_max", t_max), ("pet", pet)]:
                if var in df.columns:
                    sub = df[var].reindex(dates)
                    valid = sub.notna()
                    arr[i, valid.values] = sub[valid].values.astype(np.float32)

    ds = xr.Dataset(
        {
            "precip": (["gauge", "time"], precip),
            "temp_mean": (["gauge", "time"], t_mean),
            "temp_min": (["gauge", "time"], t_min),
            "temp_max": (["gauge", "time"], t_max),
            "pet": (["gauge", "time"], pet),
        },
        coords={"gauge": ws_ids, "time": dates},
        attrs={
            "title": "CAMELS-RU meteorological forcing",
            "precip_source": "MSWEP v2.8",
            "temp_source": "ERA5-Land",
            "pet_source": "ERA5-Land (Penman-Monteith)",
            "period": f"{PERIOD_START} to {PERIOD_END}",
            "precip_units": "mm/day",
            "temp_units": "degrees_C",
            "pet_units": "mm/day",
        },
    )
    out = OUTPUT_DIR / "camels_ru_forcing.nc"
    encoding = {v: {"dtype": "float32", "zlib": True, "complevel": 4} for v in ds.data_vars}
    ds.to_netcdf(out, encoding=encoding)
    print(f"  {n_gauges} gauges -> {out.name}")


def package_attributes() -> None:
    """Copy HydroATLAS attributes CSV."""
    print("Packaging attributes...")
    if not ATTRS_FILE.exists():
        print(f"  WARNING: {ATTRS_FILE} not found, skipping")
        return
    df = pd.read_csv(ATTRS_FILE)
    out = OUTPUT_DIR / "camels_ru_attributes.csv"
    df.to_csv(out, index=False)
    print(f"  {len(df)} catchments, {len(df.columns)} columns -> {out.name}")


def package_signatures() -> None:
    """Copy hydrological signatures CSV."""
    print("Packaging signatures...")
    sig_file = PROJECT_ROOT / "paper" / "tables" / "overall_hydro_statistics.csv"
    if not sig_file.exists():
        print(f"  WARNING: {sig_file} not found, skipping")
        return
    shutil.copy2(sig_file, OUTPUT_DIR / "camels_ru_signatures_summary.csv")
    print("  -> camels_ru_signatures_summary.csv")


def package_water_level() -> None:
    """Copy water level CSVs to release directory."""
    print("Packaging water level...")
    out_dir = OUTPUT_DIR / "camels_ru_water_level"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Get gauge IDs that have watersheds
    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws_ids = set(ws.gauge_id.astype(str))

    count = 0
    for src_dir in [LEVEL_DIR, LEVEL_GTS_DIR]:
        if not src_dir.exists():
            continue
        for f in sorted(src_dir.glob("*.csv")):
            if f.stem in ws_ids:
                shutil.copy2(f, out_dir / f.name)
                count += 1

    print(f"  {count} gauge files -> {out_dir.name}/")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Packaging CAMELS-RU dataset to {OUTPUT_DIR}\n")

    package_boundaries()
    package_attributes()
    package_signatures()
    package_water_level()
    package_forcing()
    package_discharge()

    print(f"\nDone. Release package at: {OUTPUT_DIR}")
    # Show sizes
    total = 0
    for f in OUTPUT_DIR.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    print(f"Total size: {total / 1e9:.1f} GB")


if __name__ == "__main__":
    main()
