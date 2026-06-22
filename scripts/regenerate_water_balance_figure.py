"""Regenerate fig_water_balance.png — runoff ratio + water-balance closure residual.

A 2x3 small multiple over the three precipitation products (ERA5-Land, MSWEP, GPCP):
  Row 1 (a-c): runoff ratio Q/P.
  Row 2 (d-f): water-balance closure residual R = P - Q - E (mm/yr), with E the GLEAM4
               actual evaporation. R ~ 0 means P, Q and E are mutually consistent;
               R > 0 means P exceeds Q + E (e.g. ERA5-Land snowfall wet bias, or net
               storage gain); R < 0 the converse. This replaces the old "ET proxy P-Q"
               panel, which was just the closure residual under the assumption E = 0.

Eligible catchments (mirrors scripts/check_et_adequacy.py): drainage area in
[50, 50000) km^2, >= 5 yr of finite daily discharge, and a finite annual-mean GLEAM E.

Reads from data/ (mounted external drive). With --write the figure goes to
paper/images/; otherwise to .tmp/cluster_diag/. Prints per-product n, residual
median/IQR, and Q/P median for the captions.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd
from matplotlib.colors import BoundaryNorm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))
from src.plots.paper_maps import get_russia_projection, scatter_map  # noqa: E402

DATA = PROJECT_ROOT / "data" / "CAMELS_RU"
GEOM = DATA / "geometry"
GLEAM_DIR = DATA / "parsed_meteo" / "gleam"
DISCHARGE_NC = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_discharge.nc"
BOUNDARIES = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_boundaries.gpkg"

# ERA5-Land precip: use the full-coverage source (2007-2024); CAMELS_RU/parsed_meteo/
# era5_land is a stale copy truncated at 2018-02.
ERA5_FULL = PROJECT_ROOT / "data" / "Russia" / "MeteoData" / "CamelsRU" / "era5_land"
PRODUCTS = {
    "ERA5-Land": (ERA5_FULL, "prcp"),
    "MSWEP": (DATA / "parsed_meteo" / "mswep", "precipitation"),
    "GPCP": (DATA / "parsed_meteo" / "gpcp", "precip"),
}
MIN_DAYS = 365 * 5  # >= 5 years of finite discharge

# Runoff-ratio bins (sequential) and residual bins (symmetric, diverging white centre).
QP_EDGES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0]

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"]})


def _annual_mean_mm_yr(s: pd.Series) -> float:
    """Convert a daily series (mm/d) to an annual mean (mm/yr)."""
    valid = s.dropna()
    if valid.empty:
        return np.nan
    return float(valid.mean()) * 365.25


def _gauge_terms(gauge_id: str, q_values: np.ndarray, dates: pd.DatetimeIndex) -> dict | None:
    """Per-gauge annual-mean Q, GLEAM actual evaporation, and P per product (mm/yr)."""
    q = pd.Series(q_values, index=dates).dropna()
    if len(q) < MIN_DAYS:
        return None
    gleam_path = GLEAM_DIR / f"{gauge_id}.csv"
    if not gleam_path.exists():
        return None
    gleam = pd.read_csv(
        gleam_path, index_col="date", parse_dates=True, usecols=["date", "actual_evaporation"]
    ).reindex(dates)
    aet = _annual_mean_mm_yr(gleam["actual_evaporation"])
    if not np.isfinite(aet):
        return None
    rec: dict = {"gauge_id": gauge_id, "q": _annual_mean_mm_yr(q), "aet": aet}
    for product, (pdir, pcol) in PRODUCTS.items():
        ppath = pdir / f"{gauge_id}.csv"
        if not ppath.exists():
            rec[f"p_{product}"] = np.nan
            continue
        p = pd.read_csv(ppath, index_col="date", parse_dates=True, usecols=["date", pcol])[pcol].reindex(
            dates
        )
        rec[f"p_{product}"] = _annual_mean_mm_yr(p)
    return rec


def build_table() -> pd.DataFrame:
    """Assemble the per-catchment Q/P and closure-residual table for all products."""
    ds = xr.open_dataset(DISCHARGE_NC)
    gcoord = "gauge_id" if "gauge_id" in ds.coords else "gauge"
    gauges = [str(g) for g in ds[gcoord].values]
    dates = pd.DatetimeIndex(ds["time"].values)
    q = ds["discharge_mm"].values

    ws = gpd.read_file(BOUNDARIES)[["gauge_id", "area_km2"]]
    ws["gauge_id"] = ws["gauge_id"].astype(str)
    small = set(ws.loc[ws["area_km2"] < 50_000, "gauge_id"])
    not_anom = set(ws.loc[(ws["area_km2"] >= 50) | (ws["area_km2"].isna()), "gauge_id"])
    valid_idx = [
        i
        for i, g in enumerate(gauges)
        if g in small and g in not_anom and np.isfinite(q[i]).sum() >= MIN_DAYS
    ]

    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=12) as exe:
        futs = {exe.submit(_gauge_terms, gauges[i], q[i], dates): i for i in valid_idx}
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None:
                rows.append(r)
    df = pd.DataFrame(rows)
    for product in PRODUCTS:
        df[f"qp_{product}"] = df["q"] / df[f"p_{product}"]
        df[f"res_{product}"] = df[f"p_{product}"] - df["q"] - df["aet"]
    return df


def _residual_edges(df: pd.DataFrame) -> list[float]:
    """Symmetric diverging bin edges centred on zero (rounded), from a robust spread of R."""
    allres = np.concatenate([df[f"res_{p}"].dropna().to_numpy() for p in PRODUCTS])
    lim = max(100.0, round(float(np.percentile(np.abs(allres), 95)) / 100.0) * 100.0)
    return [round(f * lim) for f in (-1.0, -0.6, -0.3, -0.1, 0.1, 0.3, 0.6, 1.0)]


def _row_colorbar(fig, axes_row, edges, cmap, label) -> None:
    """Add one binned colorbar spanning a whole row of map panels."""
    n = len(edges) - 1
    sm = plt.cm.ScalarMappable(norm=BoundaryNorm(edges, n), cmap=plt.get_cmap(cmap, n))
    cb = fig.colorbar(sm, ax=list(axes_row), orientation="horizontal", shrink=0.6, aspect=45, pad=0.02)
    cb.set_ticks(edges)
    cb.set_ticklabels([("0" if e == 0 else f"{e:g}") for e in edges])
    cb.set_label(label, fontsize=10)
    cb.ax.tick_params(labelsize=9)


def plot(df: pd.DataFrame, out: Path) -> None:
    """Render the 2x3 Q/P (row 1) and closure-residual (row 2) small multiple."""
    gauge = gpd.read_file(GEOM / "camels_gauges.gpkg").set_index("gauge_id")
    gauge.index = gauge.index.astype(str)
    tbl = df.set_index("gauge_id")
    common = [g for g in tbl.index if g in gauge.index]
    gdf = gauge.loc[common].copy()
    for product in PRODUCTS:
        gdf[f"qp_{product}"] = tbl.loc[common, f"qp_{product}"].to_numpy()
        gdf[f"res_{product}"] = tbl.loc[common, f"res_{product}"].to_numpy()
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=gauge.crs)

    ne = gpd.read_file(GEOM / "ne_land_clipped.gpkg")
    aea = get_russia_projection()
    res_edges = _residual_edges(df)
    products = list(PRODUCTS)
    panel = "abcdef"

    fig, axes = plt.subplots(
        2, 3, figsize=(15, 8.4), subplot_kw={"projection": aea}, constrained_layout=True
    )
    for j, product in enumerate(products):
        scatter_map(
            gdf,
            axes[0, j],
            f"qp_{product}",
            cmap_name="YlGnBu",
            bin_edges=QP_EDGES,
            marker_size=10,
            colorbar=False,
            title=f"({panel[j]}) Q/P — {product}",
            background_gdf=ne,
        )
        scatter_map(
            gdf,
            axes[1, j],
            f"res_{product}",
            cmap_name="RdBu_r",
            bin_edges=res_edges,
            marker_size=10,
            colorbar=False,
            title=f"({panel[3 + j]}) P − Q − E — {product}",
            background_gdf=ne,
        )

    _row_colorbar(fig, axes[0, :], QP_EDGES, "YlGnBu", "Runoff ratio Q/P")
    _row_colorbar(fig, axes[1, :], res_edges, "RdBu_r", "Closure residual P − Q − E (mm yr$^{-1}$)")
    fig.suptitle(
        "Water balance: runoff ratio and closure residual against GLEAM4 evaporation",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def main(write: bool) -> None:
    """Build the table, render the figure, and print caption numbers."""
    df = build_table()
    dest = (PROJECT_ROOT / "paper" / "images") if write else (PROJECT_ROOT / ".tmp" / "cluster_diag")
    dest.mkdir(parents=True, exist_ok=True)
    suffix = "" if write else "_test"
    plot(df, dest / f"fig_water_balance{suffix}.png")

    print("\n" + "=" * 64)
    print("WATER-BALANCE CAPTION NUMBERS (mm/yr):")
    print(f"  eligible catchments (area in [50,50000), >=5yr Q, GLEAM E finite): {len(df)}")
    for product in PRODUCTS:
        r = df[f"res_{product}"].dropna()
        qp = df[f"qp_{product}"].dropna()
        print(
            f"  {product:<10s} n={len(r):4d}  R median {r.median():+.0f}  "
            f"IQR [{r.quantile(0.25):+.0f}, {r.quantile(0.75):+.0f}]  | "
            f"Q/P median {qp.median():.2f}  (R>0: {100 * (r > 0).mean():.0f}%)"
        )
    print("=" * 64)


if __name__ == "__main__":
    main(write="--write" in sys.argv)
