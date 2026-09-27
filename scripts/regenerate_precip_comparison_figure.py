"""Regenerate fig_precip_comparison.pdf — precipitation difference maps.

Two Albers hexagon maps show the median per-gauge annual precipitation difference
within each occupied cell: (a) ERA5-Land - MSWEP and (b) GPCP - MSWEP (mm yr^-1).
The fixed pointy-top grid has 66 km circumradius and projected origin 0,0, shared
with the other paper maps. Histograms count original gauges, not cells. Median
aggregation changes only spatial display; all per-gauge values and caption
statistics remain unchanged. Empty cells are unfilled; all-missing cells are grey.

Reads basin-averaged daily precipitation from data/ (mounted external drive). With
--write the figure goes to paper/images/ and paper/overleaf/images/; otherwise to
.tmp/cluster_diag/. Prints the basin-mean of each difference for sanity against the text
(~+96 and ~+53 mm/yr).
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
from src.plots.hex_maps import aggregate_hex, assign_hex_cells, export_hex_support  # noqa: E402
from src.plots.paper_maps import (  # noqa: E402
    _add_graticule,
    _class_counts,
    _format_edge_labels,
    _set_extent_from_data,
    get_russia_projection,
)
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

plt.rcParams.update(
    {"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "pdf.fonttype": 42}
)


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


def plot(df: pd.DataFrame, out: Path, *, support_dir: Path | None = None) -> None:
    """Render stacked cell-median maps with original-gauge histograms and scales."""
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

    if gdf.crs is None or ne.crs is None:
        raise ValueError("Gauge and basemap layers must have a CRS")
    gdf = gdf.to_crs(4326).sort_index()
    ne = ne.to_crs(aea.proj4_init)
    support = support_dir if support_dir is not None else PROJECT_ROOT / ".tmp/cluster_diag/hex_support"
    support.mkdir(parents=True, exist_ok=True)
    columns = [f"d_{m}" for m, _ in DIFFS]
    assign_hex_cells(gdf, aea.proj4_init).join(gdf[columns]).to_csv(
        support / "precip_comparison_membership.csv", index_label="gauge_id"
    )
    fig = plt.figure(figsize=(160 / 25.4, 170 / 25.4), constrained_layout=True)
    grid = fig.add_gridspec(4, 2, height_ratios=[1, 0.28, 1, 0.28], hspace=0.10, wspace=0.12)
    n = len(edges) - 1
    norm = BoundaryNorm(edges, n, clip=True)
    cmap = plt.get_cmap("RdBu_r", n)
    for j, (minuend, subtrahend) in enumerate(DIFFS):
        value_col = f"d_{minuend}"
        cells = aggregate_hex(gdf, value_col, aea.proj4_init)
        export_hex_support(
            gdf,
            value_col,
            cells,
            aea.proj4_init,
            support / f"precip_comparison_{minuend}.json",
        )
        ax = fig.add_subplot(grid[2 * j, :], projection=aea)
        ax.axis("off")
        _set_extent_from_data(ax, gdf)
        _add_graticule(ax)
        ne.plot(ax=ax, color="#DEDEDE", edgecolor="#B9B9B9", linewidth=0.3, zorder=1)
        facecolors = [cmap(norm(value)) if pd.notna(value) else "#BBBBBB" for value in cells["value"]]
        ax.add_geometries(
            cells.geometry, crs=aea, facecolor=facecolors, edgecolor="#3E3E3E", linewidth=0.22, zorder=3
        )
        ax.set_title(
            f"({panel[j]}) {minuend} − {subtrahend} · cell median", fontsize=9, loc="left", pad=7
        )
        hist = fig.add_subplot(grid[2 * j + 1, 0])
        counts = _class_counts(gdf[value_col].to_numpy(), np.asarray(edges))
        bars = hist.bar(
            np.arange(n), counts, color=[cmap(i) for i in range(n)], edgecolor="#333333", linewidth=0.3
        )
        hist.bar_label(bars, fontsize=8.5, padding=2)
        hist.set_ylim(0, max(float(counts.max()) * 1.35, 1))
        hist.set_xticks([])
        hist.set_yticks([])
        hist.set_title("Gauge counts by colour class", fontsize=8.5, loc="left", pad=3)
        for side in ("left", "right", "top"):
            hist.spines[side].set_visible(False)
        note = fig.add_subplot(grid[2 * j + 1, 1])
        note.axis("off")
        missing = int(gdf[value_col].isna().sum())
        note.text(
            0,
            1,
            f"{len(gdf) - missing:,} gauges · {len(cells):,} cells · {missing} missing",
            fontsize=8.5,
            va="top",
        )
        cax = note.inset_axes([0, 0.42, 1, 0.16])
        cb = fig.colorbar(
            plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation="horizontal", ticks=edges
        )
        cb.set_ticklabels(_format_edge_labels(np.asarray(edges)))
        cb.set_label("Annual P difference (mm yr$^{-1}$)", fontsize=8.5)
        cb.ax.tick_params(labelsize=8.5, length=2)

    # Resolve the layout at delivery DPI before freezing its physical dimensions.
    fig.set_dpi(400)
    fig.canvas.draw()
    fig.set_layout_engine("none")
    fig.savefig(out, dpi=400, facecolor="white")
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
    # Save once and copy so both manuscript image trees are byte-identical.
    first = dests[0] / f"fig_precip_comparison{suffix}.pdf"
    dests[0].mkdir(parents=True, exist_ok=True)
    support_dir = PROJECT_ROOT / (
        "paper/figure_data/hex_support" if write else ".tmp/cluster_diag/hex_support"
    )
    plot(df, first, support_dir=support_dir)
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
