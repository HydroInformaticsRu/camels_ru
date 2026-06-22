"""Regenerate the CAMELS-RU gauge-network figure (Section 2, Figure 1).

Standalone port of the gauge-network figure from ``notebooks/00_DataDescription.py``
(two-panel layout: (a) Albers map of paper-analysis gauges coloured by discharge
quality grade, (b) horizontal bar chart of catchment size distribution).

The only design change versus the notebook is the grade colour palette: the old
Paul-Tol blue/cyan ramp made grades A and B nearly indistinguishable, so this
script uses an intuitive ordinal green-to-red ramp (A dark green -> F red, with
grey for ungraded). Panel (b) still encodes catchment size (a different variable)
and keeps its single-colour bars.

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
import sys
import warnings

import cartopy.crs as ccrs
import geopandas as gpd
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.plots.paper_maps import (  # noqa: E402
    _set_extent_from_data,
    get_russia_projection,
)
from src.static.hydro_atlas_analysis import (  # noqa: E402
    categorize_catchment_size,
    get_size_categories,
)
from src.utils.paper_analysis_scope import (  # noqa: E402
    PAPER_ANALYSIS_EXCLUDED_MIN_ID_LENGTH,
    PAPER_ANALYSIS_EXCLUSION_NOTE,
    filter_paper_analysis_index,
    paper_analysis_scope_summary,
)

gpd.options.io_engine = "pyogrio"
warnings.simplefilter(action="ignore", category=FutureWarning)

# ── Style (matches the notebook serif rcParams) ──────────────────────────────
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

# ── Grade palette (ordinal green -> red; the single design change) ───────────
# Replaces the old Paul-Tol blue/cyan/yellow/pink ramp where A and B were almost
# indistinguishable. Better grades are intuitively green, worse grades red.
GRADE_COLORS = {
    "A": "#1a9850",  # dark green
    "B": "#91cf60",  # light green
    "C": "#fee08b",  # amber
    "D": "#fc8d59",  # orange
    "F": "#d73027",  # red
    "ungraded": "#BBBBBB",  # grey
}
GRADE_ORDER = ["A", "B", "C", "D", "F", "ungraded"]
HYDRO_ID_MIN_LEN = PAPER_ANALYSIS_EXCLUDED_MIN_ID_LENGTH

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
COMPOUND_DIR = DATA_DIR / "HydroData" / "Compound"
GEOM_DIR = DATA_DIR / "geometry"
PAPER_OUTPUT = PROJECT_ROOT / "paper" / "images" / "fig_gauge_network.png"
TEST_OUTPUT = PROJECT_ROOT / ".tmp" / "cluster_diag" / "fig_gauge_network_test.png"


def load_data() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.Series[int]]:
    """Load watersheds, gauges, and grades scoped to the paper analysis set.

    Returns:
        Tuple of (gauge points with grade + hydropower flag, watershed scope
        summary count container is not returned; instead returns the gauge
        GeoDataFrame, the size-bin counts Series, and the per-grade counts).
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

    quality_df = pd.read_csv(COMPOUND_DIR / "quality_summary.csv")
    quality_df["gauge_id"] = quality_df["gauge_id"].astype(str)
    quality_df.set_index("gauge_id", inplace=True)

    gauge["grade"] = gauge.index.map(
        lambda gid: (
            quality_df.loc[gid, "overall_grade"]
            if gid in quality_df.index and pd.notna(quality_df.loc[gid, "overall_grade"])
            else "ungraded"
        )
    )
    gauge["is_hydropower"] = gauge.index.str.len() >= HYDRO_ID_MIN_LEN

    print(f"Total release watersheds: {release_scope.n_total}")
    print(f"Paper-analysis watersheds: {len(ws)}")
    print(f"Paper-analysis gauges:     {len(gauge)}")
    print(
        f"Gauge-ID excluded from paper analyses (ID>={HYDRO_ID_MIN_LEN} chars): "
        f"{release_scope.n_excluded}"
    )
    print(PAPER_ANALYSIS_EXCLUSION_NOTE)

    grade_counts = gauge["grade"].value_counts().reindex(GRADE_ORDER)
    print("\n=== Grade Distribution ===")
    for grade, count in grade_counts.items():
        safe = 0 if pd.isna(count) else int(count)
        print(f"  {grade}: {safe} ({safe / len(gauge) * 100:.1f}%)")

    ws["size_category"] = ws["area_km2"].apply(categorize_catchment_size)
    ws["size_category"] = pd.Categorical(ws["size_category"], categories=get_size_categories())
    size_counts = ws["size_category"].value_counts(sort=False)

    print("\n=== Watershed Size Distribution ===")
    for cat, cnt in size_counts.items():
        print(f"  {cat}: {cnt} ({cnt / len(ws) * 100:.1f}%)")

    return gauge, size_counts, grade_counts


def build_figure(gauge: gpd.GeoDataFrame, size_counts: pd.Series[int]) -> plt.Figure:
    """Assemble the two-panel gauge-network figure.

    Args:
        gauge: Paper-analysis gauge points with ``grade`` and ``is_hydropower``.
        size_counts: Catchment counts per ordered size category.

    Returns:
        The assembled matplotlib Figure (caller saves/closes it).
    """
    aea = get_russia_projection()
    data_crs = ccrs.PlateCarree()

    fig = plt.figure(figsize=(14.0, 5.5), constrained_layout=True)
    gs = fig.add_gridspec(1, 2, width_ratios=[2.2, 1])
    ax_map = fig.add_subplot(gs[0, 0], projection=aea)
    ax_hist = fig.add_subplot(gs[0, 1])

    ax_map.axis("off")
    _set_extent_from_data(ax_map, gauge)

    # Natural Earth landmass background (no political borders)
    ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    ne_land.to_crs(aea.proj4_init).plot(
        ax=ax_map, color="#EDEDED", edgecolor="#CCCCCC", linewidth=0.3, zorder=1
    )

    # (a) Gauge locations by grade — worse grades drawn last so they stay
    # visible on the dense European-Russia cluster.  Iterating in reverse
    # (ungraded -> A) means A is plotted last; to keep worse-on-top we instead
    # plot best first and worst last, then assign zorder by ordinal rank.
    n_grades = len(GRADE_ORDER)
    for rank, grade in enumerate(GRADE_ORDER):
        subset = gauge[gauge["grade"] == grade]
        if len(subset) == 0:
            continue
        regular = subset[~subset["is_hydropower"]]
        hydro = subset[subset["is_hydropower"]]
        # Higher rank (worse grade) -> higher zorder, so worse plots on top.
        # ungraded is the background layer regardless.
        base_z = 2 if grade == "ungraded" else 3 + (n_grades - rank)

        if len(regular) > 0:
            ax_map.scatter(
                regular.geometry.x,
                regular.geometry.y,
                s=12,
                alpha=0.65,
                c=GRADE_COLORS[grade],
                label=f"{grade} (n={len(subset)})",
                edgecolors="none",
                zorder=base_z,
                transform=data_crs,
            )
        if len(hydro) > 0:
            ax_map.scatter(
                hydro.geometry.x,
                hydro.geometry.y,
                s=24,
                alpha=0.85,
                c=GRADE_COLORS[grade],
                marker="^",
                edgecolors="black",
                linewidths=0.4,
                zorder=base_z + n_grades,
                transform=data_crs,
            )

    ax_map.set_title("(a) Gauge network", fontsize=13, fontweight="bold", loc="left")

    # Legend ordered Grade A first; legend handles come from the scatter labels
    # which are appended in GRADE_ORDER, so no reversal is needed here.
    handles, labels = ax_map.get_legend_handles_labels()
    order = {f"{g} (n=": i for i, g in enumerate(GRADE_ORDER)}

    def _rank(label: str) -> int:
        for key, idx in order.items():
            if label.startswith(key):
                return idx
        return len(order)

    pairs = sorted(zip(handles, labels, strict=True), key=lambda hl: _rank(hl[1]))
    all_handles = [h for h, _ in pairs]
    all_labels = [label for _, label in pairs]

    n_hydro_in_scope = int(gauge["is_hydropower"].sum())
    if n_hydro_in_scope:
        hp_handle = Line2D(
            [],
            [],
            marker="^",
            color="none",
            markerfacecolor="#888888",
            markeredgecolor="black",
            markersize=6,
            linestyle="None",
            label=f"Hydropower (n={n_hydro_in_scope})",
        )
        all_handles.append(hp_handle)
        all_labels.append(hp_handle.get_label())

    ax_map.legend(
        all_handles,
        all_labels,
        loc="lower left",
        fontsize=8,
        framealpha=0.9,
        markerscale=2.0,
        ncol=2,
        columnspacing=0.8,
        handletextpad=0.4,
    )

    # (b) Catchment size distribution (horizontal bars; encodes size, not grade)
    clean_labels = [cat.split(") ")[1].replace("$km^2$", "km²") for cat in size_counts.index]
    bars = ax_hist.barh(
        range(len(size_counts)),
        size_counts.values,
        color="#4477AA",
        edgecolor="black",
        linewidth=0.5,
    )
    ax_hist.set_yticks(range(len(size_counts)))
    ax_hist.set_yticklabels(clean_labels, fontsize=10)
    ax_hist.set_xlabel("Number of catchments", fontsize=12)
    ax_hist.set_title("(b) Size distribution", fontsize=13, fontweight="bold", loc="left")
    ax_hist.grid(alpha=0.15, axis="x", linestyle="--")
    ax_hist.invert_yaxis()

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
    """Parse CLI args, build the figure, and write it to the chosen path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to paper/images/fig_gauge_network.png (else a .tmp test path).",
    )
    args = parser.parse_args()

    gauge, size_counts, grade_counts = load_data()
    fig = build_figure(gauge, size_counts)

    out_path = PAPER_OUTPUT if args.write else TEST_OUTPUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"\nSaved: {out_path}")
    print("\n=== Per-grade counts (for caption verification) ===")
    for grade in GRADE_ORDER:
        count = grade_counts.get(grade)
        safe = 0 if pd.isna(count) else int(count)
        print(f"  {grade}: {safe}")
    print("\n=== Size-bin counts (for caption verification) ===")
    for cat, cnt in size_counts.items():
        print(f"  {cat}: {int(cnt)}")


if __name__ == "__main__":
    main()
