#!/usr/bin/env python3
"""Quick adequacy check: compare water-balance AET (P-Q) against GLEAM4 AET.

For each eligible catchment under each precipitation product, computes:
  - AET_wb = annual mean P - annual mean Q (water-balance-derived AET, mm/yr)
  - AET_gleam = annual mean GLEAM4 actual_evaporation (mm/yr)

Reports medians, IQRs, and the per-catchment difference distribution to test
whether GLEAM4 PET (used in the Budyko diagnostic) and the implied AET are
consistent with the discharge-and-precipitation forcing pair.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm.auto import tqdm
import xarray as xr

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))
from src.utils.logger import setup_logger  # noqa: E402

log = setup_logger("ETAdequacy", log_file="logs/et_adequacy.log")

PRODUCTS = {
    # Corrected de-accumulated ERA5-Land precip; the era5_land copy over-accumulated
    # tp (~1.5x), inflating basin P. era5land_tp_new is the re-downloaded fix (prcp only).
    "ERA5-Land": (ROOT / "data/Russia/MeteoData/CamelsRU/era5land_tp_new", "prcp"),
    "MSWEP": (ROOT / "data/CAMELS_RU/parsed_meteo/mswep", "precipitation"),
    "GPCP": (ROOT / "data/CAMELS_RU/parsed_meteo/gpcp", "precip"),
}
GLEAM_DIR = ROOT / "data/CAMELS_RU/parsed_meteo/gleam"


def _annual_mean_mm_yr(s: pd.Series) -> float:
    """Convert a daily series (mm/d) to annual mean (mm/yr)."""
    valid = s.dropna()
    if valid.empty:
        return np.nan
    return float(valid.mean()) * 365.25


def _gauge_one(gauge_id: str, q_values: np.ndarray, dates: pd.DatetimeIndex) -> dict | None:
    """Compute per-gauge AET_wb (per product) and AET_gleam, all in mm/yr."""
    try:
        q = pd.Series(q_values, index=dates).dropna()
        if len(q) < 365 * 5:
            return None
        q_mm_yr = _annual_mean_mm_yr(q)

        gleam_path = GLEAM_DIR / f"{gauge_id}.csv"
        if not gleam_path.exists():
            return None
        gleam = pd.read_csv(
            gleam_path,
            index_col="date",
            parse_dates=True,
            usecols=["date", "actual_evaporation", "potential_evaporation"],
        ).reindex(dates)
        aet_gleam = _annual_mean_mm_yr(gleam["actual_evaporation"])
        pet_gleam = _annual_mean_mm_yr(gleam["potential_evaporation"])

        record: dict = {
            "gauge_id": gauge_id,
            "q_mm_yr": q_mm_yr,
            "aet_gleam_mm_yr": aet_gleam,
            "pet_gleam_mm_yr": pet_gleam,
        }
        for product, (pdir, pcol) in PRODUCTS.items():
            ppath = pdir / f"{gauge_id}.csv"
            if not ppath.exists():
                record[f"p_{product}_mm_yr"] = np.nan
                record[f"aet_wb_{product}_mm_yr"] = np.nan
                continue
            p = pd.read_csv(ppath, index_col="date", parse_dates=True, usecols=["date", pcol])[
                pcol
            ].reindex(dates)
            p_mm_yr = _annual_mean_mm_yr(p)
            record[f"p_{product}_mm_yr"] = p_mm_yr
            record[f"aet_wb_{product}_mm_yr"] = p_mm_yr - q_mm_yr if np.isfinite(p_mm_yr) else np.nan
        return record
    except Exception as exc:
        log.error(f"gauge {gauge_id}: {exc!r}")
        return None


def main() -> None:
    """Compute AET adequacy stats and print a summary."""
    disch = ROOT / "release/CAMELS_RU_v1.0/camels_ru_discharge.nc"
    boundaries = ROOT / "release/CAMELS_RU_v1.0/camels_ru_boundaries.gpkg"

    ds = xr.open_dataset(disch)
    gauge_coord = "gauge_id" if "gauge_id" in ds.coords else "gauge"
    gauges = [str(g) for g in ds[gauge_coord].values]
    dates = pd.DatetimeIndex(ds["time"].values)
    q = ds["discharge_mm"].values

    ws = gpd.read_file(boundaries)[["gauge_id", "area_km2"]]
    ws["gauge_id"] = ws["gauge_id"].astype(str)
    small = set(ws.loc[ws["area_km2"] < 50_000, "gauge_id"])
    not_anomalous = set(ws.loc[(ws["area_km2"] >= 50) | (ws["area_km2"].isna()), "gauge_id"])
    valid_idx = [
        i
        for i, g in enumerate(gauges)
        if g in small and g in not_anomalous and np.isfinite(q[i]).sum() >= 365 * 5
    ]
    log.info(f"{len(valid_idx)} gauges pass area>=50, area<50000, ≥5y discharge")

    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=12) as exe:
        futures = {exe.submit(_gauge_one, gauges[i], q[i], dates): gauges[i] for i in valid_idx}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="ET"):
            r = fut.result()
            if r is not None:
                rows.append(r)

    df = pd.DataFrame(rows).dropna(subset=["aet_gleam_mm_yr"])
    log.info(f"{len(df)} gauges with valid GLEAM AET")

    print("\n=== ET ADEQUACY SUMMARY (mm/yr, per-catchment then median across catchments) ===\n")
    print(
        f"GLEAM AET                : median {df['aet_gleam_mm_yr'].median():.0f}  "
        f"mean {df['aet_gleam_mm_yr'].mean():.0f}  "
        f"IQR [{df['aet_gleam_mm_yr'].quantile(0.25):.0f}, {df['aet_gleam_mm_yr'].quantile(0.75):.0f}]"
    )
    print(
        f"GLEAM PET                : median {df['pet_gleam_mm_yr'].median():.0f}  "
        f"mean {df['pet_gleam_mm_yr'].mean():.0f}  "
        f"IQR [{df['pet_gleam_mm_yr'].quantile(0.25):.0f}, {df['pet_gleam_mm_yr'].quantile(0.75):.0f}]"
    )
    print(
        f"Discharge Q              : median {df['q_mm_yr'].median():.0f}  "
        f"mean {df['q_mm_yr'].mean():.0f}\n"
    )

    for product in PRODUCTS:
        aet_col = f"aet_wb_{product}_mm_yr"
        p_col = f"p_{product}_mm_yr"
        sub = df.dropna(subset=[aet_col])
        diff = sub[aet_col] - sub["aet_gleam_mm_yr"]
        ratio = sub[aet_col] / sub["aet_gleam_mm_yr"]
        print(f"--- {product} ---")
        print(f"P                        : median {sub[p_col].median():.0f}")
        print(
            f"AET_wb = P - Q           : median {sub[aet_col].median():.0f}  "
            f"IQR [{sub[aet_col].quantile(0.25):.0f}, {sub[aet_col].quantile(0.75):.0f}]"
        )
        print(
            f"AET_wb - AET_gleam       : median {diff.median():+.0f}  "
            f"IQR [{diff.quantile(0.25):+.0f}, {diff.quantile(0.75):+.0f}]"
        )
        print(
            f"AET_wb / AET_gleam       : median {ratio.median():.2f}  "
            f"IQR [{ratio.quantile(0.25):.2f}, {ratio.quantile(0.75):.2f}]"
        )
        print(
            f"AET_wb > PET (impossible): {(sub[aet_col] > sub['pet_gleam_mm_yr']).sum()} "
            f"({100 * (sub[aet_col] > sub['pet_gleam_mm_yr']).mean():.1f}%)"
        )
        print(
            f"AET_wb < 0 (closure viol): {(sub[aet_col] < 0).sum()} "
            f"({100 * (sub[aet_col] < 0).mean():.1f}%)\n"
        )


if __name__ == "__main__":
    main()
