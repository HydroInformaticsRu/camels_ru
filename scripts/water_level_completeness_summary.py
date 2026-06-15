#!/usr/bin/env python3
"""Summarize CAMELS-RU water-level completeness for HESS review.

Water levels are an auxiliary CAMELS-RU product, not the core rainfall-runoff
benchmark target.  This script creates a compact completeness audit from the
released NetCDF so the manuscript can describe the component without implying
that water levels have the same A--F grading as discharge.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

plt.switch_backend("Agg")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.paper_analysis_scope import (  # noqa: E402
    is_paper_analysis_excluded_gauge_id,
)

RELEASE = ROOT / "release" / "CAMELS_RU_v1.0"
OUT_DIR = ROOT / "results" / "hess_quality"
OUT_CSV = OUT_DIR / "water_level_completeness.csv"
OUT_SUMMARY = OUT_DIR / "water_level_completeness_summary.csv"
OUT_TEX = OUT_DIR / "water_level_completeness_summary.tex"
OUT_PNG = ROOT / "paper" / "images" / "fig_water_level_completeness.png"
OVERLEAF_OUT_PNG = ROOT / "paper" / "overleaf" / "images" / "fig_water_level_completeness.png"
WATER_LEVEL_NC = RELEASE / "camels_ru_water_level.nc"

GAUGE_TYPE_LABELS = {
    -1: "unknown_or_no_water_level",
    0: "river",
    1: "reservoir_or_hydropower",
}


def _type_label(value: object) -> str:
    """Return a readable gauge-type label from the NetCDF flag value."""
    try:
        return GAUGE_TYPE_LABELS.get(int(value), f"unmapped_{int(value)}")
    except (TypeError, ValueError):
        return "missing"


def _build_completeness_table() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute per-gauge completeness and summary rows from water-level NetCDF."""
    with xr.open_dataset(WATER_LEVEL_NC) as ds:
        gauge_ids = pd.Series(ds["gauge"].values.astype(str), name="gauge_id")
        n_days = int(ds.sizes["time"])
        obs_cm = (~np.isnan(ds["water_level_cm"])).sum(dim="time").values.astype(int)
        obs_mbs = (~np.isnan(ds["water_level_mbs"])).sum(dim="time").values.astype(int)
        gauge_zero = ds["gauge_zero_m"].values
        gauge_type = ds["gauge_type"].values.astype(int)

    table = pd.DataFrame(
        {
            "gauge_id": gauge_ids,
            "gauge_type_flag": gauge_type,
            "gauge_type": [_type_label(value) for value in gauge_type],
            "n_days_total": n_days,
            "n_water_level_cm": obs_cm,
            "n_water_level_mbs": obs_mbs,
            "completeness_pct": obs_cm / n_days * 100.0,
            "mbs_completeness_pct": obs_mbs / n_days * 100.0,
            "has_water_level": obs_cm > 0,
            "has_absolute_mbs": obs_mbs > 0,
            "has_gauge_zero_m": np.isfinite(gauge_zero),
            "paper_analysis_excluded": gauge_ids.map(is_paper_analysis_excluded_gauge_id).astype(bool),
        }
    )
    table["paper_analysis_included"] = ~table["paper_analysis_excluded"]

    rows: list[dict[str, object]] = []

    def add_row(label: str, mask: pd.Series) -> None:
        subset = table.loc[mask].copy()
        with_data = subset.loc[subset["has_water_level"]]
        completeness = with_data["completeness_pct"]
        rows.append(
            {
                "subset": label,
                "n_gauge_rows": int(len(subset)),
                "n_with_water_level": int(len(with_data)),
                "n_with_absolute_mbs": int(with_data["has_absolute_mbs"].sum()),
                "n_with_gauge_zero_m": int(with_data["has_gauge_zero_m"].sum()),
                "median_completeness_pct": float(completeness.median())
                if not completeness.empty
                else np.nan,
                "p10_completeness_pct": float(completeness.quantile(0.10))
                if not completeness.empty
                else np.nan,
                "p90_completeness_pct": float(completeness.quantile(0.90))
                if not completeness.empty
                else np.nan,
                "n_completeness_ge_95": int((completeness >= 95.0).sum()),
                "n_completeness_ge_90": int((completeness >= 90.0).sum()),
                "n_completeness_ge_80": int((completeness >= 80.0).sum()),
            }
        )

    add_row("all_release_rows", pd.Series(True, index=table.index))
    add_row("paper_analysis_scope", table["paper_analysis_included"])
    for gauge_type in ["river", "reservoir_or_hydropower", "unknown_or_no_water_level"]:
        add_row(gauge_type, table["gauge_type"] == gauge_type)
    add_row(
        "paper_analysis_river",
        table["paper_analysis_included"] & table["gauge_type"].eq("river"),
    )
    summary = pd.DataFrame(rows)
    return table, summary


def _plot_summary(table: pd.DataFrame, summary: pd.DataFrame) -> None:
    """Plot water-level completeness distribution and type counts."""
    data = table.loc[table["has_water_level"]].copy()
    data["plot_type"] = data["gauge_type"].replace(
        {
            "river": "River gauges",
            "reservoir_or_hydropower": "Reservoir/hydropower gauges",
            "unknown_or_no_water_level": "Unknown/no class",
        }
    )

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), constrained_layout=True)
    bins = np.arange(0, 105, 5)
    colors = {
        "River gauges": "#315a9c",
        "Reservoir/hydropower gauges": "#a76500",
        "Unknown/no class": "#757575",
    }
    for label, group in data.groupby("plot_type"):
        axes[0].hist(
            group["completeness_pct"],
            bins=bins,
            alpha=0.65,
            label=f"{label} (n={len(group):,})",
            color=colors.get(label, "#757575"),
        )
    axes[0].set_xlabel("Water-level completeness (% of days, 2008--2023)")
    axes[0].set_ylabel("Number of gauges")
    axes[0].set_title("Per-gauge water-level record completeness")
    axes[0].legend(frameon=False, fontsize=8)
    axes[0].grid(axis="y", alpha=0.25)

    subset_order = ["paper_analysis_river", "reservoir_or_hydropower"]
    subset_rank = {name: i for i, name in enumerate(subset_order)}
    plot_rows = (
        summary.loc[summary["subset"].isin(subset_order)]
        .assign(subset_order=lambda df: df["subset"].map(subset_rank))
        .sort_values("subset_order")
    )
    label_map = {
        "paper_analysis_river": "River gauges\n(paper-analysis scope)",
        "reservoir_or_hydropower": "Reservoir / hydropower\nretained in release",
    }
    color_map = {
        "paper_analysis_river": "#315a9c",
        "reservoir_or_hydropower": "#a76500",
    }
    bar_labels = [label_map[str(label)] for label in plot_rows["subset"]]
    axes[1].bar(
        bar_labels,
        plot_rows["n_with_water_level"],
        color=[color_map[str(label)] for label in plot_rows["subset"]],
        alpha=0.8,
    )
    for idx, row in enumerate(plot_rows.to_dict(orient="records")):
        axes[1].text(
            idx,
            float(row["n_with_water_level"]) + 35,
            f"n={int(row['n_with_water_level']):,}\nmedian={row['median_completeness_pct']:.1f}%",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )
    axes[1].set_ylabel("Gauges with any water-level data")
    axes[1].set_title("Auxiliary water-level component")
    axes[1].set_ylim(0, max(plot_rows["n_with_water_level"]) * 1.18)
    axes[1].grid(axis="y", alpha=0.25)

    fig.suptitle(
        "CAMELS-RU water-level completeness audit",
        fontsize=14,
        fontweight="bold",
    )
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=220, bbox_inches="tight")
    plt.close(fig)
    if OVERLEAF_OUT_PNG.parent.exists():
        shutil.copy2(OUT_PNG, OVERLEAF_OUT_PNG)


def main() -> None:
    """Write water-level completeness CSV, LaTeX summary, and figure."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    table, summary = _build_completeness_table()
    table.to_csv(OUT_CSV, index=False, float_format="%.6g")
    summary.to_csv(OUT_SUMMARY, index=False, float_format="%.6g")
    summary.to_latex(OUT_TEX, index=False, escape=True, float_format=lambda value: f"{value:.1f}")
    _plot_summary(table, summary)
    all_row = summary.loc[summary["subset"] == "all_release_rows"].iloc[0]
    paper_row = summary.loc[summary["subset"] == "paper_analysis_scope"].iloc[0]
    print(f"Wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"Wrote {OUT_SUMMARY.relative_to(ROOT)}")
    print(f"Wrote {OUT_PNG.relative_to(ROOT)}")
    if OVERLEAF_OUT_PNG.exists():
        print(f"Copied {OVERLEAF_OUT_PNG.relative_to(ROOT)}")
    print(
        "Water-level gauges with data: "
        f"{int(all_row['n_with_water_level']):,} release / "
        f"{int(paper_row['n_with_water_level']):,} paper-analysis"
    )


if __name__ == "__main__":
    main()
