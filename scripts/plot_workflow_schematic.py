"""Render the production-workflow schematic (Fig. in Sect. 3) for the manuscript.

Three columns — data sources, processing and screening steps, released files —
with the screens and provenance marks annotated on the connecting paths
(ESSD writing round-9 M6: provenance should be readable from one figure
instead of being assembled from Sects. 3-5 and the file table).

The pipeline constants named in the boxes (16 active flags, gap filling <= 6 d,
>= 70 % coverage, >= 5 valid years) restate values that are macro-locked in the
manuscript (macros.tex) and verified by scripts/verify_macros.py; the schematic
introduces no new numbers.

Vector PDF output (line art); CreationDate stripped so reruns are byte-identical.

Usage:
    pixi run python scripts/plot_workflow_schematic.py            # test output (.tmp)
    pixi run python scripts/plot_workflow_schematic.py --write    # paper output
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAPER_DIRS = (PROJECT_ROOT / "paper" / "images", PROJECT_ROOT / "paper" / "overleaf" / "images")
TEST_DIR = PROJECT_ROOT / ".tmp" / "cluster_diag"

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"]})

STYLE = {
    "source": {"facecolor": "#dbe9f6", "edgecolor": "#5b8db8"},
    "process": {"facecolor": "#fdeed7", "edgecolor": "#c98a3d"},
    "release": {"facecolor": "#e2f0e4", "edgecolor": "#5e9e6f"},
}

# (key, style, x-center, y-center, width, height, text)
BOXES = [
    ("s_ais", "source", 13, 54, 24, 9, "AIS GMVO portal\ndaily discharge & stage\n2008–2023"),
    ("s_merit", "source", 13, 40, 24, 6, "MERIT Hydro DEM"),
    ("s_forc", "source", 13, 27, 24, 9, "Gridded forcing\nMSWEP, ERA5-Land,\nGPCP, GLEAM4"),
    ("s_hyd", "source", 13, 12, 24, 6, "HydroATLAS v1.0"),
    ("p_parse", "process", 50, 54, 30, 8, "Parsing & harmonisation\ngap filling ≤ 6 d"),
    (
        "p_grade",
        "process",
        50,
        42,
        30,
        9,
        "Per-year quality grading\ncompleteness + 16 flags\n→ grades A–F",
    ),
    ("p_delin", "process", 50, 29, 30, 9, "Watershed delineation +\nmanual boundary\nverification"),
    ("p_aggr", "process", 50, 17, 30, 7, "Basin-averaged\nforcing aggregation"),
    ("p_attr", "process", 50, 6, 30, 7, "Attribute extraction &\nsignature computation"),
    ("r_hydro", "release", 87, 54, 24, 8, "discharge.nc\nwater_level.nc"),
    ("r_grades", "release", 87, 42, 24, 8, "year_grades.csv\nyear_flags.csv"),
    ("r_bound", "release", 87, 29, 24, 6, "boundaries.gpkg"),
    ("r_forc", "release", 87, 17, 24, 6, "forcing.nc"),
    ("r_attr", "release", 87, 6, 24, 8, "attributes.csv\nsignatures.csv"),
]

# (from-key, from-side, to-key, to-side, arc, label, label-xy, label-ha)
ARROWS = [
    ("s_ais", "r", "p_parse", "l", 0.0, "", None, "center"),
    (
        "p_parse",
        "r",
        "r_hydro",
        "l",
        0.0,
        "provenance flag:\nobserved / filled / missing",
        (70, 58.5),
        "center",
    ),
    ("p_parse", "b", "p_grade", "t", 0.0, "", None, "center"),
    (
        "p_grade",
        "r",
        "r_grades",
        "l",
        0.0,
        "per-year evidence,\nauditable row by row",
        (70, 46.5),
        "center",
    ),
    ("s_merit", "r", "p_delin", "l", 0.0, "", None, "center"),
    (
        "p_delin",
        "r",
        "r_bound",
        "l",
        0.0,
        "areal-error screen vs\nRoshydromet reference",
        (70, 33.5),
        "center",
    ),
    ("s_forc", "r", "p_aggr", "l", 0.0, "", None, "center"),
    ("p_delin", "b", "p_aggr", "t", 0.0, "area weights", (51.5, 22.6), "left"),
    ("p_aggr", "r", "r_forc", "l", 0.0, "", None, "center"),
    ("s_hyd", "r", "p_attr", "l", 0.0, "", None, "center"),
    ("p_delin", "bl", "p_attr", "tl", 0.5, "", None, "center"),
    (
        "p_attr",
        "r",
        "r_attr",
        "l",
        0.0,
        "≥ 70 % coverage, ≥ 5 valid\nyears, anomaly screen",
        (70, 10.5),
        "center",
    ),
]


def _anchor(key: str, side: str) -> tuple[float, float]:
    """Edge midpoint (or corner offset) of a box for arrow attachment."""
    _, _, x, y, w, h, _ = next(b for b in BOXES if b[0] == key)
    return {
        "l": (x - w / 2, y),
        "r": (x + w / 2, y),
        "t": (x, y + h / 2),
        "b": (x, y - h / 2),
        "bl": (x - w / 2 + 0.5, y - h / 2),
        "tl": (x - w / 2 + 0.5, y + h / 2),
    }[side]


def build_figure() -> plt.Figure:
    """Assemble the three-column workflow schematic."""
    fig, ax = plt.subplots(figsize=(10, 6.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 66)
    ax.axis("off")

    for col_x, header in ((13, "Sources"), (50, "Processing and screening"), (87, "Released files")):
        ax.text(col_x, 63, header, ha="center", va="center", fontsize=14, fontweight="bold")

    for _, style, x, y, w, h, text in BOXES:
        ax.add_patch(
            mpatches.FancyBboxPatch(
                (x - w / 2, y - h / 2),
                w,
                h,
                boxstyle="round,pad=0.5",
                linewidth=1.2,
                mutation_aspect=0.6,
                **STYLE[style],
            )
        )
        ax.text(x, y, text, ha="center", va="center", fontsize=11)

    for src, s_side, dst, d_side, arc, label, label_xy, label_ha in ARROWS:
        ax.add_patch(
            mpatches.FancyArrowPatch(
                _anchor(src, s_side),
                _anchor(dst, d_side),
                arrowstyle="-|>",
                mutation_scale=14,
                linewidth=1.1,
                color="#444444",
                connectionstyle=f"arc3,rad={arc}",
                shrinkA=4,
                shrinkB=4,
            )
        )
        if label:
            ax.text(
                *label_xy,
                label,
                ha=label_ha,
                va="center",
                fontsize=10.5,
                style="italic",
                color="#444444",
            )

    fig.tight_layout(pad=0.2)
    return fig


def main() -> None:
    """Parse CLI args, build the schematic, and write it out."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to paper/images and paper/overleaf/images (else .tmp).",
    )
    args = parser.parse_args()

    fig = build_figure()
    out_dirs = PAPER_DIRS if args.write else (TEST_DIR,)
    suffix = "" if args.write else "_test"
    first, *rest = out_dirs
    first.mkdir(parents=True, exist_ok=True)
    out = first / f"fig_workflow{suffix}.pdf"
    # Save once and copy (byte parity between the two paper image dirs).
    fig.savefig(out, bbox_inches="tight", metadata={"CreationDate": None})
    print(f"wrote {out}")
    for out_dir in rest:
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, out_dir / out.name)
        print(f"wrote {out_dir / out.name}")
    plt.close(fig)


if __name__ == "__main__":
    main()
