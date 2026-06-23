"""Regenerate fig_precip_comparison.png — precipitation difference maps.

Two difference maps over the paper-analysis catchments (gauge-id length < 7):
  (a) ERA5-Land - MSWEP    (b) GPCP - MSWEP    (mm yr^-1)
on a diverging scale centred on zero. This replaces the three near-identical
absolute-precipitation maps: differences make ERA5-Land's high-latitude wet bias
directly visible (panel a is strongly positive) while GPCP and MSWEP nearly agree
(panel b near zero).

Reads basin-averaged daily precipitation from data/ (mounted external drive). With
--write the figure goes to paper/images/; otherwise to .tmp/cluster_diag/. Prints the
basin-mean of each difference for sanity against the text (~+218 and ~+35 mm/yr).
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

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))
from src.plots.paper_maps import get_russia_projection, scatter_map  # noqa: E402
from src.utils.paper_analysis_scope import paper_analysis_inclusion_mask  # noqa: E402

DATA = PROJECT_ROOT / "data" / "CAMELS_RU"
GEOM = DATA / "geometry"
# ERA5-Land precip: corrected de-accumulated source (era5land_tp_new); the era5_land
# copy over-accumulated tp (~1.5x), inflating basin P.
ERA5_FULL = PROJECT_ROOT / "data" / "Russia" / "MeteoData" / "CamelsRU" / "era5land_tp_new"
PRODUCTS = {
    "ERA5-Land": (ERA5_FULL, "prcp"),
    "MSWEP": (DATA / "parsed_meteo" / "mswep", "precipitation"),
    "GPCP": (DATA / "parsed_meteo" / "gpcp", "precip"),
}
# Common analysis window: all three products have full real coverage to 2023-12-31.
WINDOW = ("2008-01-01", "2023-12-31")
# (panel column, minuend, subtrahend)
DIFFS = [("ERA5-Land", "MSWEP"), ("GPCP", "MSWEP")]

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"]})


def _annual_mean_mm_yr(path: Path, col: str) -> float:
    """Annual-mean precipitation (mm/yr) over WINDOW from a daily per-gauge CSV (mm/d)."""
    if not path.exists():
        return np.nan
    s = pd.read_csv(path, index_col="date", parse_dates=True, usecols=["date", col])[col]
    s = s.loc[WINDOW[0] : WINDOW[1]].dropna()
    return float(s.mean()) * 365.25 if not s.empty else np.nan


def _gauge_precip(gauge_id: str) -> dict:
    """Per-gauge annual-mean precipitation for all three products (mm/yr)."""
    rec: dict = {"gauge_id": gauge_id}
    for product, (pdir, pcol) in PRODUCTS.items():
        rec[product] = _annual_mean_mm_yr(pdir / f"{gauge_id}.csv", pcol)
    return rec


def build_table() -> pd.DataFrame:
    """Per-catchment annual-mean P and the two product differences (paper-analysis scope)."""
    gauge = gpd.read_file(GEOM / "camels_gauges.gpkg")
    gauge["gauge_id"] = gauge["gauge_id"].astype(str)
    included = gauge.loc[paper_analysis_inclusion_mask(gauge["gauge_id"]).to_numpy(), "gauge_id"]

    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=12) as exe:
        futs = [exe.submit(_gauge_precip, g) for g in included]
        for fut in as_completed(futs):
            rows.append(fut.result())
    df = pd.DataFrame(rows)
    for minuend, subtrahend in DIFFS:
        df[f"d_{minuend}"] = df[minuend] - df[subtrahend]
    return df


def _edges(df: pd.DataFrame) -> list[int]:
    """Symmetric diverging bin edges centred on zero, rounded, from a robust spread."""
    alld = np.concatenate([df[f"d_{m}"].dropna().to_numpy() for m, _ in DIFFS])
    lim = max(100.0, round(float(np.percentile(np.abs(alld), 97)) / 100.0) * 100.0)
    return [round(f * lim) for f in (-1.0, -0.6, -0.3, -0.1, 0.1, 0.3, 0.6, 1.0)]


def plot(df: pd.DataFrame, out: Path) -> None:
    """Render the 1x2 precipitation-difference maps with a shared diverging colorbar."""
    gauge = gpd.read_file(GEOM / "camels_gauges.gpkg").set_index("gauge_id")
    gauge.index = gauge.index.astype(str)
    tbl = df.set_index("gauge_id")
    common = [g for g in tbl.index if g in gauge.index]
    gdf = gauge.loc[common].copy()
    for minuend, _ in DIFFS:
        gdf[f"d_{minuend}"] = tbl.loc[common, f"d_{minuend}"].to_numpy()
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=gauge.crs)

    ne = gpd.read_file(GEOM / "ne_land_clipped.gpkg")
    aea = get_russia_projection()
    edges = _edges(df)
    panel = "ab"

    fig, axes = plt.subplots(
        1, 2, figsize=(13, 5.0), subplot_kw={"projection": aea}, constrained_layout=True
    )
    for j, (minuend, subtrahend) in enumerate(DIFFS):
        scatter_map(
            gdf,
            axes[j],
            f"d_{minuend}",
            cmap_name="RdBu_r",
            bin_edges=edges,
            marker_size=11,
            colorbar=False,
            title=f"({panel[j]}) {minuend} − {subtrahend}",
            background_gdf=ne,
        )

    n = len(edges) - 1
    sm = plt.cm.ScalarMappable(norm=BoundaryNorm(edges, n), cmap=plt.get_cmap("RdBu_r", n))
    cb = fig.colorbar(sm, ax=list(axes), orientation="horizontal", shrink=0.5, aspect=45, pad=0.03)
    cb.set_ticks(edges)
    cb.set_ticklabels([("0" if e == 0 else f"{e:g}") for e in edges])
    cb.set_label("Mean annual precipitation difference (mm yr$^{-1}$)", fontsize=10)
    cb.ax.tick_params(labelsize=9)

    fig.suptitle(
        "Precipitation-product differences (relative to MSWEP v2.8)",
        fontsize=13,
        fontweight="bold",
        y=1.02,
    )
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def main(write: bool) -> None:
    """Build the table, render the figure, and print sanity numbers."""
    df = build_table()
    dest = (PROJECT_ROOT / "paper" / "images") if write else (PROJECT_ROOT / ".tmp" / "cluster_diag")
    dest.mkdir(parents=True, exist_ok=True)
    suffix = "" if write else "_test"
    plot(df, dest / f"fig_precip_comparison{suffix}.png")

    n_all = int(df[list(PRODUCTS)].notna().all(axis=1).sum())
    print("\n" + "=" * 64)
    print(f"PRECIP-DIFFERENCE CAPTION NUMBERS ({WINDOW[0][:4]}-{WINDOW[1][:4]}, basin-mean, mm/yr):")
    print(f"  paper-analysis catchments with all three products: {n_all}")
    for product in PRODUCTS:
        print(f"  {product:<10s} basin-mean P = {df[product].mean():.0f} mm/yr")
    for minuend, subtrahend in DIFFS:
        d = df[f"d_{minuend}"].dropna()
        print(f"  {minuend} − {subtrahend}: mean {d.mean():+.0f}  median {d.median():+.0f}  mm/yr")
    print("=" * 64)


if __name__ == "__main__":
    main(write="--write" in sys.argv)
