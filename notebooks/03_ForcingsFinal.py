"""CAMELS-RU meteorological forcing diagnostics for the HESS manuscript.

Produces publication-quality figures for Section 4 (forcings description):
  - fig_precip_comparison.png     — 3-panel map: ERA5/MSWEP/GPCP mean annual P
  - fig_water_balance.png         — 2-panel map: runoff ratio (Q/P) + ET proxy (P-Q)
  - fig_forcing_correlations.png  — Inter-dataset scatter/agreement

Tables:
  - paper/tables/precip_dataset_comparison.csv
  - paper/tables/precip_inter_dataset_corr.csv

Design:
  - No trend analysis (reserved for Paper 2)
  - No P-Q lag analysis, event detection, or seasonal regime classification
  - Colorblind-safe Paul Tol palette (via paper_maps)
  - No country borders or basemap
"""

from __future__ import annotations

from pathlib import Path
import sys
import warnings

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from src.plots.paper_maps import continuous_multiplot
from src.utils.paper_analysis_scope import (
    PAPER_ANALYSIS_EXCLUSION_NOTE,
    filter_paper_analysis_index,
    paper_analysis_scope_summary,
)

gpd.options.io_engine = "pyogrio"
warnings.simplefilter(action="ignore", category=FutureWarning)

# ── Style ────────────────────────────────────────────────────────────────────
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

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
METEO_DIR = DATA_DIR / "parsed_meteo"
ERA5_DIR = METEO_DIR / "era5_land"
MSWEP_DIR = METEO_DIR / "mswep"
GPCP_DIR = METEO_DIR / "gpcp"
COMPOUND_DIR = DATA_DIR / "HydroData" / "Compound"
GEOM_DIR = DATA_DIR / "geometry"
IMAGE_DIR = PROJECT_ROOT / "paper" / "images"
TABLE_DIR = PROJECT_ROOT / "paper" / "tables"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

# Analysis period
PERIOD_START = "2008-01-01"
PERIOD_END_ERA5 = "2023-12-31"
PERIOD_END_GPCP = "2021-09-30"  # GPCP ends earlier


# ── Helpers ──────────────────────────────────────────────────────────────────
def load_csv_series(path: Path, value_col: str, date_col: str = "date") -> pd.Series | None:
    """Load a single-column time series from CSV, returning None on failure."""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col=date_col, parse_dates=True)
        if value_col not in df.columns:
            return None
        return pd.Series(df[value_col])
    except Exception:
        return None


def annual_mean_precip(series: pd.Series, end_date: str) -> float:
    """Mean annual precipitation total (mm/yr) over the analysis period."""
    sub = series.loc[PERIOD_START:end_date]
    if len(sub) < 365:
        return np.nan
    return float(sub.resample("YE").sum().mean())


def annual_cv_precip(series: pd.Series, end_date: str) -> float:
    """Coefficient of variation of annual precipitation totals."""
    sub = series.loc[PERIOD_START:end_date]
    if len(sub) < 365:
        return np.nan
    annual = sub.resample("YE").sum()
    return float(annual.std() / annual.mean()) if annual.mean() > 0 else np.nan


# ══════════════════════════════════════════════════════════════════════════════
# LOAD GEOMETRY
# ══════════════════════════════════════════════════════════════════════════════

gauge_gdf = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
gauge_gdf.set_index("gauge_id", inplace=True)
gauge_gdf.index = gauge_gdf.index.astype(str)

ws_gdf = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
ws_gdf.set_index("gauge_id", inplace=True)
ws_gdf.index = ws_gdf.index.astype(str)

release_scope = paper_analysis_scope_summary(gauge_gdf.index)
gauge_gdf = filter_paper_analysis_index(gauge_gdf)
ws_gdf = filter_paper_analysis_index(ws_gdf)

print(
    f"Loaded {release_scope.n_total} release gauge locations, {len(ws_gdf)} paper-analysis watersheds"
)
print(
    "Paper-analysis gauge-ID scope: "
    f"include {release_scope.n_included}, exclude {release_scope.n_excluded} "
    f"(ID length >= {release_scope.excluded_min_id_length})"
)
print(PAPER_ANALYSIS_EXCLUSION_NOTE)

# ══════════════════════════════════════════════════════════════════════════════
# LOAD PRECIPITATION (ERA5-Land, MSWEP, GPCP)
# ══════════════════════════════════════════════════════════════════════════════

# Determine valid gauge set from gauge geometry
all_gauge_ids: list[str] = gauge_gdf.index.tolist()

# Storage: gauge_id -> dataset -> pd.Series
precip_data: dict[str, dict[str, pd.Series]] = {}
dataset_availability: dict[str, list[str]] = {
    "era5": [],
    "mswep": [],
    "gpcp": [],
}

for gid in all_gauge_ids:
    precip_data[gid] = {}

    # ERA5-Land: column "prcp"
    era5_s = load_csv_series(ERA5_DIR / f"{gid}.csv", "prcp")
    if era5_s is not None:
        precip_data[gid]["era5"] = era5_s
        dataset_availability["era5"].append(gid)

    # MSWEP: column "precipitation"
    mswep_s = load_csv_series(MSWEP_DIR / f"{gid}.csv", "precipitation")
    if mswep_s is not None:
        precip_data[gid]["mswep"] = mswep_s
        dataset_availability["mswep"].append(gid)

    # GPCP: column "precip"
    gpcp_s = load_csv_series(GPCP_DIR / f"{gid}.csv", "precip")
    if gpcp_s is not None:
        precip_data[gid]["gpcp"] = gpcp_s
        dataset_availability["gpcp"].append(gid)

n_total = len(all_gauge_ids)
n_all_three = len(
    set(dataset_availability["era5"])
    & set(dataset_availability["mswep"])
    & set(dataset_availability["gpcp"])
)
print("=" * 70)
print("PRECIPITATION DATASET AVAILABILITY")
print("=" * 70)
for ds in ("era5", "mswep", "gpcp"):
    n = len(dataset_availability[ds])
    print(f"  {ds.upper():10s}: {n:>5d} gauges ({100 * n / n_total:.1f}%)")
print(f"  {'All three':10s}: {n_all_three:>5d} gauges")
print("=" * 70)

# ══════════════════════════════════════════════════════════════════════════════
# PRECIPITATION STATISTICS PER GAUGE
# ══════════════════════════════════════════════════════════════════════════════

prcp_rows: list[dict[str, object]] = []

for gid in all_gauge_ids:
    row: dict[str, object] = {"gauge_id": gid}
    has_any = False

    for ds in ("era5", "mswep", "gpcp"):
        if ds not in precip_data[gid]:
            continue
        end = PERIOD_END_GPCP if ds == "gpcp" else PERIOD_END_ERA5
        s = precip_data[gid][ds]

        mean_ann = annual_mean_precip(s, end)
        cv_ann = annual_cv_precip(s, end)
        if np.isnan(mean_ann):
            continue

        row[f"{ds}_mean_annual_mm"] = mean_ann
        row[f"{ds}_cv_annual"] = cv_ann
        has_any = True

    if has_any:
        prcp_rows.append(row)

prcp_stats_df = pd.DataFrame(prcp_rows).set_index("gauge_id")
print(f"\nPrecipitation statistics computed for {len(prcp_stats_df)} gauges")

# Summary table
print("\nMean annual precipitation across gauges (mm/yr):")
for ds in ("era5", "mswep", "gpcp"):
    col = f"{ds}_mean_annual_mm"
    if col in prcp_stats_df.columns:
        vals = prcp_stats_df[col].dropna()
        print(f"  {ds.upper():8s}: {vals.mean():.0f} +/- {vals.std():.0f}  (n={len(vals)})")

# ══════════════════════════════════════════════════════════════════════════════
# INTER-DATASET CORRELATIONS (daily precip, common period 2008-2021)
# ══════════════════════════════════════════════════════════════════════════════

COMMON_END = "2021-09-30"  # limited by GPCP

corr_rows: list[dict[str, object]] = []
for gid in all_gauge_ids:
    crow: dict[str, object] = {"gauge_id": gid}
    has_corr = False

    pairs = [
        ("era5", "mswep", "era5_mswep"),
        ("era5", "gpcp", "era5_gpcp"),
        ("mswep", "gpcp", "mswep_gpcp"),
    ]
    for ds_a, ds_b, label in pairs:
        if ds_a not in precip_data[gid] or ds_b not in precip_data[gid]:
            continue
        a = precip_data[gid][ds_a].loc[PERIOD_START:COMMON_END]
        b = precip_data[gid][ds_b].loc[PERIOD_START:COMMON_END]
        common_idx = a.index.intersection(b.index)
        if len(common_idx) < 365:
            continue
        crow[f"{label}_r"] = float(a.loc[common_idx].corr(b.loc[common_idx]))
        crow[f"{label}_bias_mm_day"] = float(a.loc[common_idx].mean() - b.loc[common_idx].mean())
        has_corr = True

    if has_corr:
        corr_rows.append(crow)

corr_df = pd.DataFrame(corr_rows).set_index("gauge_id")
print(f"\nInter-dataset correlations computed for {len(corr_df)} gauges")
print("\nMedian daily-value correlations:")
for label in ("era5_mswep", "era5_gpcp", "mswep_gpcp"):
    col = f"{label}_r"
    if col in corr_df.columns:
        vals = corr_df[col].dropna()
        print(f"  {label.upper():15s}: {vals.median():.3f}  (mean {vals.mean():.3f})")

# ══════════════════════════════════════════════════════════════════════════════
# LOAD TEMPERATURE (ERA5-Land) — basic overview
# ══════════════════════════════════════════════════════════════════════════════

temp_rows: list[dict[str, object]] = []

for gid in all_gauge_ids:
    era5_path = ERA5_DIR / f"{gid}.csv"
    if not era5_path.exists():
        continue
    try:
        df = pd.read_csv(era5_path, index_col="date", parse_dates=True)
    except Exception:
        continue

    if "t_mean" not in df.columns:
        continue

    t = df["t_mean"].loc[PERIOD_START:PERIOD_END_ERA5]
    if len(t) < 365:
        continue

    trow: dict[str, object] = {"gauge_id": gid}
    trow["t_mean_annual_C"] = float(t.mean())

    # Seasonal means (DJF, MAM, JJA, SON)
    month_to_season = {
        12: "DJF",
        1: "DJF",
        2: "DJF",
        3: "MAM",
        4: "MAM",
        5: "MAM",
        6: "JJA",
        7: "JJA",
        8: "JJA",
        9: "SON",
        10: "SON",
        11: "SON",
    }
    t_df = t.to_frame("t")
    t_df["season"] = t_df.index.month.map(month_to_season)
    for season in ("DJF", "MAM", "JJA", "SON"):
        smean = t_df.loc[t_df["season"] == season, "t"].mean()
        trow[f"t_mean_{season}_C"] = float(smean)

    temp_rows.append(trow)

temp_df = pd.DataFrame(temp_rows).set_index("gauge_id")
print(f"\nTemperature overview computed for {len(temp_df)} gauges")
print(f"  Mean annual T: {temp_df['t_mean_annual_C'].mean():.1f} C")

# ══════════════════════════════════════════════════════════════════════════════
# LOAD DISCHARGE & COMPUTE WATER BALANCE
# ══════════════════════════════════════════════════════════════════════════════

# We need area_km2 for Q_mm conversion only if Compound does not have q_mm_day.
# Compound files already have q_mm_day, so use it directly.

wb_rows: list[dict[str, object]] = []

# Use ERA5 as the primary P dataset for water balance (most complete).
# Also compute for MSWEP where available.
for gid in all_gauge_ids:
    q_series = load_csv_series(COMPOUND_DIR / f"{gid}.csv", "q_mm_day")
    if q_series is None:
        continue
    # Remove NaN/zero-only
    q_series = q_series.dropna()
    if len(q_series) < 365:
        continue

    wrow: dict[str, object] = {"gauge_id": gid}
    has_wb = False

    for ds in ("era5", "mswep"):
        if ds not in precip_data[gid]:
            continue
        end = PERIOD_END_ERA5
        p_s = precip_data[gid][ds].loc[PERIOD_START:end]
        q_s = q_series.loc[PERIOD_START:end]
        common_idx = p_s.index.intersection(q_s.index)
        if len(common_idx) < 365:
            continue

        p_ann = p_s.loc[common_idx].resample("YE").sum()
        q_ann = q_s.loc[common_idx].resample("YE").sum()
        years = p_ann.index.intersection(q_ann.index)
        if len(years) < 3:
            continue

        p_ann = p_ann.loc[years]
        q_ann = q_ann.loc[years]

        qp = (q_ann / p_ann).replace([np.inf, -np.inf], np.nan)
        et_proxy = p_ann - q_ann

        wrow[f"{ds}_qp_ratio"] = float(qp.median())
        wrow[f"{ds}_et_proxy_mm"] = float(et_proxy.mean())
        wrow[f"{ds}_p_annual_mm"] = float(p_ann.mean())
        wrow[f"{ds}_q_annual_mm"] = float(q_ann.mean())
        has_wb = True

    if has_wb:
        wb_rows.append(wrow)

wb_df = pd.DataFrame(wb_rows).set_index("gauge_id")
print(f"\nWater balance computed for {len(wb_df)} gauges")
if "era5_qp_ratio" in wb_df.columns:
    vals = wb_df["era5_qp_ratio"].dropna()
    print(f"  ERA5 runoff ratio Q/P: {vals.median():.2f} (median)")
if "era5_et_proxy_mm" in wb_df.columns:
    vals = wb_df["era5_et_proxy_mm"].dropna()
    print(f"  ERA5 ET proxy (P-Q):  {vals.mean():.0f} mm/yr (mean)")

# ══════════════════════════════════════════════════════════════════════════════
# ASSEMBLE GeoDataFrame FOR PLOTTING
# ══════════════════════════════════════════════════════════════════════════════

plot_gdf = gpd.GeoDataFrame(gauge_gdf[["geometry"]].copy())
plot_gdf = gpd.GeoDataFrame(plot_gdf.join(prcp_stats_df, how="inner"))
plot_gdf = gpd.GeoDataFrame(plot_gdf.join(corr_df, how="left"))
plot_gdf = gpd.GeoDataFrame(plot_gdf.join(temp_df, how="left"))
plot_gdf = gpd.GeoDataFrame(plot_gdf.join(wb_df, how="left"))
print(f"\nPlot GeoDataFrame: {len(plot_gdf)} gauges, {len(plot_gdf.columns)} columns")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 1: Precipitation Comparison — 3-panel map
# ══════════════════════════════════════════════════════════════════════════════

# Natural Earth coastline (no political borders)
_ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")

# -- Precip comparison: 3 panels with ONE shared colorbar --
import cartopy.crs as ccrs  # noqa: E402
from matplotlib import cm as mpl_cm  # noqa: E402
from matplotlib.colors import BoundaryNorm  # noqa: E402

from src.plots.paper_maps import get_russia_projection  # noqa: E402

_aea = get_russia_projection()
_data_crs = ccrs.PlateCarree()
_bin_edges = np.array([200, 400, 600, 800, 1000, 1200, 1400])
_norm = BoundaryNorm(_bin_edges, len(_bin_edges) - 1)
_cmap = mpl_cm.get_cmap("YlGnBu", len(_bin_edges) - 1)

fig_precip, axes_p = plt.subplots(3, 1, figsize=(12, 12), subplot_kw={"projection": _aea})

for ax, metric, title in zip(
    axes_p,
    ["era5_mean_annual_mm", "mswep_mean_annual_mm", "gpcp_mean_annual_mm"],
    ["(a) ERA5-Land", "(b) MSWEP v2.8", "(c) GPCP v3.3"],
    strict=True,
):
    from src.plots.paper_maps import _set_extent_from_data  # noqa: E402

    ax.axis("off")
    _set_extent_from_data(ax, plot_gdf)
    _ne_land.to_crs(_aea.proj4_init).plot(
        ax=ax,
        color="#EDEDED",
        edgecolor="#CCCCCC",
        linewidth=0.3,
        zorder=1,
    )
    valid = plot_gdf[plot_gdf[metric].notna()]
    sc = ax.scatter(
        valid.geometry.x,
        valid.geometry.y,
        c=valid[metric],
        cmap=_cmap,
        norm=_norm,
        s=8,
        edgecolors="none",
        zorder=3,
        transform=_data_crs,
    )
    ax.set_title(title, fontsize=13, fontweight="bold", loc="left")

# Single shared colorbar — positioned explicitly below all panels
fig_precip.subplots_adjust(hspace=0.35, bottom=0.08)
cbar_ax = fig_precip.add_axes([0.25, 0.02, 0.5, 0.015])  # [left, bottom, width, height]
cb = fig_precip.colorbar(
    sc,
    cax=cbar_ax,
    orientation="horizontal",
)
cb.set_ticks(_bin_edges.tolist())
cb.set_ticklabels([str(int(v)) for v in _bin_edges])
cb.set_label("mm yr⁻¹", fontsize=11)
cb.ax.tick_params(labelsize=10)

fig_precip.suptitle("Mean Annual Precipitation (mm yr⁻¹)", fontsize=14, fontweight="bold", y=1.02)
fig_precip.savefig(IMAGE_DIR / "fig_precip_comparison.png", dpi=300, bbox_inches="tight")
plt.close(fig_precip)
print("\nSaved fig_precip_comparison.png")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 2: Water Balance — 2-panel map (Q/P + ET proxy)
# ══════════════════════════════════════════════════════════════════════════════

fig_wb = continuous_multiplot(
    plot_gdf,
    metrics=["era5_qp_ratio", "era5_et_proxy_mm"],
    titles=["(a) Runoff Ratio (Q/P)", "(b) ET Proxy (P \u2212 Q, mm yr\u207b\u00b9)"],
    ncols=2,
    panel_size=(7.5, 5.5),
    cmap_name="RdYlBu_r",
    bin_intervals={
        "era5_qp_ratio": [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0],
        "era5_et_proxy_mm": [0, 100, 200, 300, 400, 500, 700],
    },
    marker_size=12,
    suptitle="Water Balance (ERA5-Land precipitation)",
    colorbar_labels={
        "era5_qp_ratio": "Q/P",
        "era5_et_proxy_mm": "mm yr⁻¹",
    },
    background_gdf=_ne_land,
)
fig_wb.savefig(IMAGE_DIR / "fig_water_balance.png", dpi=300, bbox_inches="tight")
plt.close(fig_wb)
print("Saved fig_water_balance.png")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 3: Inter-dataset Precipitation Agreement — scatter plots
# ══════════════════════════════════════════════════════════════════════════════

# Build per-gauge annual means for the common period so we scatter annual P
ann_era5: dict[str, float] = {}
ann_mswep: dict[str, float] = {}
ann_gpcp: dict[str, float] = {}

for gid in all_gauge_ids:
    for ds, store in [
        ("era5", ann_era5),
        ("mswep", ann_mswep),
        ("gpcp", ann_gpcp),
    ]:
        if ds not in precip_data[gid]:
            continue
        end = PERIOD_END_GPCP  # use common period for fair comparison
        val = annual_mean_precip(precip_data[gid][ds], end)
        if not np.isnan(val):
            store[gid] = val

# Align into a single DataFrame
scatter_df = pd.DataFrame({"ERA5": ann_era5, "MSWEP": ann_mswep, "GPCP": ann_gpcp})
scatter_df = scatter_df.dropna(subset=["ERA5"])  # need at least ERA5

fig_corr, axes = plt.subplots(1, 3, figsize=(16, 5.5))

pairs_plot = [
    ("ERA5", "MSWEP", "era5_mswep"),
    ("ERA5", "GPCP", "era5_gpcp"),
    ("MSWEP", "GPCP", "mswep_gpcp"),
]

for ax, (ds_a, ds_b, _label) in zip(axes, pairs_plot, strict=True):
    sub = scatter_df[[ds_a, ds_b]].dropna()
    if sub.empty:
        ax.set_visible(False)
        continue

    col_a = pd.Series(sub[ds_a], dtype=float)
    col_b = pd.Series(sub[ds_b], dtype=float)

    ax.scatter(col_a, col_b, s=8, alpha=0.4, c="#4477AA", edgecolors="none")

    # 1:1 line
    lo = min(float(col_a.min()), float(col_b.min())) * 0.9
    hi = max(float(col_a.max()), float(col_b.max())) * 1.1
    ax.plot([lo, hi], [lo, hi], "k--", lw=0.8, alpha=0.5, label="1:1")

    # Pearson r
    r_val = float(col_a.corr(col_b))
    bias = float(col_a.mean() - col_b.mean())
    ax.text(
        0.05,
        0.95,
        f"r = {r_val:.3f}\nbias = {bias:+.0f} mm yr⁻¹",
        transform=ax.transAxes,
        va="top",
        fontsize=11,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8},
    )

    ax.set_xlabel(f"{ds_a} (mm yr⁻¹)")
    ax.set_ylabel(f"{ds_b} (mm yr⁻¹)")
    ax.set_title(f"{ds_a} vs {ds_b}", fontsize=13, fontweight="bold", loc="left")
    ax.set_aspect("equal")
    ax.grid(alpha=0.15, linestyle="--")
    ax.legend(fontsize=9, loc="lower right")

fig_corr.suptitle(
    "Inter-Dataset Precipitation Agreement (mean annual, common period)",
    fontsize=14,
    fontweight="bold",
    y=1.02,
)
fig_corr.tight_layout()
fig_corr.savefig(IMAGE_DIR / "fig_forcing_correlations.png", dpi=300, bbox_inches="tight")
plt.close(fig_corr)
print("Saved fig_forcing_correlations.png")

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 1: Precipitation Dataset Comparison
# ══════════════════════════════════════════════════════════════════════════════

table_rows: list[dict[str, object]] = []
for ds, ds_label in [("era5", "ERA5-Land"), ("mswep", "MSWEP"), ("gpcp", "GPCP")]:
    col_ann = f"{ds}_mean_annual_mm"
    col_cv = f"{ds}_cv_annual"
    n_gauges = len(dataset_availability[ds])

    ann_vals = (
        prcp_stats_df[col_ann].dropna() if col_ann in prcp_stats_df.columns else pd.Series(dtype=float)
    )
    cv_vals = (
        prcp_stats_df[col_cv].dropna() if col_cv in prcp_stats_df.columns else pd.Series(dtype=float)
    )

    table_rows.append(
        {
            "Dataset": ds_label,
            "N gauges": n_gauges,
            "Coverage (%)": f"{100 * n_gauges / n_total:.1f}",
            "Mean annual P (mm/yr)": f"{ann_vals.mean():.0f}" if len(ann_vals) else "—",
            "Std annual P (mm/yr)": f"{ann_vals.std():.0f}" if len(ann_vals) else "—",
            "Mean CV": f"{cv_vals.mean():.2f}" if len(cv_vals) else "—",
        }
    )

table1 = pd.DataFrame(table_rows)
table1.to_csv(TABLE_DIR / "precip_dataset_comparison.csv", index=False)
print("\nTable 1: Precipitation Dataset Comparison")
print(table1.to_string(index=False))

# ══════════════════════════════════════════════════════════════════════════════
# TABLE 2: Inter-Dataset Correlations
# ══════════════════════════════════════════════════════════════════════════════

corr_table_rows: list[dict[str, object]] = []
for label, nice_label in [
    ("era5_mswep", "ERA5-Land vs MSWEP"),
    ("era5_gpcp", "ERA5-Land vs GPCP"),
    ("mswep_gpcp", "MSWEP vs GPCP"),
]:
    r_col = f"{label}_r"
    bias_col = f"{label}_bias_mm_day"
    r_vals = corr_df[r_col].dropna() if r_col in corr_df.columns else pd.Series(dtype=float)
    bias_vals = corr_df[bias_col].dropna() if bias_col in corr_df.columns else pd.Series(dtype=float)

    corr_table_rows.append(
        {
            "Comparison": nice_label,
            "N gauges": len(r_vals),
            "Mean r": f"{r_vals.mean():.3f}" if len(r_vals) else "—",
            "Median r": f"{r_vals.median():.3f}" if len(r_vals) else "—",
            "Std r": f"{r_vals.std():.3f}" if len(r_vals) else "—",
            "Mean bias (mm/day)": f"{bias_vals.mean():.3f}" if len(bias_vals) else "—",
        }
    )

table2 = pd.DataFrame(corr_table_rows)
table2.to_csv(TABLE_DIR / "precip_inter_dataset_corr.csv", index=False)
print("\nTable 2: Inter-Dataset Correlations (daily values, 2008-2021)")
print(table2.to_string(index=False))

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("FORCINGS ANALYSIS COMPLETE (CAMELS-RU manuscript diagnostics)")
print("=" * 70)
print(f"  Figures saved to: {IMAGE_DIR}")
print(f"  Tables saved to:  {TABLE_DIR}")
print(f"  Gauges analyzed:  {len(plot_gdf)}")
print("=" * 70)
