"""Render the four hydrological-signature map figures (Section 5) from the release.

Reads the released ``camels_ru_signatures.csv``, drops the small-basin anomalies flagged
``is_anomalous``, and summarizes eight key signatures by 66-km-radius hex-cell medians on the
shared Albers Equal-Area basemap. The bin edges and panel order follow the original
notebook-02 maps; the gauge set is now the released cleaned subset, so the figures
reproduce from the archive plus the gauge-point layer used by every other map script.

Each figure holds two panels stacked vertically (one column) so every panel prints at
full text width (ESSD editor round-N re-review: the previous 2x2-panel figures rendered
too small to read).

Usage:
    pixi run python scripts/plot_signature_maps.py            # test output (.tmp)
    pixi run python scripts/plot_signature_maps.py --write    # paper output
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import warnings

import geopandas as gpd
from matplotlib.colors import BoundaryNorm, to_rgba
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.plots.hex_maps import aggregate_hex, export_hex_support  # noqa: E402
from src.plots.paper_maps import (  # noqa: E402
    _add_graticule,
    _class_counts,
    _format_edge_labels,
    _set_extent_from_data,
    get_russia_projection,
)
from src.utils.paper_analysis_scope import filter_paper_analysis_index  # noqa: E402

gpd.options.io_engine = "pyogrio"
warnings.simplefilter(action="ignore", category=FutureWarning)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "pdf.fonttype": 42,
    }
)

GEOM_DIR = PROJECT_ROOT / "data" / "CAMELS_RU" / "geometry"
SIGNATURES_CSV = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_signatures.csv"
PAPER_DIRS = (PROJECT_ROOT / "paper" / "images", PROJECT_ROOT / "paper" / "overleaf" / "images")
TEST_DIR = PROJECT_ROOT / ".tmp" / "cluster_diag"

# (release column, panel title, bin edges) in figure order; bins as in notebooks/02.
PANELS_1 = [
    ("q_mean", "Mean discharge (mm d$^{-1}$)", [0, 0.3, 0.6, 1.0, 1.5, 2.5, 5.0, 8.0]),
    (
        "q95",
        "Low flow: 5th percentile (95% exceedance; mm d$^{-1}$)",
        [0, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0, 2.5],
    ),
]
PANELS_2 = [
    ("q05", "High flow: 95th percentile (5% exceedance; mm d$^{-1}$)", [0, 1, 3, 5, 7, 10, 15, 20]),
    ("baseflow_index", "Baseflow index", [0.2, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85]),
]
PANELS_3 = [
    (
        "half_flow_date",
        # Not "DOY": under a calendar day-of-year reading the 120-270 classes look like
        # Apr-Sep instead of the intended late-Jan to late-Jun of the 1-Oct year.
        "Mean half-flow date (day of hydrological year)",
        [120, 150, 180, 200, 220, 240, 270],
    ),
    ("fdc_slope", "FDC slope", [0, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 15.0]),
]
PANELS_4 = [
    ("high_flow_freq", "High-flow frequency (%)", [0, 10, 15, 20, 25, 30, 40, 50]),
    ("low_flow_freq", "Low-flow frequency (%)", [0, 2, 5, 10, 20, 35, 50, 70]),
]


def load_signatures() -> gpd.GeoDataFrame:
    """Gauge points of the released cleaned signature set with the signature columns attached."""
    sig = pd.read_csv(SIGNATURES_CSV, dtype={"gauge_id": str}).set_index("gauge_id")
    n_all = len(sig)
    sig = sig[~sig["is_anomalous"].astype(bool)]
    print(f"signature rows: {n_all}, cleaned (is_anomalous dropped): {len(sig)}")

    gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg").set_index("gauge_id")
    gauge.index = gauge.index.astype(str)
    gauge = filter_paper_analysis_index(gauge)
    missing = sig.index.difference(gauge.index)
    if len(missing):
        raise RuntimeError(f"{len(missing)} signature gauges lack a point geometry: {list(missing)[:5]}")

    cols = [c for c, _, _ in PANELS_1 + PANELS_2 + PANELS_3 + PANELS_4]
    gdf = gauge.loc[sig.index].join(sig[cols])
    n_half = int(gdf["half_flow_date"].notna().sum())
    print(f"mapped gauges: {len(gdf)}; half-flow date available: {n_half}")
    return gdf


def build_figure(
    gdf: gpd.GeoDataFrame,
    panels: list[tuple[str, str, list[float]]],
    letters: str,
    support_dir: Path | None = None,
) -> plt.Figure:
    """Two hex maps: cell medians above outlet-count histograms and compact legends."""
    ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    if ne_land.crs is None:
        raise ValueError("The map background requires a declared CRS")
    projection = get_russia_projection()
    crs = projection.proj4_init
    ne_land = ne_land.to_crs(crs)
    fig = plt.figure(figsize=(6.3, 7.1), constrained_layout=True)
    grid = fig.add_gridspec(2, 1, hspace=0.12)
    for row, (letter, (metric, title, edges)) in enumerate(zip(letters, panels, strict=True)):
        panel = grid[row].subgridspec(2, 2, height_ratios=[1, 0.22], width_ratios=[1, 1.15])
        ax = fig.add_subplot(panel[0, :], projection=projection)
        histogram = fig.add_subplot(panel[1, 0])
        legend_grid = panel[1, 1].subgridspec(2, 1, height_ratios=[1, 0.18])
        support = fig.add_subplot(legend_grid[0])
        colour_ax = fig.add_subplot(legend_grid[1])
        cells = aggregate_hex(gdf, metric, crs)
        if support_dir is not None:
            export_hex_support(gdf, metric, cells, crs, support_dir / f"signature_{metric}.json")
            cells.drop(columns="geometry").to_csv(support_dir / f"signature_{metric}.csv", index=False)
        _set_extent_from_data(ax, gdf)
        ax.axis("off")
        _add_graticule(ax)
        ne_land.plot(ax=ax, color="#e6e6e6", edgecolor="#cccccc", linewidth=0.25, zorder=1)
        cmap = plt.get_cmap("viridis", len(edges) - 1)
        norm = BoundaryNorm(edges, cmap.N, clip=True)
        colors = [
            cmap(norm(value)) if np.isfinite(value) else to_rgba("#aaaaaa") for value in cells.value
        ]
        cells.plot(ax=ax, color=colors, edgecolor="#444444", linewidth=0.16, zorder=3)
        ax.set_title(f"({letter}) {title}", fontsize=9, fontweight="normal", loc="left", pad=7)

        counts = _class_counts(gdf[metric].to_numpy(), np.asarray(edges))
        bars = histogram.bar(np.arange(len(counts)), counts, color=[cmap(i) for i in range(cmap.N)])
        histogram.bar_label(bars, fontsize=7, padding=2)
        histogram.set_ylim(0, max(counts.max() * 1.45, 1))
        histogram.set_title("Individual-gauge counts by colour class", fontsize=7, loc="left", pad=2)
        histogram.axis("off")
        finite = int(np.isfinite(gdf[metric]).sum())
        all_missing = int(cells.value.isna().sum())
        support.axis("off")
        support.text(
            0,
            0.5,
            f"{len(gdf)} gauges; {len(cells)} occupied hexagons\n"
            f"Missing gauges: {len(gdf) - finite}; all-missing cells: {all_missing}",
            transform=support.transAxes,
            fontsize=7,
            va="center",
            color="#444444",
        )
        colourbar = fig.colorbar(
            plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=colour_ax, orientation="horizontal"
        )
        colourbar.set_ticks(edges)
        colourbar.set_ticklabels(_format_edge_labels(np.asarray(edges)))
        colourbar.ax.tick_params(labelsize=7, length=2)
        colourbar.set_label("Cell median (grey: all values missing)", fontsize=7, labelpad=3)
        print(
            f"{metric}: gauges={len(gdf)}, finite={finite}, cells={len(cells)}, "
            f"all_missing_cells={all_missing}, class_counts={counts.tolist()}"
        )
    return fig


def main() -> None:
    """Parse CLI args, build all four figures, and write them out."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to paper/images and paper/overleaf/images (else .tmp).",
    )
    args = parser.parse_args()

    gdf = load_signatures()
    out_dirs = PAPER_DIRS if args.write else (TEST_DIR,)
    suffix = "" if args.write else "_test"
    for name, panels, letters in (
        ("fig_hydro_signatures_1", PANELS_1, "ab"),
        ("fig_hydro_signatures_2", PANELS_2, "ab"),
        ("fig_hydro_signatures_3", PANELS_3, "ab"),
        ("fig_hydro_signatures_4", PANELS_4, "ab"),
    ):
        support_dir = (
            PROJECT_ROOT / "paper/figure_data/hex_support" if args.write else TEST_DIR / "hex_support"
        )
        fig = build_figure(gdf, panels, letters, support_dir)
        # Save once and copy so both manuscript image trees are byte-identical.
        first, *rest = out_dirs
        first.mkdir(parents=True, exist_ok=True)
        # Resolve the layout at delivery DPI before freezing its physical dimensions.
        fig.set_dpi(300)
        fig.canvas.draw()
        fig.set_layout_engine("none")
        fig.savefig(first / f"{name}{suffix}.pdf", dpi=300, facecolor="white")
        print(f"wrote {first / f'{name}{suffix}.pdf'}")
        for out_dir in rest:
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(first / f"{name}{suffix}.pdf", out_dir / f"{name}{suffix}.pdf")
            print(f"wrote {out_dir / f'{name}{suffix}.pdf'}")
        plt.close(fig)


if __name__ == "__main__":
    main()
