"""Render the two hydrological-signature map figures (Section 5) from the release.

Reads the released ``camels_ru_signatures.csv``, drops the small-basin anomalies flagged
``is_anomalous``, and maps eight key signatures for the remaining cleaned gauges on the
shared Albers Equal-Area basemap. The bin edges and panel order follow the original
notebook-02 maps; the gauge set is now the released cleaned subset, so the figures
reproduce from the archive plus the gauge-point layer used by every other map script.

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
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.plots.paper_maps import continuous_multiplot  # noqa: E402
from src.utils.paper_analysis_scope import filter_paper_analysis_index  # noqa: E402

gpd.options.io_engine = "pyogrio"
warnings.simplefilter(action="ignore", category=FutureWarning)

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "figure.dpi": 150,
        "savefig.dpi": 300,
    }
)

GEOM_DIR = PROJECT_ROOT / "data" / "CAMELS_RU" / "geometry"
SIGNATURES_CSV = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_signatures.csv"
PAPER_DIRS = (PROJECT_ROOT / "paper" / "images", PROJECT_ROOT / "paper" / "overleaf" / "images")
TEST_DIR = PROJECT_ROOT / ".tmp" / "cluster_diag"

# (release column, panel title, bin edges) in figure order; bins as in notebooks/02.
PANELS_1 = [
    ("q_mean", "Mean discharge (mm d$^{-1}$)", [0, 0.3, 0.6, 1.0, 1.5, 2.5, 5.0, 8.0]),
    ("q95", "Q95 (mm d$^{-1}$)", [0, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0, 2.5]),
    ("q05", "Q05 (mm d$^{-1}$)", [0, 1, 3, 5, 7, 10, 15, 20]),
    ("baseflow_index", "Baseflow index", [0.2, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85]),
]
PANELS_2 = [
    (
        "half_flow_date",
        "Mean half-flow date (day of hydrological year)",
        [120, 150, 180, 200, 220, 240, 270],
    ),
    ("fdc_slope", "FDC slope", [0, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 15.0]),
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

    cols = [c for c, _, _ in PANELS_1 + PANELS_2]
    gdf = gauge.loc[sig.index].join(sig[cols])
    n_half = int(gdf["half_flow_date"].notna().sum())
    print(f"mapped gauges: {len(gdf)}; half-flow date available: {n_half}")
    return gdf


def build_figure(
    gdf: gpd.GeoDataFrame, panels: list[tuple[str, str, list[float]]], letters: str
) -> plt.Figure:
    """Four-panel signature map for one panel set."""
    ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    return continuous_multiplot(
        gdf=gdf,
        metrics=[c for c, _, _ in panels],
        titles=[f"({letter}) {title}" for letter, (_, title, _) in zip(letters, panels, strict=True)],
        ncols=2,
        panel_size=(8.0, 4.1),
        cmap_name="RdYlBu_r",
        bin_intervals={c: edges for c, _, edges in panels},
        marker_size=8,
        show_nan=True,
        background_gdf=ne_land,
    )


def main() -> None:
    """Parse CLI args, build both figures, and write them out."""
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
        ("fig_hydro_signatures_1", PANELS_1, "abcd"),
        ("fig_hydro_signatures_2", PANELS_2, "abcd"),
    ):
        fig = build_figure(gdf, panels, letters)
        # Save once and copy: repeated tight-bbox saves crop a few pixels differently,
        # which breaks the md5 parity between paper/images and paper/overleaf/images.
        first, *rest = out_dirs
        first.mkdir(parents=True, exist_ok=True)
        fig.savefig(first / f"{name}{suffix}.png", dpi=300, bbox_inches="tight")
        print(f"wrote {first / f'{name}{suffix}.png'}")
        for out_dir in rest:
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(first / f"{name}{suffix}.png", out_dir / f"{name}{suffix}.png")
            print(f"wrote {out_dir / f'{name}{suffix}.png'}")
        plt.close(fig)


if __name__ == "__main__":
    main()
