"""Regenerate fig_forcing_correlations on the full ERA5-Land record.

Reproduces the inter-dataset precipitation-agreement scatter that previously
lived only in ``notebooks/03_ForcingsFinal.py`` (Figure 3). Notebooks must not
be executed, so this standalone, lint-clean script rebuilds the figure from the
repointed full ERA5-Land source.

Per catchment it computes the mean-annual precipitation total (mm/yr) for each
product over the paper-analysis period (2008-2023, capped by each product's
availability), restricted to the paper-analysis gauge-ID scope (gauge_id length
< 7). It then scatters each product pair (ERA5 vs MSWEP, ERA5 vs GPCP, MSWEP vs
GPCP), annotating each panel with the Pearson r and the per-catchment mean
annual bias. It additionally reports the daily-value biases and correlations
over the common overlap period for the manuscript text numbers.

Sources (per-gauge daily CSVs, mm/d):
- ERA5-Land : data/Russia/MeteoData/CamelsRU/era5_land/*.csv  (col ``prcp``)
  NOTE: the old data/CAMELS_RU/parsed_meteo/era5_land copy was STALE
  (truncated at 2018-02); this script uses the full 2007-2024 source.
- MSWEP     : data/CAMELS_RU/parsed_meteo/mswep/*.csv          (col ``precipitation``)
- GPCP      : data/CAMELS_RU/parsed_meteo/gpcp/*.csv           (col ``precip``)

Geometry: data/CAMELS_RU/geometry/camels_gauges.gpkg (gauge_id index).

Output: paper/images/fig_forcing_correlations.png (non-release path).
"""

from __future__ import annotations

from pathlib import Path
import sys

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))
from src.utils.paper_analysis_scope import (  # noqa: E402
    filter_paper_analysis_index,
    paper_analysis_scope_summary,
)

# ── Configuration ────────────────────────────────────────────────────────────
PRODUCTS: dict[str, tuple[Path, str]] = {
    # Corrected de-accumulated ERA5-Land precip; the era5_land copy over-accumulated
    # tp (~1.5x), inflating basin P.
    "ERA5": (ROOT / "data/Russia/MeteoData/CamelsRU/era5land_tp_new", "prcp"),
    "MSWEP": (ROOT / "data/CAMELS_RU/parsed_meteo/mswep", "precipitation"),
    "GPCP": (ROOT / "data/CAMELS_RU/parsed_meteo/gpcp", "precip"),
}
GEOM_GAUGES = ROOT / "data/CAMELS_RU/geometry/camels_gauges.gpkg"
OUT_PNG = ROOT / "paper/images/fig_forcing_correlations.png"

# Paper-analysis period; GPCP availability ends earlier so it caps itself.
PERIOD_START = "2008-01-01"
PERIOD_END = "2023-12-31"
# Common overlap for the daily-statistics text numbers (limited by GPCP).
COMMON_END = "2021-09-30"

PAIRS: list[tuple[str, str]] = [("ERA5", "MSWEP"), ("ERA5", "GPCP"), ("MSWEP", "GPCP")]

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


def load_series(path: Path, col: str) -> pd.Series | None:
    """Load a daily value column from a per-gauge CSV (None on failure)."""
    if not path.exists():
        return None
    try:
        frame = pd.read_csv(path, index_col="date", parse_dates=True)
    except Exception:
        return None
    if col not in frame.columns:
        return None
    return pd.Series(frame[col])


def annual_mean_total(series: pd.Series, end: str) -> float:
    """Mean of annual precipitation totals (mm/yr) over PERIOD_START..end."""
    sub = series.loc[PERIOD_START:end]
    if len(sub) < 365:
        return np.nan
    return float(sub.resample("YE").sum().mean())


def gauge_ids() -> list[str]:
    """Paper-analysis gauge IDs (gauge_id length < 7)."""
    gdf = gpd.read_file(GEOM_GAUGES)
    gdf["gauge_id"] = gdf["gauge_id"].astype(str)
    gdf = gdf.set_index("gauge_id")
    scope = paper_analysis_scope_summary(gdf.index)
    gdf = filter_paper_analysis_index(gdf)
    print(
        f"Paper-analysis scope: include {scope.n_included}, "
        f"exclude {scope.n_excluded} (gauge_id length >= {scope.excluded_min_id_length})"
    )
    return gdf.index.tolist()


def load_precip(ids: list[str]) -> dict[str, dict[str, pd.Series]]:
    """gauge_id -> product -> daily mm/d series, for available products."""
    store: dict[str, dict[str, pd.Series]] = {}
    for gid in ids:
        store[gid] = {}
        for product, (directory, col) in PRODUCTS.items():
            s = load_series(directory / f"{gid}.csv", col)
            if s is not None:
                store[gid][product] = s
    return store


def annual_means(store: dict[str, dict[str, pd.Series]]) -> pd.DataFrame:
    """Per-catchment mean-annual P (mm/yr) per product over 2008-2023."""
    rows: dict[str, dict[str, float]] = {p: {} for p in PRODUCTS}
    for gid, products in store.items():
        for product, series in products.items():
            val = annual_mean_total(series, PERIOD_END)
            if not np.isnan(val):
                rows[product][gid] = val
    return pd.DataFrame({p: pd.Series(rows[p]) for p in PRODUCTS})


def daily_statistics(store: dict[str, dict[str, pd.Series]]) -> dict[str, dict[str, float]]:
    """Median per-catchment daily Pearson r and mean daily bias per pair."""
    acc: dict[str, dict[str, list[float]]] = {f"{a}-{b}": {"r": [], "bias": []} for a, b in PAIRS}
    for products in store.values():
        for a, b in PAIRS:
            if a not in products or b not in products:
                continue
            sa = products[a].loc[PERIOD_START:COMMON_END]
            sb = products[b].loc[PERIOD_START:COMMON_END]
            idx = sa.index.intersection(sb.index)
            if len(idx) < 365:
                continue
            ra = sa.loc[idx]
            rb = sb.loc[idx]
            acc[f"{a}-{b}"]["r"].append(float(ra.corr(rb)))
            acc[f"{a}-{b}"]["bias"].append(float(ra.mean() - rb.mean()))
    out: dict[str, dict[str, float]] = {}
    for pair, vals in acc.items():
        r = pd.Series(vals["r"]).dropna()
        bias = pd.Series(vals["bias"]).dropna()
        out[pair] = {
            "r_median": float(r.median()) if not r.empty else np.nan,
            "r_std": float(r.std()) if not r.empty else np.nan,
            "bias_median": float(bias.median()) if not bias.empty else np.nan,
            "n": int(len(r)),
        }
    return out


def make_figure(ann: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Render the 3-panel scatter; return annual r and bias per pair."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))
    stats: dict[str, dict[str, float]] = {}
    for ax, (a, b) in zip(axes, PAIRS, strict=True):
        sub = ann[[a, b]].dropna()
        col_a = pd.Series(sub[a], dtype=float)
        col_b = pd.Series(sub[b], dtype=float)
        ax.scatter(col_a, col_b, s=8, alpha=0.4, c="#4477AA", edgecolors="none")

        lo = min(float(col_a.min()), float(col_b.min())) * 0.9
        hi = max(float(col_a.max()), float(col_b.max())) * 1.1
        ax.plot([lo, hi], [lo, hi], "k--", lw=0.8, alpha=0.5, label="1:1")

        r_val = float(col_a.corr(col_b))
        bias = float(col_a.mean() - col_b.mean())
        stats[f"{a}-{b}"] = {"r": r_val, "bias": bias, "n": int(len(sub))}
        ax.text(
            0.05,
            0.95,
            f"r = {r_val:.3f}\nbias = {bias:+.0f} mm yr$^{{-1}}$",
            transform=ax.transAxes,
            va="top",
            fontsize=11,
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8},
        )
        ax.set_xlabel(f"{a} (mm yr$^{{-1}}$)")
        ax.set_ylabel(f"{b} (mm yr$^{{-1}}$)")
        ax.set_title(f"{a} vs {b}", fontsize=13, fontweight="bold", loc="left")
        ax.set_aspect("equal")
        ax.grid(alpha=0.15, linestyle="--")
        ax.legend(fontsize=9, loc="lower right")

    fig.suptitle(
        "Inter-Dataset Precipitation Agreement (mean annual, 2008-2023)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )
    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return stats


def main() -> None:
    """Build the figure and print the manuscript-facing numbers."""
    ids = gauge_ids()
    store = load_precip(ids)
    ann = annual_means(store)
    annual_stats = make_figure(ann)
    daily_stats = daily_statistics(store)

    print(f"\nSaved {OUT_PNG}")
    print("\n=== Annual mean-P scatter (per-catchment, 2008-2023) ===")
    for pair, s in annual_stats.items():
        print(f"  {pair:12s} r={s['r']:.3f}  annual bias={s['bias']:+.0f} mm/yr  n={s['n']}")
    print("\n=== Daily-value statistics (common overlap 2008..2021-09-30) ===")
    for pair, s in daily_stats.items():
        print(
            f"  {pair:12s} median r={s['r_median']:.3f} (sd {s['r_std']:.2f})  "
            f"median daily bias={s['bias_median']:+.2f} mm/d  n={s['n']}"
        )


if __name__ == "__main__":
    main()
