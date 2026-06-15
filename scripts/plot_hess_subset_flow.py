#!/usr/bin/env python3
"""Plot the CAMELS-RU HESS subset/sample-size flow from audit outputs.

The HESS manuscript uses several defensible N values: release membership,
HydroATLAS coverage, discharge-bearing gauges, graded gauges, cleaned signature
rows, strict map subsets, and dam/regulation-screened broad-analysis subsets.
This figure turns the CSV outputs from ``scripts/hess_quality_audit.py`` into a
reviewer-facing visual flow without rerunning long notebooks.
"""

from __future__ import annotations

from pathlib import Path
import shutil

from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import matplotlib.pyplot as plt
import pandas as pd

plt.switch_backend("Agg")

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "results" / "hess_quality"
SUBSET_FLOW = AUDIT_DIR / "subset_flow.csv"
DAM_FILTER = AUDIT_DIR / "dam_filter_summary.csv"
OUT_PNG = ROOT / "paper" / "images" / "fig_subset_flow.png"
OVERLEAF_OUT_PNG = ROOT / "paper" / "overleaf" / "images" / "fig_subset_flow.png"

BOX_FACE = "#f3f7ff"
BOX_EDGE = "#315a9c"
BRANCH_FACE = "#fff7e6"
BRANCH_EDGE = "#a76500"
ACCENT_FACE = "#eefaf1"
ACCENT_EDGE = "#1f7a3a"
TEXT_COLOR = "#182033"


def _subset_count(flow: pd.DataFrame, subset: str) -> int:
    """Return an integer count from subset_flow.csv."""
    match = flow.loc[flow["subset"] == subset, "n"]
    if match.empty:
        raise KeyError(f"Missing subset in {SUBSET_FLOW}: {subset}")
    return int(match.iloc[0])


def _dam_count(dam: pd.DataFrame, subset: str) -> int:
    """Return an integer count from dam_filter_summary.csv."""
    match = dam.loc[dam["subset"] == subset, "n"]
    if match.empty:
        raise KeyError(f"Missing subset in {DAM_FILTER}: {subset}")
    return int(match.iloc[0])


def _box(
    ax: plt.Axes,
    x: float,
    y: float,
    label: str,
    count: int,
    detail: str,
    facecolor: str = BOX_FACE,
    edgecolor: str = BOX_EDGE,
) -> None:
    """Draw one labelled rounded box."""
    width = 0.39
    height = 0.13
    patch = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.015,rounding_size=0.02",
        linewidth=1.3,
        edgecolor=edgecolor,
        facecolor=facecolor,
    )
    ax.add_patch(patch)
    ax.text(
        x,
        y + 0.027,
        label,
        ha="center",
        va="center",
        fontsize=9.3,
        fontweight="bold",
        color=TEXT_COLOR,
    )
    ax.text(
        x,
        y - 0.012,
        f"n = {count:,}",
        ha="center",
        va="center",
        fontsize=9.0,
        color=TEXT_COLOR,
    )
    ax.text(
        x,
        y - 0.047,
        detail,
        ha="center",
        va="center",
        fontsize=7.2,
        color="#4d5667",
    )


def _arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float]) -> None:
    """Draw a flow arrow between boxes."""
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.2,
        color="#5b6375",
        shrinkA=8,
        shrinkB=8,
        connectionstyle="arc3,rad=0.0",
    )
    ax.add_patch(arrow)


def _draw_column(
    ax: plt.Axes,
    x: float,
    nodes: list[tuple[str, int, str, str]],
    y_top: float = 0.88,
    y_step: float = 0.17,
) -> list[tuple[float, float]]:
    """Draw one vertical flow column and return node centres."""
    positions: list[tuple[float, float]] = []
    for i, (label, count, detail, kind) in enumerate(nodes):
        y = y_top - i * y_step
        if kind == "branch":
            face, edge = BRANCH_FACE, BRANCH_EDGE
        elif kind == "accent":
            face, edge = ACCENT_FACE, ACCENT_EDGE
        else:
            face, edge = BOX_FACE, BOX_EDGE
        _box(ax, x, y, label, count, detail, face, edge)
        positions.append((x, y))
    for start, end in zip(positions[:-1], positions[1:], strict=False):
        _arrow(ax, (start[0], start[1] - 0.065), (end[0], end[1] + 0.065))
    return positions


def plot_subset_flow(flow: pd.DataFrame, dam: pd.DataFrame) -> None:
    """Render the subset-flow figure."""
    left_nodes = [
        (
            "Delineated catchments",
            _subset_count(flow, "all_delineated_catchments"),
            "boundary + NetCDF coordinate universe",
            "normal",
        ),
        (
            "HydroATLAS-covered",
            _subset_count(flow, "hydroatlas_covered_catchments"),
            "static attributes available",
            "normal",
        ),
        (
            "Discharge-bearing",
            _subset_count(flow, "discharge_bearing_gauges"),
            "any finite daily Q",
            "normal",
        ),
        (
            "Graded discharge gauges",
            _subset_count(flow, "graded_discharge_gauges"),
            "annual A--F QC assigned",
            "normal",
        ),
        (
            "Grade A subset",
            _subset_count(flow, "grade_a_all_assessed_years"),
            "every assessed year is A",
            "accent",
        ),
    ]
    right_nodes = [
        (
            "Signature rows",
            _subset_count(flow, "signatures_raw_area_record_filter"),
            "area < 50,000 km² + >=5 hydrological years",
            "normal",
        ),
        (
            "Cleaned signatures",
            _subset_count(flow, "signatures_clean_non_anomalous"),
            "17 small-basin anomalies removed",
            "normal",
        ),
        (
            "Dam-excluded broad analysis",
            _dam_count(dam, "broad_analysis_dam_excluded"),
            "dor_pc_pva = 0; proxy, not natural-basin proof",
            "accent",
        ),
        (
            "Water-balance subset",
            _subset_count(flow, "water_balance_released_era5_columns"),
            "Q/P + aridity + evaporative indices",
            "branch",
        ),
        (
            "Strict map subset",
            _subset_count(flow, "strict_completeness_main_text_maps"),
            ">70%/yr intermediate completeness",
            "branch",
        ),
        (
            "Half-flow strict subset",
            _subset_count(flow, "half_flow_strict_main_text_maps"),
            ">82%/yr for timing metric",
            "branch",
        ),
    ]

    fig, ax = plt.subplots(figsize=(11.8, 7.2), constrained_layout=True)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title(
        "CAMELS-RU sample-size flow for HESS manuscript analyses",
        fontsize=15,
        fontweight="bold",
        color=TEXT_COLOR,
        pad=16,
    )
    ax.text(
        0.5,
        0.965,
        "Counts are recomputed from release files and local intermediate artefacts by "
        "scripts/hess_quality_audit.py.",
        ha="center",
        va="center",
        fontsize=9,
        color="#4d5667",
    )

    left_pos = _draw_column(ax, 0.28, left_nodes, y_top=0.85, y_step=0.17)
    right_pos = _draw_column(ax, 0.72, right_nodes, y_top=0.85, y_step=0.135)
    _arrow(ax, (left_pos[2][0] + 0.20, left_pos[2][1]), (right_pos[0][0] - 0.20, right_pos[0][1]))

    ax.text(
        0.28,
        0.055,
        "QC path",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color=BOX_EDGE,
    )
    ax.text(
        0.72,
        0.055,
        "Hydrological-signature / HESS-analysis path",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color=BRANCH_EDGE,
    )
    ax.text(
        0.5,
        0.018,
        "The dam-excluded subset uses HydroATLAS dor_pc_pva as a regulation proxy; "
        "it must not be described as a verified natural-basin class.",
        ha="center",
        va="center",
        fontsize=8.2,
        color="#6b2737",
    )

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=220, bbox_inches="tight")
    plt.close(fig)
    if OVERLEAF_OUT_PNG.parent.exists():
        shutil.copy2(OUT_PNG, OVERLEAF_OUT_PNG)


def main() -> None:
    """Load audit CSVs and write the HESS subset-flow figure."""
    if not SUBSET_FLOW.exists() or not DAM_FILTER.exists():
        raise SystemExit(
            "Missing audit CSVs; run `pixi run python scripts/hess_quality_audit.py` first."
        )
    flow = pd.read_csv(SUBSET_FLOW)
    dam = pd.read_csv(DAM_FILTER)
    plot_subset_flow(flow, dam)
    print(f"Wrote {OUT_PNG.relative_to(ROOT)}")
    if OVERLEAF_OUT_PNG.exists():
        print(f"Copied {OVERLEAF_OUT_PNG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
