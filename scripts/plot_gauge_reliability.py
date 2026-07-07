"""Render the gauge-reliability map (Section 4): per-gauge share of grade-A years.

For every graded discharge gauge, we compute the fraction of its assessed
hydrological years that received grade A, then plot the gauges on the same
Albers Equal-Area map and Natural Earth basemap as the Section 2 network figure.
The Section 2 map shows each gauge's single overall grade; this map shows how
consistently reliable each gauge is across the record, which the overall grade
(dominated by the worst year under the strict rule) cannot convey.

The reliability is derived from the released ``camels_ru_year_grades.csv`` so the
figure reproduces from the archive alone.

Usage:
    pixi run python scripts/plot_gauge_reliability.py            # test output (.tmp)
    pixi run python scripts/plot_gauge_reliability.py --write    # paper output
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import warnings

import cartopy.crs as ccrs
import geopandas as gpd
from matplotlib.colors import BoundaryNorm, ListedColormap
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.plots.paper_maps import (  # noqa: E402
    _set_extent_from_data,
    get_russia_projection,
)
from src.utils.paper_analysis_scope import (  # noqa: E402
    filter_paper_analysis_index,
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
    }
)

DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
GEOM_DIR = DATA_DIR / "geometry"
GRADES_CSV = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_year_grades.csv"
OUT_NAME = "fig_gauge_reliability.png"
PAPER_OUTPUTS = (
    PROJECT_ROOT / "paper" / "images" / OUT_NAME,
    PROJECT_ROOT / "paper" / "overleaf" / "images" / OUT_NAME,
)
TEST_OUTPUT = PROJECT_ROOT / ".tmp" / "cluster_diag" / "fig_gauge_reliability_test.png"

# Discrete reliability classes on the share of grade-A years. Bin edges are equal
# 20-point bands; the five colours reuse the Section 2 grade palette exactly
# (F red -> A dark green) so the two quality figures read as one visual language.
BOUNDS = [0, 20, 40, 60, 80, 100]
BIN_COLORS = ["#d73027", "#fc8d59", "#fee08b", "#91cf60", "#1a9850"]
BIN_LABELS = ["0-20", "20-40", "40-60", "60-80", "80-100"]


def load_reliability() -> gpd.GeoDataFrame:
    """Load gauge points and attach the per-gauge share of grade-A years.

    Returns:
        Paper-analysis gauge points that carry at least one assessed year, with a
        ``pct_a`` column (0-100) and an ``n_assessed`` column.
    """
    gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
    gauge.set_index("gauge_id", inplace=True)
    gauge.index = gauge.index.astype(str)
    gauge = filter_paper_analysis_index(gauge)

    grades = pd.read_csv(GRADES_CSV, dtype=str).set_index("gauge_id")
    grades.index = grades.index.astype(str)
    year_cols = [c for c in grades.columns if c.isdigit()]
    grades = grades[year_cols]

    n_assessed = grades.notna().sum(axis=1)
    n_a = (grades == "A").sum(axis=1)
    graded = n_assessed > 0
    pct_a = pd.Series(np.nan, index=grades.index)
    pct_a[graded] = 100.0 * n_a[graded] / n_assessed[graded]

    gauge["pct_a"] = gauge.index.map(pct_a)
    gauge["n_assessed"] = gauge.index.map(n_assessed)
    gauge = gauge[gauge["pct_a"].notna()].copy()

    print(f"graded gauges plotted: {len(gauge)}")
    print(f"median share of A years: {gauge['pct_a'].median():.1f}%")
    print(f"gauges at 100% A: {(gauge['pct_a'] >= 100).sum()}")
    print(f"gauges at 0% A:   {(gauge['pct_a'] <= 0).sum()}")
    return gauge


def build_figure(gauge: gpd.GeoDataFrame) -> plt.Figure:
    """Assemble the single-panel reliability map.

    Args:
        gauge: Gauge points carrying ``pct_a`` (share of grade-A years).

    Returns:
        The assembled matplotlib Figure (caller saves/closes it).
    """
    aea = get_russia_projection()
    data_crs = ccrs.PlateCarree()

    fig = plt.figure(figsize=(9.5, 6.0), constrained_layout=True)
    ax_map = fig.add_subplot(1, 1, 1, projection=aea)
    ax_map.axis("off")
    _set_extent_from_data(ax_map, gauge)

    ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    ne_land.to_crs(aea.proj4_init).plot(
        ax=ax_map, color="#EDEDED", edgecolor="#CCCCCC", linewidth=0.3, zorder=1
    )

    cmap = ListedColormap(BIN_COLORS)
    norm = BoundaryNorm(BOUNDS, cmap.N)

    # Draw least-reliable gauges last so they stay visible on the dense cluster.
    gauge = gauge.sort_values("pct_a", ascending=False)
    sc = ax_map.scatter(
        gauge.geometry.x,
        gauge.geometry.y,
        c=gauge["pct_a"],
        cmap=cmap,
        norm=norm,
        s=20,
        alpha=0.95,
        edgecolors="#333333",
        linewidths=0.2,
        zorder=3,
        transform=data_crs,
    )

    cbar = fig.colorbar(
        sc,
        ax=ax_map,
        orientation="horizontal",
        boundaries=BOUNDS,
        ticks=BOUNDS,
        spacing="uniform",
        drawedges=True,
        shrink=0.62,
        pad=0.02,
        aspect=30,
    )
    cbar.set_label("Share of assessed years graded A (%)", fontsize=11)
    cbar.dividers.set_color("white")
    cbar.dividers.set_linewidth(1.5)

    ax_map.text(
        0.01,
        0.02,
        f"n = {len(gauge):,} graded gauges",
        transform=ax_map.transAxes,
        fontsize=9,
        va="bottom",
        ha="left",
    )
    return fig


def main() -> None:
    """Parse CLI args, build the reliability map, and write it out."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to paper/images and paper/overleaf/images (else a .tmp test path).",
    )
    args = parser.parse_args()

    gauge = load_reliability()
    fig = build_figure(gauge)

    outputs = PAPER_OUTPUTS if args.write else (TEST_OUTPUT,)
    for out in outputs:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=300, bbox_inches="tight")
        print(f"wrote {out}")
    plt.close(fig)


if __name__ == "__main__":
    main()
