"""Render the discharge-quality figure (Section 4): overall grade and per-gauge reliability.

Two stacked Albers maps of the discharge gauges of the Analysis set:
(a) the overall A-F grade of every discharge gauge (ungraded gauges in grey), from
    the released ``camels_ru_gauge_summary.csv``;
(b) the share of assessed hydrological years graded A, from the released
    ``camels_ru_year_grades.csv``, in five 20-point classes that reuse the grade palette.

Panel (a) gives the single grade users filter on; panel (b) shows how consistently
reliable each record is, which the overall grade (dominated by the worst year under the
strict rule) cannot convey. Both panels reproduce from the archive plus the gauge-point
layer used by every other map script.

Usage:
    pixi run python scripts/plot_gauge_reliability.py            # test output (.tmp)
    pixi run python scripts/plot_gauge_reliability.py --write    # paper output
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import warnings

import cartopy.crs as ccrs
import geopandas as gpd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

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

GEOM_DIR = PROJECT_ROOT / "data" / "CAMELS_RU" / "geometry"
RELEASE = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0"
GRADES_CSV = RELEASE / "camels_ru_year_grades.csv"
SUMMARY_CSV = RELEASE / "camels_ru_gauge_summary.csv"
DISCHARGE_NC = RELEASE / "camels_ru_discharge.nc"
OUT_NAME = "fig_gauge_reliability.png"
PAPER_OUTPUTS = (
    PROJECT_ROOT / "paper" / "images" / OUT_NAME,
    PROJECT_ROOT / "paper" / "overleaf" / "images" / OUT_NAME,
)
TEST_OUTPUT = PROJECT_ROOT / ".tmp" / "cluster_diag" / "fig_gauge_reliability_test.png"

# Ordinal grade palette, shared by both panels. Sampled from viridis rather than the
# red-yellow-green ramp this figure used through v1.0: under deuteranopia the old grade A
# and grade F were near-indistinguishable, which defeats the point of the map. Grades are
# ordinal, so a sequential ramp is the correct encoding, and it runs the same direction as
# panel (b)'s colourbar (bright = more grade-A years).
GRADE_COLORS = {
    "A": "#dfe318",
    "B": "#4ec36b",
    "C": "#21918c",
    "D": "#375a8c",
    "F": "#440154",
    "ungraded": "#BBBBBB",
}
GRADE_ORDER = ["A", "B", "C", "D", "F", "ungraded"]

# Discrete reliability classes on the share of grade-A years: equal 20-point bands
# coloured with the same five grade colours (F red -> A dark green).
BOUNDS = [0, 20, 40, 60, 80, 100]
BIN_COLORS = [GRADE_COLORS[g] for g in ("F", "D", "C", "B", "A")]


def load_gauges() -> gpd.GeoDataFrame:
    """Discharge gauges of the Analysis set with ``grade`` and ``pct_a`` columns.

    Returns:
        Gauge points for every catchment that carries discharge observations, with the
        overall grade (``"ungraded"`` where none was assigned), the share of assessed
        years graded A (``pct_a``, NaN when ungraded), and ``n_assessed``.
    """
    gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
    gauge.set_index("gauge_id", inplace=True)
    gauge.index = gauge.index.astype(str)
    gauge = filter_paper_analysis_index(gauge)

    has_q = xr.open_dataset(DISCHARGE_NC)["discharge_m3s"].notnull().any("time").to_pandas()
    has_q.index = has_q.index.astype(str)
    gauge = gauge.loc[gauge.index.intersection(has_q[has_q].index)].copy()

    summary = pd.read_csv(SUMMARY_CSV, dtype=str).set_index("gauge_id")
    gauge["grade"] = gauge.index.map(summary["overall_grade"]).fillna("ungraded")

    grades = pd.read_csv(GRADES_CSV, dtype=str).set_index("gauge_id")
    year_cols = [c for c in grades.columns if c.isdigit()]
    grades = grades[year_cols]
    n_assessed = grades.notna().sum(axis=1)
    n_a = (grades == "A").sum(axis=1)
    pct_a = pd.Series(np.nan, index=grades.index)
    graded = n_assessed > 0
    pct_a[graded] = 100.0 * n_a[graded] / n_assessed[graded]
    gauge["pct_a"] = gauge.index.map(pct_a)
    gauge["n_assessed"] = gauge.index.map(n_assessed)

    print(f"discharge gauges plotted: {len(gauge)}")
    for grade, cnt in gauge["grade"].value_counts().reindex(GRADE_ORDER).items():
        print(f"  {grade}: {0 if pd.isna(cnt) else int(cnt)}")
    rel = gauge["pct_a"].dropna()
    print(f"graded gauges with reliability: {len(rel)}; median share of A years: {rel.median():.1f}%")
    print(f"gauges at 100% A: {int((rel >= 100).sum())}; at 0% A: {int((rel <= 0).sum())}")
    return gauge


def _basemap(ax: plt.Axes, gauge: gpd.GeoDataFrame, aea: ccrs.Projection) -> None:
    """Shared extent and Natural Earth landmass background for one panel.

    Args:
        ax: GeoAxes to draw on.
        gauge: Gauge points defining the shared extent.
        aea: Albers projection.
    """
    ax.axis("off")
    _set_extent_from_data(ax, gauge)
    from src.plots.paper_maps import _add_graticule

    _add_graticule(ax)
    ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    ne_land.to_crs(aea.proj4_init).plot(
        ax=ax, color="#EDEDED", edgecolor="#CCCCCC", linewidth=0.3, zorder=1
    )


def _panel_grades(ax: plt.Axes, gauge: gpd.GeoDataFrame, data_crs: ccrs.Projection) -> None:
    """Panel (a): overall grade per discharge gauge, worse grades drawn on top."""
    handles = []
    for rank, grade in enumerate(GRADE_ORDER):
        sub = gauge[gauge["grade"] == grade]
        if sub.empty:
            continue
        z = 2 if grade == "ungraded" else 3 + rank
        ax.scatter(
            sub.geometry.x,
            sub.geometry.y,
            s=14,
            alpha=0.85,
            c=GRADE_COLORS[grade],
            edgecolors="#333333",
            linewidths=0.15,
            zorder=z,
            transform=data_crs,
        )
        handles.append(
            Line2D(
                [],
                [],
                marker="o",
                linestyle="None",
                markersize=6,
                markerfacecolor=GRADE_COLORS[grade],
                markeredgecolor="#333333",
                markeredgewidth=0.3,
                label=f"{grade} (n={len(sub)})",
            )
        )
    ax.legend(
        handles=handles,
        loc="lower left",
        fontsize=8,
        framealpha=0.9,
        ncol=2,
        columnspacing=0.8,
        handletextpad=0.4,
    )
    ax.set_title("(a) Overall discharge grade", fontsize=13, fontweight="bold", loc="left")


def _panel_reliability(
    fig: plt.Figure, ax: plt.Axes, gauge: gpd.GeoDataFrame, data_crs: ccrs.Projection
) -> None:
    """Panel (b): share of assessed years graded A, five discrete classes."""
    graded = gauge[gauge["pct_a"].notna()].sort_values("pct_a", ascending=False)
    cmap = ListedColormap(BIN_COLORS)
    norm = BoundaryNorm(BOUNDS, cmap.N)
    # Least-reliable gauges drawn last so they stay visible on the dense cluster.
    sc = ax.scatter(
        graded.geometry.x,
        graded.geometry.y,
        c=graded["pct_a"],
        cmap=cmap,
        norm=norm,
        s=14,
        alpha=0.95,
        edgecolors="#333333",
        linewidths=0.15,
        zorder=3,
        transform=data_crs,
    )
    cbar = fig.colorbar(
        sc,
        ax=ax,
        orientation="horizontal",
        boundaries=BOUNDS,
        ticks=BOUNDS,
        spacing="uniform",
        drawedges=True,
        shrink=0.55,
        pad=0.02,
        aspect=30,
    )
    cbar.set_label("Share of assessed years graded A (%)", fontsize=10)
    cbar.dividers.set_color("white")
    cbar.dividers.set_linewidth(1.5)
    ax.text(
        0.01,
        0.02,
        f"n = {len(graded)} graded gauges",
        transform=ax.transAxes,
        fontsize=9,
        va="bottom",
        ha="left",
    )
    ax.set_title("(b) Share of assessed years graded A", fontsize=13, fontweight="bold", loc="left")


def build_figure(gauge: gpd.GeoDataFrame) -> plt.Figure:
    """Assemble the two-panel discharge-quality figure.

    Args:
        gauge: Discharge gauge points carrying ``grade`` and ``pct_a``.

    Returns:
        The assembled matplotlib Figure (caller saves/closes it).
    """
    aea = get_russia_projection()
    data_crs = ccrs.PlateCarree()
    fig, axes = plt.subplots(
        2, 1, figsize=(9.5, 9.2), subplot_kw={"projection": aea}, constrained_layout=True
    )
    _basemap(axes[0], gauge, aea)
    _basemap(axes[1], gauge, aea)
    _panel_grades(axes[0], gauge, data_crs)
    _panel_reliability(fig, axes[1], gauge, data_crs)
    return fig


def main() -> None:
    """Parse CLI args, build the quality figure, and write it out."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to paper/images and paper/overleaf/images (else a .tmp test path).",
    )
    args = parser.parse_args()

    gauge = load_gauges()
    fig = build_figure(gauge)
    outputs = PAPER_OUTPUTS if args.write else (TEST_OUTPUT,)
    first, *rest = outputs  # save once, copy: repeated tight saves differ by a few pixels
    first.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(first, dpi=300, bbox_inches="tight")
    print(f"wrote {first}")
    for out in rest:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first, out)
        print(f"wrote {out}")
    plt.close(fig)


if __name__ == "__main__":
    main()
