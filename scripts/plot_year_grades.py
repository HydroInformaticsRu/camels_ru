"""Render the per-year quality-grade census heatmap (gauge x year, coloured A-F).

Reads the released per-year grades and draws one row per gauge and one column per
hydrological year, with each cell coloured by its A-F grade (ungraded years grey).
Rows are sorted by overall quality so the network's quality structure and the
temporal build-up of the record are both visible in one figure.

Output: paper/images/fig_year_grades.png and paper/overleaf/images/fig_year_grades.png
"""

from pathlib import Path

import matplotlib as mpl
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRADES_CSV = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_year_grades.csv"
OUT_PATHS = (
    PROJECT_ROOT / "paper" / "images" / "fig_year_grades.png",
    PROJECT_ROOT / "paper" / "overleaf" / "images" / "fig_year_grades.png",
)

# Ordinal mapping (higher = better) and a green->red colour ramp.
GRADE_ORDER = ["A", "B", "C", "D", "F"]
GRADE_VALUE = {g: len(GRADE_ORDER) - i for i, g in enumerate(GRADE_ORDER)}  # A=5 .. F=1
GRADE_COLOURS = {
    "A": "#1a9850",
    "B": "#91cf60",
    "C": "#fee08b",
    "D": "#fc8d59",
    "F": "#d73027",
}
NO_GRADE_COLOUR = "#d9d9d9"


def load_grade_matrix() -> tuple[np.ndarray, list[str], pd.Index]:
    """Load grades and return (numeric matrix, year columns, sorted gauge index)."""
    df = pd.read_csv(GRADES_CSV, dtype=str).set_index("gauge_id")
    year_cols = [c for c in df.columns if c.isdigit()]
    df = df[year_cols]

    seen = set(np.unique(df.values.astype(str)))
    unexpected = seen - set(GRADE_ORDER) - {"nan", "None", ""}
    if unexpected:
        print(f"WARNING: unexpected grade tokens ignored: {sorted(unexpected)}")

    num = df.apply(lambda col: col.map(GRADE_VALUE)).astype(float)
    # Sort gauges by overall quality: mean grade, then count of graded years.
    quality = num.mean(axis=1, skipna=True)
    n_graded = num.notna().sum(axis=1)
    order = (
        pd.DataFrame({"q": quality, "n": n_graded})
        .sort_values(["q", "n"], ascending=[False, False])
        .index
    )
    num = num.loc[order]
    return num.to_numpy(), year_cols, order


def plot(matrix: np.ndarray, year_cols: list[str], n_gauges: int) -> None:
    """Draw and save the census heatmap."""
    cmap = ListedColormap([GRADE_COLOURS[g] for g in reversed(GRADE_ORDER)])  # F..A -> 1..5
    cmap.set_bad(NO_GRADE_COLOUR)
    norm = BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5, 5.5], cmap.N)

    fig, ax = plt.subplots(figsize=(6.5, 8.2))
    masked = np.ma.masked_invalid(matrix)
    ax.imshow(masked, aspect="auto", cmap=cmap, norm=norm, interpolation="nearest")

    ax.set_xticks(range(len(year_cols)))
    ax.set_xticklabels(year_cols, rotation=90, fontsize=8)
    ax.set_yticks([])
    ax.set_ylabel(f"Gauges (n = {n_gauges:,}, sorted by overall quality)", fontsize=10)
    ax.set_xlabel("Hydrological year", fontsize=10)

    # Per-grade share of all graded cells, for the legend.
    total_graded = np.isfinite(matrix).sum()
    shares = {g: float((matrix == GRADE_VALUE[g]).sum()) / total_graded for g in GRADE_ORDER}
    handles = [
        Patch(facecolor=GRADE_COLOURS[g], edgecolor="none", label=f"{g}  ({shares[g]:.0%})")
        for g in GRADE_ORDER
    ]
    handles.append(Patch(facecolor=NO_GRADE_COLOUR, edgecolor="none", label="no grade"))
    ax.legend(
        handles=handles,
        title="Annual grade (share of graded cells)",
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        frameon=False,
        fontsize=9,
        title_fontsize=9,
    )

    fig.tight_layout()
    for out in OUT_PATHS:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=300, bbox_inches="tight")
        print(f"wrote {out}")
    plt.close(fig)


def main() -> None:
    """Build the per-year grade census heatmap."""
    mpl.rcParams["font.family"] = "DejaVu Sans"
    matrix, year_cols, order = load_grade_matrix()
    print(f"gauges: {len(order):,} | years: {year_cols[0]}-{year_cols[-1]}")
    plot(matrix, year_cols, len(order))


if __name__ == "__main__":
    main()
