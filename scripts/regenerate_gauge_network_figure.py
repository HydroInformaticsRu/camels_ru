"""Regenerate the study-area figure (Section 2, Figure 1).

Two-panel layout: (a) Albers map of the Analysis-set catchments coloured by
Köppen-Geiger climate class, (b) horizontal bar chart of the catchment size
distribution.

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
import sys
import warnings

import cartopy.crs as ccrs
import geopandas as gpd
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.meteo.koppen import classify_koppen  # noqa: E402
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
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9,
    }
)

# Köppen-Geiger legend colours in the Peel et al. (2007) / Beck et al. (2018) convention;
# dict order is the canonical legend order.
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
    ds = xr.open_dataset(FORCING_NC)
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


def build_figure(gauge: gpd.GeoDataFrame, size_counts: pd.Series) -> plt.Figure:
    """Assemble the two-panel study-area figure.

    Args:
        gauge: Analysis-set gauge points with a ``kg`` column.
        size_counts: Catchment counts per ordered size category.

    Returns:
        The assembled matplotlib Figure (caller saves/closes it).
    """
    aea = get_russia_projection()
    data_crs = ccrs.PlateCarree()

    fig = plt.figure(figsize=(13.0, 4.4), constrained_layout=True)
    gs = fig.add_gridspec(1, 2, width_ratios=[2.7, 1])
    ax_map = fig.add_subplot(gs[0, 0], projection=aea)
    ax_hist = fig.add_subplot(gs[0, 1])

    ax_map.axis("off")
    _set_extent_from_data(ax_map, gauge)
    ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    ne_land.to_crs(aea.proj4_init).plot(
        ax=ax_map, color="#EDEDED", edgecolor="#CCCCCC", linewidth=0.3, zorder=1
    )

    counts = gauge["kg"].value_counts()
    classes = [c for c in KG_COLORS if c in counts.index]
    classes += sorted(c for c in counts.index if c and c not in KG_COLORS)
    # Draw the common classes first so the rare ones stay visible on top.
    for cls in sorted(classes, key=lambda c: -int(counts[c])):
        sub = gauge[gauge["kg"] == cls]
        ax_map.scatter(
            sub.geometry.x,
            sub.geometry.y,
            s=12,
            alpha=0.85,
            c=KG_COLORS.get(cls, FALLBACK_COLOR),
            edgecolors="none",
            zorder=3,
            transform=data_crs,
        )
    unclassified = gauge[gauge["kg"] == ""]
    if not unclassified.empty:
        ax_map.scatter(
            unclassified.geometry.x,
            unclassified.geometry.y,
            s=6,
            c=FALLBACK_COLOR,
            edgecolors="none",
            zorder=2,
            transform=data_crs,
        )

    handles = [
        Line2D(
            [],
            [],
            marker="o",
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
                marker="o",
                linestyle="None",
                markersize=4,
                markerfacecolor=FALLBACK_COLOR,
                markeredgecolor="none",
                label=f"no class (n={len(unclassified)})",
            )
        )
    ax_map.legend(
        handles=handles,
        loc="lower left",
        fontsize=8,
        framealpha=0.9,
        ncol=3,
        columnspacing=0.8,
        handletextpad=0.4,
        title="Köppen-Geiger class",
        title_fontsize=8,
    )
    ax_map.set_title("(a) Climate classes", fontsize=13, fontweight="bold", loc="left")

    # (b) Catchment size distribution
    bars = ax_hist.barh(
        range(len(size_counts)),
        size_counts.values,
        color="#4477AA",
        edgecolor="black",
        linewidth=0.5,
    )
    ax_hist.set_yticks(range(len(size_counts)))
    ax_hist.set_yticklabels([_size_label(str(cat)) for cat in size_counts.index], fontsize=10)
    ax_hist.set_ylabel("Catchment area (km²)", fontsize=11)
    ax_hist.set_xlabel("Number of catchments", fontsize=11)
    ax_hist.set_title("(b) Size distribution", fontsize=13, fontweight="bold", loc="left")
    ax_hist.grid(alpha=0.15, axis="x", linestyle="--")
    ax_hist.invert_yaxis()
    ax_hist.set_xlim(0, float(size_counts.max()) * 1.18)
    for bar, cnt in zip(bars, size_counts.values, strict=False):
        ax_hist.text(
            cnt + 20,
            bar.get_y() + bar.get_height() / 2,
            f"{cnt}",
            va="center",
            fontsize=10,
            fontweight="bold",
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
    fig = build_figure(gauge, size_counts)
    outputs = PAPER_OUTPUTS if args.write else (TEST_OUTPUT,)
    for out in outputs:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=300, bbox_inches="tight")
        print(f"\nSaved: {out}")
    plt.close(fig)


if __name__ == "__main__":
    main()
