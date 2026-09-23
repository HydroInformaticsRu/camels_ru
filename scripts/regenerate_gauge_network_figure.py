"""Regenerate the study-area figure (Section 2, Figure 1).

Two-panel layout: (a) fixed 66 km Albers hexagons coloured by modal
Köppen-Geiger class of their gauge outlets (alphabetical ties), (b) individual
catchment size distribution. Legend counts describe gauges, not cells.

The climate classes are derived from the released forcing itself: the 2008-2023
monthly climatologies of MSWEP precipitation and ERA5-Land air temperature in
``camels_ru_forcing.nc``, classified with the Peel et al. (2007) criteria implemented
in ``src/meteo/koppen.py``. The per-catchment classes are written to
``results/koppen_classes.csv`` for provenance.

Usage
-----
    pixi run python scripts/regenerate_gauge_network_figure.py            # test output
    pixi run python scripts/regenerate_gauge_network_figure.py --write    # paper output

Without ``--write`` the figure goes to ``.tmp/cluster_diag/`` so the manuscript
asset is never touched by accident.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import sys
import warnings

import cartopy.crs as ccrs
import geopandas as gpd
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import pandas as pd

from utils.release_io import open_release_dataset

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.meteo.koppen import classify_koppen  # noqa: E402
from src.plots.hex_maps import aggregate_hex, export_hex_support  # noqa: E402
from src.plots.paper_maps import (  # noqa: E402
    _set_extent_from_data,
    get_russia_projection,
)
from src.static.hydro_atlas_analysis import (  # noqa: E402
    categorize_catchment_size,
    get_size_categories,
)
from src.utils.paper_analysis_scope import (  # noqa: E402
    filter_paper_analysis_index,
    paper_analysis_scope_summary,
)

gpd.options.io_engine = "pyogrio"
warnings.simplefilter(action="ignore", category=FutureWarning)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
    }
)

# Köppen-Geiger legend colours in the Peel et al. (2007) / Beck et al. (2018) convention;
# dict order is the canonical legend order.
MERGE_MAX = 11  # classes with at most this many catchments merge into "other"

KG_COLORS = {
    "BWk": "#FF9696",
    "BSk": "#FFDC64",
    "Csa": "#FFFF00",
    "Csb": "#C8C800",
    "Cwa": "#96FF96",
    "Cwb": "#64C864",
    "Cfa": "#C8FF50",
    "Cfb": "#64FF50",
    "Dsa": "#FF00FF",
    "Dsb": "#C800C8",
    "Dsc": "#963296",
    "Dsd": "#966496",
    "Dwa": "#ABB1FF",
    "Dwb": "#5A77DB",
    "Dwc": "#4C51B5",
    "Dwd": "#320087",
    "Dfa": "#00FFFF",
    "Dfb": "#38C8FF",
    "Dfc": "#007D7D",
    "Dfd": "#00465F",
    "ET": "#B2B2B2",
    "EF": "#666666",
}
FALLBACK_COLOR = "#999999"

# ── Paths ────────────────────────────────────────────────────────────────────
GEOM_DIR = PROJECT_ROOT / "data" / "CAMELS_RU" / "geometry"
FORCING_NC = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_forcing.nc"
KG_CSV = PROJECT_ROOT / "results" / "koppen_classes.csv"
OUT_NAME = "fig_gauge_network.png"
PAPER_OUTPUTS = (
    PROJECT_ROOT / "paper" / "images" / OUT_NAME,
    PROJECT_ROOT / "paper" / "overleaf" / "images" / OUT_NAME,
)
TEST_OUTPUT = PROJECT_ROOT / ".tmp" / "cluster_diag" / "fig_gauge_network_test.png"


def _thousands(n: int) -> str:
    """Copernicus number style: no separator below 10 000, thin space above."""
    return str(n) if n < 10_000 else f"{n:,}".replace(",", " ")


def _size_label(category: str) -> str:
    """Turn a size-category string such as '(b) 100 - 2 000 $km^2$' into '100–2000'."""
    body = category.split(") ", 1)[-1].replace("$km^2$", "")
    nums = [int(x.replace(" ", "")) for x in re.findall(r"\d[\d ]*\d|\d", body)]
    if "<" in body:
        return f"< {_thousands(nums[0])}"
    if ">" in body:
        return f"> {_thousands(nums[0])}"
    return f"{_thousands(nums[0])}–{_thousands(nums[1])}"


def classify_catchments() -> pd.Series:
    """Köppen-Geiger class per catchment from the released forcing climatology.

    Returns:
        Series indexed by ``gauge_id`` (string) with the class label, ``""`` where the
        forcing is incomplete. Also written to ``results/koppen_classes.csv``.
    """
    ds = open_release_dataset(FORCING_NC)
    t = ds["temp_mean"].groupby("time.month").mean("time").transpose("gauge_id", "month").to_pandas()
    p_month = ds["precip_mswep"].resample(time="1MS").sum(min_count=1)
    p = p_month.groupby("time.month").mean("time").transpose("gauge_id", "month").to_pandas()

    kg = pd.Series(
        {str(gid): classify_koppen(t.loc[gid].to_numpy(), p.loc[gid].to_numpy()) for gid in t.index},
        name="kg",
    )
    KG_CSV.parent.mkdir(parents=True, exist_ok=True)
    kg.rename_axis("gauge_id").to_csv(KG_CSV)
    print(f"Köppen-Geiger classes written: {KG_CSV} ({int((kg != '').sum())} classified)")
    return kg


def load_data() -> tuple[gpd.GeoDataFrame, pd.Series]:
    """Load watersheds and gauges scoped to the Analysis set, with climate classes.

    Returns:
        Gauge points carrying a ``kg`` column, and the catchment counts per size category.
    """
    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws.set_index("gauge_id", inplace=True)
    ws.index = ws.index.astype(str)

    gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
    gauge.set_index("gauge_id", inplace=True)
    gauge.index = gauge.index.astype(str)

    release_scope = paper_analysis_scope_summary(ws.index)
    ws = filter_paper_analysis_index(ws)
    gauge = filter_paper_analysis_index(gauge)
    print(f"Total release watersheds: {release_scope.n_total}")
    print(f"Analysis-set watersheds:  {len(ws)} (excluded: {release_scope.n_excluded})")

    gauge["kg"] = gauge.index.map(classify_catchments()).fillna("")

    counts = gauge["kg"].value_counts()
    print("\n=== Köppen-Geiger classes (Analysis set) ===")
    for cls, cnt in counts.items():
        print(f"  {cls or 'unclassified'}: {cnt} ({cnt / len(gauge) * 100:.1f}%)")

    ws["size_category"] = ws["area_km2"].apply(categorize_catchment_size)
    ws["size_category"] = pd.Categorical(ws["size_category"], categories=get_size_categories())
    size_counts = ws["size_category"].value_counts(sort=False)
    print("\n=== Watershed Size Distribution ===")
    for cat, cnt in size_counts.items():
        print(f"  {cat}: {cnt} ({cnt / len(ws) * 100:.1f}%)")

    return gauge, size_counts


def _hero_background(ax: plt.Axes, aea: ccrs.Projection) -> None:
    """Hillshade + major-river backdrop for the hero map (CAMELS-CH/FR convention).

    Only Fig. 1 gets this treatment; every repeated attribute/signature map keeps the
    flat gray silhouette, matching the hero/small-multiple split used by CAMELS-FR and
    LamaH-CE. The MERIT mosaic (253 tiles, decimated to 0.05 deg/px) and the RiverATLAS
    extract are cached in .tmp/ — delete the cache files to force a rebuild.
    """
    from matplotlib.colors import LightSource
    import numpy as np
    import pyogrio
    import rasterio

    # Bounds aligned to the 5-degree MERIT tile grid so every tile lands whole
    lon0, lon1, lat0, lat1 = 15, 180, 40, 85
    cache = PROJECT_ROOT / ".tmp"
    cache.mkdir(exist_ok=True)

    dem_npz = cache / "hero_dem_0p05.npz"
    if dem_npz.exists():
        z = np.load(dem_npz)["z"]
    else:
        px = 100  # each 5-degree MERIT tile decimated to 100 px -> 0.05 deg/px
        z = np.full(((lat1 - lat0) * 20, (lon1 - lon0) * 20), np.nan, dtype="float32")
        rasters = PROJECT_ROOT / "data/World/SpatialData/merit_global/adjusted_elevation/rasters"
        for f in sorted(rasters.glob("n*_elv.tif")):
            m = re.search(r"n(\d+)e(\d+)", f.name)
            if m is None:
                continue
            tlat, tlon = int(m.group(1)), int(m.group(2))
            if not (lat0 <= tlat < lat1 and lon0 <= tlon < lon1):
                continue
            with rasterio.open(f) as src:
                a = src.read(1, out_shape=(px, px)).astype("float32")
            a[a < -100] = np.nan  # MERIT nodata (ocean)
            row0 = (lat1 - (tlat + 5)) * 20
            col0 = (tlon - lon0) * 20
            z[row0 : row0 + px, col0 : col0 + px] = a
        np.savez_compressed(dem_npz, z=z)

    # vert_exag tuned visually: 5 was invisible at print scale, 15 keeps the plains
    # light while making the eastern ranges read at \textwidth
    shade = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(z, nan=0.0), vert_exag=15.0, dx=2800.0, dy=5500.0
    )
    ax.imshow(
        np.ma.masked_where(np.isnan(z), shade),
        extent=(lon0, lon1, lat0, lat1),
        transform=ccrs.PlateCarree(),
        origin="upper",
        cmap="gray",
        vmin=0.0,
        vmax=1.0,
        alpha=0.45,
        zorder=1.05,
        interpolation="bilinear",
        regrid_shape=1200,
    )

    rivers_gpkg = cache / "hero_rivers.gpkg"
    if rivers_gpkg.exists():
        rivers = gpd.read_file(rivers_gpkg)
    else:
        rivers = pyogrio.read_dataframe(
            str(PROJECT_ROOT / "data/World/SpatialData/HydroSheds/RiverATLAS_v10.gdb"),
            layer="RiverATLAS_v10",
            columns=["UPLAND_SKM"],
            where="UPLAND_SKM >= 25000",
            bbox=(lon0, lat0, lon1, lat1),
        )
        rivers.to_file(rivers_gpkg, driver="GPKG")
    rivers.to_crs(aea.proj4_init).plot(ax=ax, color="#5b8cb8", linewidth=0.45, alpha=0.6, zorder=1.2)


def _scale_bar(ax: plt.Axes, length_km: float = 1000.0, fontsize: int = 8) -> None:
    """Corner scale bar in projected meters; approximate on an equal-area conic.

    Hero map only (CAMELS-CH/FR/LamaH precedent). No north arrow: on a conic spanning
    165 degrees of longitude, north varies visibly across the map, so a single arrow
    would be wrong — the meridian lines carry that information.
    """
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    x0 = xlim[0] + 0.04 * (xlim[1] - xlim[0])
    y0 = ylim[0] + 0.06 * (ylim[1] - ylim[0])
    length_m = length_km * 1000.0
    tick = 0.012 * (ylim[1] - ylim[0])
    ax.plot([x0, x0 + length_m], [y0, y0], color="black", lw=1.6, solid_capstyle="butt", zorder=6)
    for x in (x0, x0 + length_m):
        ax.plot([x, x], [y0 - tick, y0 + tick], color="black", lw=1.2, zorder=6)
    ax.text(
        x0 + length_m / 2,
        y0 + tick * 1.6,
        f"{int(length_km)} km",
        ha="center",
        va="bottom",
        fontsize=fontsize,
        zorder=6,
    )


def build_figure(
    gauge: gpd.GeoDataFrame, size_counts: pd.Series, support_dir: Path | None = None
) -> plt.Figure:
    """Assemble the two-panel study-area figure.

    Args:
        gauge: Analysis-set gauge points with a ``kg`` column.
        size_counts: Catchment counts per ordered size category.
        support_dir: Cell-support output directory; defaults to the temporary preview folder.

    Returns:
        The assembled matplotlib Figure (caller saves/closes it).
    """
    if support_dir is None:
        support_dir = TEST_OUTPUT.parent / "hex_support"
    aea = get_russia_projection()
    data_crs = ccrs.PlateCarree()

    fig = plt.figure(figsize=(6.3, 4.9), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.35, 1], width_ratios=[1, 1.6], hspace=0.12)
    ax_map = fig.add_subplot(gs[0, :], projection=aea)
    ax_legend = fig.add_subplot(gs[1, 0])
    ax_hist = fig.add_subplot(gs[1, 1])
    ax_legend.axis("off")

    ax_map.axis("off")
    _set_extent_from_data(ax_map, gauge, pad=0.04)  # tighter than the 0.08 default
    # The aspect-locked GeoAxes is height-bound, so constrained_layout centers it
    # vertically in its cell and its title sags below panel (b)'s; anchoring north
    # aligns both panel tops and frees the space below the map for the legend.
    ax_map.set_anchor("N")
    from src.plots.paper_maps import _add_graticule

    _add_graticule(ax_map)
    # Sparse labels give geographic orientation without crowding the climate map.
    for lon, lat, label in (
        (40, 44, "40°E"),
        (100, 50, "100°E"),
        (160, 52, "160°E"),
        (22, 60, "60°N"),
        (70, 75, "75°N"),
    ):
        ax_map.text(
            lon,
            lat,
            label,
            transform=data_crs,
            fontsize=8,
            color="#555555",
            ha="center",
            zorder=5,
            bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none", "pad": 1},
        )
    ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    if ne_land.crs is None:
        raise ValueError("Land background requires a CRS")
    ne_land.to_crs(aea.proj4_init).plot(
        ax=ax_map, color="#B7B7B7", edgecolor="#777777", linewidth=0.3, zorder=1
    )
    _hero_background(ax_map, aea)
    _scale_bar(ax_map)

    counts = gauge["kg"].value_counts()
    # Classes with MERGE_MAX or fewer catchments merge into a grey "other" class:
    # preserve the established display categories before cell aggregation; dropping the
    # rare hues keeps the remaining palette legible (round-6 editor m7).
    rare = {c for c in counts.index if c and counts[c] <= MERGE_MAX}
    gauge = gauge.copy()
    gauge.loc[gauge["kg"].isin(rare), "kg"] = "other"
    counts = gauge["kg"].value_counts()
    classes = [c for c in KG_COLORS if c in counts.index]
    classes += sorted(c for c in counts.index if c and c != "other" and c not in KG_COLORS)
    if "other" in counts.index:
        classes.append("other")
    # Aggregate categorical labels without converting classes into numeric scores.
    plotted = gauge.copy()
    plotted["kg"] = plotted["kg"].where(plotted["kg"].ne(""))
    categories = sorted(classes)
    cells = aggregate_hex(plotted, "kg", aea.proj4_init, categories=categories)
    cells.plot(
        ax=ax_map,
        color=[KG_COLORS.get(value, FALLBACK_COLOR) for value in cells["value"]],
        edgecolor="#454545",
        linewidth=0.25,
        zorder=3,
    )
    export_hex_support(
        plotted, "kg", cells, aea.proj4_init,
        support_dir / "network_climate.json",
        categories=categories,
    )
    unclassified = gauge[gauge["kg"] == ""]

    handles = [
        Line2D(
            [],
            [],
            marker="h",
            linestyle="None",
            markersize=6,
            markerfacecolor=KG_COLORS.get(cls, FALLBACK_COLOR),
            markeredgecolor="none",
            label=f"{cls} (n={int(counts[cls])})",
        )
        for cls in classes
    ]
    if not unclassified.empty:
        handles.append(
            Line2D(
                [],
                [],
                marker="h",
                linestyle="None",
                markersize=4,
                markerfacecolor=FALLBACK_COLOR,
                markeredgecolor="none",
                label=f"no class (n={len(unclassified)})",
            )
        )
    ax_legend.legend(
        handles=handles,
        loc="upper left",
        fontsize=8,
        frameon=False,
        ncol=1,
        handletextpad=0.4,
        title="Gauge counts by climate class",
        title_fontsize=9,
    )
    ax_map.set_title(
        f"(a) Most frequent climate class ({len(cells)} cells)",
        fontsize=9, fontweight="normal", loc="left", pad=7,
    )

    # (b) Catchment size distribution
    bars = ax_hist.barh(
        range(len(size_counts)),
        size_counts.values,
        color="#4477AA",
        edgecolor="black",
        linewidth=0.5,
    )
    ax_hist.set_yticks(range(len(size_counts)))
    ax_hist.set_yticklabels([_size_label(str(cat)) for cat in size_counts.index], fontsize=8)
    ax_hist.set_ylabel("Catchment area (km²)", fontsize=8)
    ax_hist.set_xlabel("Number of catchments", fontsize=8)
    ax_hist.set_title("(b) Size distribution", fontsize=9, fontweight="normal", loc="left", pad=7)
    ax_hist.grid(alpha=0.15, axis="x", linestyle="--")
    ax_hist.spines[["top", "right"]].set_visible(False)
    ax_hist.invert_yaxis()
    # Leave room for the exact count to the right of the longest bar.
    ax_hist.set_xlim(0, float(size_counts.max()) * 1.3)
    ax_hist.set_xticks([0, 500, 1000, 1500])
    for bar, cnt in zip(bars, size_counts.values, strict=False):
        ax_hist.text(
            cnt + 20,
            bar.get_y() + bar.get_height() / 2,
            f"{cnt}",
            va="center",
            fontsize=8,
            fontweight="normal",
        )

    return fig


def main() -> None:
    """Parse CLI args, build the figure, and write it to the chosen path(s)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to paper/images and paper/overleaf/images (else a .tmp test path).",
    )
    args = parser.parse_args()

    gauge, size_counts = load_data()
    support_dir = (
        PROJECT_ROOT / "paper/figure_data/hex_support"
        if args.write else TEST_OUTPUT.parent / "hex_support"
    )
    fig = build_figure(gauge, size_counts, support_dir)
    # Save once and copy so both manuscript image trees are byte-identical.
    outputs = PAPER_OUTPUTS if args.write else (TEST_OUTPUT,)
    first = outputs[0]
    first.parent.mkdir(parents=True, exist_ok=True)
    # Resolve the layout at delivery DPI before freezing its physical dimensions.
    fig.set_dpi(400)
    fig.canvas.draw()
    fig.set_layout_engine("none")
    fig.savefig(first, dpi=400, facecolor="white")
    print(f"\nSaved: {first}")
    for out in outputs[1:]:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first, out)
        print(f"Copied: {out}")
    plt.close(fig)


if __name__ == "__main__":
    main()
