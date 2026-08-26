"""Regenerate fig_precip_comparison.png — precipitation difference maps.

Two difference maps over the paper-analysis catchments (gauge-id length < 7):
  (a) ERA5-Land - MSWEP    (b) GPCP - MSWEP    (mm yr^-1)
on a diverging scale centred on zero. This replaces the three near-identical
absolute-precipitation maps: differences make ERA5-Land's high-latitude wet bias
directly visible (panel a is strongly positive) while GPCP and MSWEP nearly agree
(panel b near zero).

Reads basin-averaged daily precipitation from data/ (mounted external drive). With
--write the figure goes to paper/images/ and paper/overleaf/images/; otherwise to
.tmp/cluster_diag/. Prints the basin-mean of each difference for sanity against the text
(~+218 and ~+35 mm/yr).
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import shutil
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


def write_caption_stats(df: pd.DataFrame) -> None:
    """Write the six Fig. 5 caption numbers to a provenance CSV (verify_macros-locked).

    These were the only numbers in the paper with neither a macro nor a provenance
    CSV; the consistency audit could not reproduce four of them to the printed digit.
    """
    gauge = gpd.read_file(GEOM / "camels_gauges.gpkg")
    gauge["gauge_id"] = gauge["gauge_id"].astype(str)
    if gauge.crs is None or gauge.crs.to_epsg() != 4326:
        gauge = gauge.to_crs(4326)
    lon = gauge.set_index("gauge_id").geometry.x
    d = df.set_index("gauge_id")["d_GPCP"].dropna()
    lon = lon.reindex(d.index)
    west = lon < 60.0
    east = (lon >= 100.0) & (lon <= 140.0)
    stats = {
        "mean_d_era5_mswep": float(df["d_ERA5-Land"].dropna().mean()),
        "mean_d_gpcp_mswep": float(d.mean()),
        "pct_gpcp_wetter_west60": float(100.0 * (d[west] > 0).mean()),
        "mean_d_gpcp_west60": float(d[west].mean()),
        "pct_gpcp_drier_east100140": float(100.0 * (d[east] < 0).mean()),
        "mean_d_gpcp_east100140": float(d[east].mean()),
        "n_west60": int(west.sum()),
        "n_east100140": int(east.sum()),
    }
    out = PROJECT_ROOT / "paper" / "tables" / "precip_comparison_caption.csv"
    pd.DataFrame([stats]).to_csv(out, index=False, float_format="%.6g")
    print(f"Wrote {out}")
    for k, v in stats.items():
        print(f"  {k} = {v:.1f}" if isinstance(v, float) else f"  {k} = {v}")


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
        1, 2, figsize=(13, 4.4), subplot_kw={"projection": aea}, constrained_layout=True
    )
    for j, (minuend, subtrahend) in enumerate(DIFFS):
        scatter_map(
            gdf,
            axes[j],
            f"d_{minuend}",
            cmap_name="RdBu_r",
            bin_edges=edges,
            marker_size=11,
            marker_edgecolor="#444444",
            marker_linewidth=0.2,
            colorbar=False,
            title=f"({panel[j]}) {minuend} − {subtrahend}",
            background_gdf=ne,
            # Editor pre-review: no coordinate reference on the map. ~0.54x shrink to
            # \textwidth from this 13in figure, so labels need to start well above 7pt.
            graticule_labels=True,
            graticule_label_size=14,
        )
    # Map-furniture consistency pass: one scale bar for the figure (both panels share the
    # same extent), placed on panel (a).
    from src.plots.paper_maps import add_scale_bar

    add_scale_bar(axes[0], length_km=1000, fontsize=14)

    n = len(edges) - 1
    sm = plt.cm.ScalarMappable(norm=BoundaryNorm(edges, n), cmap=plt.get_cmap("RdBu_r", n))
    cb = fig.colorbar(sm, ax=list(axes), orientation="horizontal", shrink=0.5, aspect=45, pad=0.02)
    cb.set_ticks(edges)
    cb.set_ticklabels([("0" if e == 0 else f"{e:g}") for e in edges])
    # Font floor (ESSD editor pre-review): prints at \textwidth from a ~12.6in source
    # (~0.55x shrink), so 9/10pt source text was landing at ~5pt in the final PDF.
    cb.set_label("Mean annual precipitation difference (mm yr$^{-1}$)", fontsize=14)
    cb.ax.tick_params(labelsize=14)

    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def main(write: bool, caption_only: bool = False) -> None:
    """Build the table, render the figure, and print sanity numbers."""
    df = build_table()
    write_caption_stats(df)
    if caption_only:
        return
    if write:
        dests = [PROJECT_ROOT / "paper" / "images", PROJECT_ROOT / "paper" / "overleaf" / "images"]
    else:
        dests = [PROJECT_ROOT / ".tmp" / "cluster_diag"]
    suffix = "" if write else "_test"
    # Save once and copy: two savefig(bbox_inches="tight") calls crop differently,
    # so the two image directories would never agree byte-for-byte.
    first = dests[0] / f"fig_precip_comparison{suffix}.png"
    dests[0].mkdir(parents=True, exist_ok=True)
    plot(df, first)
    for dest in dests[1:]:
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first, dest / first.name)
        print(f"Copied {dest / first.name}")

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
    main(write="--write" in sys.argv, caption_only="--caption-only" in sys.argv)
