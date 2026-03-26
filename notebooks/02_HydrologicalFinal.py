"""CAMELS-RU Hydrological Signatures — ESSD Paper 1.

Produces publication-quality figures for Section 5.4 (hydrological signatures):
    fig_hydro_signatures.png    — 8-panel map of key hydrological metrics
    fig_regime_hydrographs.png  — 3x5 grid of normalized seasonal discharge patterns
    fig_regime_map.png          — spatial distribution of hydrological regime clusters

Tables:
    paper/tables/overall_hydro_statistics.csv

Paper 1 scope: dataset description only. Trend analysis is reserved for Paper 2.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import re
import sys
import warnings

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage

sys.path.append(str(Path(__file__).parent.parent))

from src.hydro.parallel_metrics import calculate_metrics_parallel
from src.plots.paper_maps import categorical_map, continuous_multiplot

gpd.options.io_engine = "pyogrio"
warnings.simplefilter(action="ignore", category=FutureWarning)

# -- Style (matches NB00/01) -------------------------------------------------
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

# -- Paths --------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
GEOM_DIR = DATA_DIR / "geometry"
COMPOUND_DIR = DATA_DIR / "HydroData" / "Compound"
IMAGE_DIR = PROJECT_ROOT / "paper" / "images"
TABLE_DIR = PROJECT_ROOT / "paper" / "tables"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

N_HYDRO_CLUSTERS = 15
AREA_LIMIT_KM2 = 50_000
MAX_Q_MM_DAY = 50  # filter out extreme seasonal-cycle outliers

# -- Key hydrological metrics for the 8-panel map ----------------------------
KEY_METRICS: list[str] = [
    "mean_discharge",
    "q95",
    "q05",
    "baseflow_index",
    "mean_half_flow_date",
    "fdc_slope",
    "high_flow_frequency",
    "low_flow_frequency",
]

METRIC_TITLES: list[str] = [
    "Mean discharge (mm/day)",
    "Q95 (mm/day)",
    "Q05 (mm/day)",
    "Baseflow index",
    "Mean half flow date (day of year)",
    "FDC slope",
    "High flow frequency (%)",
    "Low flow frequency (%)",
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _cluster_sort_key(name: str) -> int:
    """Extract numeric cluster ID from 'Cluster N' string for sorting."""
    m = re.search(r"\d+", name)
    return int(m.group()) if m else 999


def convert_q_cms_to_mm_day(q_cms: pd.Series, area_km2: float) -> pd.Series:
    """Convert discharge from m3/s to mm/day.

    Parameters
    ----------
    q_cms : pd.Series
        Discharge in cubic meters per second.
    area_km2 : float
        Catchment area in square kilometers.

    Returns:
    -------
    pd.Series
        Discharge in mm/day.
    """
    return q_cms * 86400 / (area_km2 * 1e6) * 1e3


# =============================================================================
# LOAD DATA
# =============================================================================

print("Loading geometry...")
ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
ws.set_index("gauge_id", inplace=True)

gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
gauge.set_index("gauge_id", inplace=True)

# Filter watersheds to reasonable size (large basins average out signatures)
ws = ws.loc[ws["area_km2"] < AREA_LIMIT_KM2]
gauge = gauge.loc[gauge.index.intersection(ws.index)]

print(f"Watersheds: {len(ws)}  |  Gauges: {len(gauge)}")

# Load cluster assignments from NB01 (geophysical clusters for context)
cluster_df = pd.read_csv(
    TABLE_DIR / "cluster_assignments.csv",
    index_col="gauge_id",
    dtype={"gauge_id": str},
)
geo_cluster_info = cluster_df[["cluster_id", "cluster_name"]].rename(  # type: ignore[call-overload]
    columns={"cluster_id": "geo_cluster_id", "cluster_name": "geo_cluster_name"}
)
print(f"Geophysical clusters loaded: {geo_cluster_info['geo_cluster_id'].nunique()} clusters")

# =============================================================================
# LOAD DISCHARGE TIME SERIES
# =============================================================================

print("Loading compound discharge files...")
discharge_data: dict[str, pd.Series] = {}

for gauge_id in ws.index:
    csv_path = COMPOUND_DIR / f"{gauge_id}.csv"
    if not csv_path.exists():
        continue

    try:
        df = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
        if "q_cms" not in df.columns:
            continue

        area_km2: float = float(ws.loc[gauge_id, "area_km2"])
        if area_km2 <= 0 or np.isnan(area_km2):
            continue

        q_series: pd.Series = df["q_cms"].dropna()  # type: ignore[assignment]
        q_mm_day = convert_q_cms_to_mm_day(q_series, area_km2)
        if len(q_mm_day) > 365:
            discharge_data[gauge_id] = q_mm_day

    except Exception:
        continue

print(f"Loaded discharge for {len(discharge_data)} gauges")

# =============================================================================
# SEASONAL PATTERN CLUSTERING (Ward linkage, k=15)
# =============================================================================

print("Computing seasonal patterns...")

# Calculate median seasonal cycle for each gauge (365 values: one per day-of-year)
q_seasonal: dict[str, np.ndarray] = {}
for gauge_id, ts in discharge_data.items():
    cycle = ts.groupby([ts.index.month, ts.index.day]).median()  # type: ignore[union-attr]
    # Drop Feb 29 to ensure uniform 365-length arrays across gauges
    if (2, 29) in cycle.index:
        cycle = cycle.drop((2, 29))
    # Only keep gauges with complete 365-day cycles
    if len(cycle) == 365:
        q_seasonal[gauge_id] = np.asarray(cycle)

print(f"Gauges with complete seasonal cycles: {len(q_seasonal)}")
q_df = pd.DataFrame.from_dict(q_seasonal, orient="columns")

# Filter out gauges with extreme outliers
q_df = q_df.loc[:, q_df.max() < MAX_Q_MM_DAY]

# Normalize each gauge to [0, 1]
q_min = q_df.min()
q_range = q_df.max() - q_min
q_range = q_range.replace(0, np.nan)
q_df_norm = (q_df - q_min) / q_range
q_df_norm = q_df_norm.dropna(axis=1)

# Transpose for clustering: rows = gauges, columns = days
q_clust = q_df_norm.T.copy()

# Add spatial coordinates as clustering features (min-max normalized to [0, 1])
raw_lat = pd.Series({gid: gauge.loc[gid, "geometry"].y for gid in q_clust.index if gid in gauge.index})
raw_lon = pd.Series({gid: gauge.loc[gid, "geometry"].x for gid in q_clust.index if gid in gauge.index})
q_clust["lat"] = (raw_lat - raw_lat.min()) / (raw_lat.max() - raw_lat.min())
q_clust["lon"] = (raw_lon - raw_lon.min()) / (raw_lon.max() - raw_lon.min())

q_clust = q_clust.dropna()
hydro_index = q_clust.index

# Keep only gauges that passed filtering for metrics computation
discharge_data = {k: v for k, v in discharge_data.items() if k in hydro_index}

print(f"Clustering {len(q_clust)} gauges ({q_clust.shape[1]} features: 365 days + 2 coords)")

# Ward linkage clustering
Z = linkage(q_clust.values, method="ward", metric="euclidean")
hydro_labels = fcluster(Z, t=N_HYDRO_CLUSTERS, criterion="maxclust")

# Assign clusters to gauge GeoDataFrame
gauge_hydro = gauge.loc[q_clust.index].copy()
gauge_hydro["hydro_cluster_id"] = hydro_labels
gauge_hydro["hydro_cluster"] = [f"Cluster {cl}" for cl in hydro_labels]

print(f"Assigned {N_HYDRO_CLUSTERS} hydrological regime clusters")
for cname in sorted(gauge_hydro["hydro_cluster"].unique(), key=_cluster_sort_key):
    n = (gauge_hydro["hydro_cluster"] == cname).sum()
    print(f"  {cname}: {n} gauges")

# =============================================================================
# FIG 1 — REGIME HYDROGRAPHS (3x5 grid)
# =============================================================================

print("Plotting regime hydrographs...")

cluster_groups = list(gauge_hydro.groupby("hydro_cluster").groups.items())
cluster_groups_sorted = sorted(cluster_groups, key=lambda x: _cluster_sort_key(x[0]))

cluster_q: OrderedDict[str, pd.DataFrame] = OrderedDict()
for clust_name, member_ids in cluster_groups_sorted:
    cdf = q_df_norm.loc[:, q_df_norm.columns.intersection(member_ids)].copy()
    cdf.index = pd.date_range(start="2000-01-01", periods=len(cdf))
    cluster_q[clust_name] = cdf

nrows, ncols = 3, 5
fig_hydro, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(20, 10))
axes_flat = axes.flatten()

for i, (clust_name, clust_data) in enumerate(cluster_q.items()):
    if i >= len(axes_flat):
        break
    ax = axes_flat[i]

    # Group by (month, day), then take median across gauges
    idx = clust_data.index
    grouped = clust_data.groupby([idx.month, idx.day]).median()  # type: ignore[attr-defined]
    grouped = grouped.reset_index(drop=True)
    cluster_median = np.asarray(grouped.median(axis=1)).ravel()

    # Individual gauges (faint)
    for col in grouped.columns:
        ax.plot(
            grouped.index.values,
            grouped[col].values,
            color="steelblue",
            alpha=0.15,
            linewidth=0.5,
        )

    # Cluster median (bold)
    ax.plot(
        grouped.index.values,
        cluster_median,
        color="#CC3311",
        alpha=1.0,
        linewidth=2.0,
        label="Cluster median",
    )

    ax.grid(alpha=0.2, linestyle="--")
    ax.set_xlim(0, 365)
    ax.set_ylim(0, 1)
    ax.set_yticks(np.arange(0, 1.25, 0.25))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))

    if i % ncols == 0:
        ax.set_ylabel("Normalized runoff")
    if i >= (nrows - 1) * ncols:
        ax.set_xlabel("Day of year")

    n_members = len(clust_data.columns)
    ax.set_title(f"{clust_name} (n={n_members})", fontsize=10, fontweight="bold")

# Hide unused subplots
for j in range(len(cluster_q), len(axes_flat)):
    axes_flat[j].set_visible(False)

fig_hydro.suptitle(
    "Hydrological Regime Types: Normalized Seasonal Discharge Patterns",
    fontsize=13,
    fontweight="bold",
    y=1.005,
)
fig_hydro.tight_layout()
fig_hydro.savefig(IMAGE_DIR / "fig_regime_hydrographs.png", dpi=300, bbox_inches="tight")
plt.close()
print(f"  Saved {IMAGE_DIR / 'fig_regime_hydrographs.png'}")

# =============================================================================
# FIG 2 — REGIME SPATIAL MAP (categorical)
# =============================================================================

print("Plotting regime spatial map...")

category_order = sorted(gauge_hydro["hydro_cluster"].unique(), key=_cluster_sort_key)

from src.plots.paper_maps import get_russia_projection  # noqa: E402

_aea = get_russia_projection()
fig_map, ax_map = plt.subplots(figsize=(14, 7), subplot_kw={"projection": _aea})
categorical_map(
    gauge_hydro,
    ax_map,
    "hydro_cluster",
    category_order=category_order,
    marker_size=16,
    title=f"Hydrological Regime Clusters ({N_HYDRO_CLUSTERS} clusters, {len(gauge_hydro)} gauges)",
    legend_ncol=5,
    legend_fontsize=7,
    legend_loc="lower right",
    show_counts=True,
)
fig_map.tight_layout()
fig_map.savefig(IMAGE_DIR / "fig_regime_map.png", dpi=300, bbox_inches="tight")
plt.close()
print(f"  Saved {IMAGE_DIR / 'fig_regime_map.png'}")

# =============================================================================
# COMPUTE HYDROLOGICAL METRICS (parallel)
# =============================================================================

print(f"Computing hydrological metrics for {len(discharge_data)} gauges...")

all_metrics = calculate_metrics_parallel(
    discharge_data=discharge_data,
    gauge_ids=hydro_index,
    n_workers=12,
    period_type="hydrological",
    hydro_year_start_month=10,
    min_data_fraction=0.7,
    min_periods=5,
    aggregation="mean",
    show_progress=True,
)

metrics_df = pd.DataFrame.from_dict(all_metrics, orient="index")
metrics_df = metrics_df.dropna(thresh=5)

# Build analysis GeoDataFrame: gauge geometry + metrics + clusters + area
gauge_analysis = gauge.join(metrics_df, how="inner")
gauge_analysis = gauge_analysis.join(gauge_hydro[["hydro_cluster_id", "hydro_cluster"]], how="left")
gauge_analysis = gauge_analysis.join(geo_cluster_info, how="left")
gauge_analysis = gauge_analysis.join(ws[["area_km2"]], how="left")

print(f"Analysis dataset: {len(gauge_analysis)} gauges with {len(gauge_analysis.columns)} attributes")

# =============================================================================
# FIG 3 — 8-PANEL HYDROLOGICAL METRICS MAP
# =============================================================================

print("Plotting 8-panel hydrological metrics map...")

# Bin edges as flat lists (paper_maps API format)
bin_intervals: dict[str, list[float]] = {
    "mean_discharge": [0, 0.3, 0.6, 1.0, 1.5, 2.5, 5.0, 8.0],
    "q95": [0, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0, 2.5],
    "q05": [0, 1, 3, 5, 7, 10, 15, 20],
    "baseflow_index": [0.2, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85],
    "mean_half_flow_date": [120.0, 150.0, 180.0, 200.0, 220.0, 240.0, 270.0],
    "fdc_slope": [0, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 15.0],
    "high_flow_frequency": [0, 10, 15, 20, 25, 30, 40, 50],
    "low_flow_frequency": [0, 2, 5, 10, 20, 35, 50, 70],
}

# Split into 2 figures of 4 panels each for readability
metrics_1 = KEY_METRICS[:4]  # discharge, Q95, Q05, BFI
titles_1 = METRIC_TITLES[:4]
bins_1 = {k: bin_intervals[k] for k in metrics_1}

metrics_2 = KEY_METRICS[4:]  # half-flow, FDC slope, high-flow freq, low-flow freq
titles_2 = METRIC_TITLES[4:]
bins_2 = {k: bin_intervals[k] for k in metrics_2}

# Natural Earth coastline (no political borders)
_ne_land = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")

fig_sig1 = continuous_multiplot(
    gdf=gauge_analysis,
    metrics=metrics_1,
    titles=[f"({c}) {t}" for c, t in zip("abcd", titles_1)],
    ncols=2,
    panel_size=(8.0, 5.0),
    cmap_name="RdYlBu_r",
    bin_intervals=bins_1,
    marker_size=8,
    suptitle=f"Hydrological Signatures: Magnitude and Baseflow (n={len(gauge_analysis)})",
    show_nan=True,
    background_gdf=_ne_land,
)
fig_sig1.savefig(IMAGE_DIR / "fig_hydro_signatures_1.png", dpi=300, bbox_inches="tight")
plt.close(fig_sig1)
print("  Saved fig_hydro_signatures_1.png")

fig_sig2 = continuous_multiplot(
    gdf=gauge_analysis,
    metrics=metrics_2,
    titles=[f"({c}) {t}" for c, t in zip("efgh", titles_2)],
    ncols=2,
    panel_size=(8.0, 5.0),
    cmap_name="RdYlBu_r",
    bin_intervals=bins_2,
    marker_size=8,
    suptitle=f"Hydrological Signatures: Timing, Variability, and Extremes (n={len(gauge_analysis)})",
    show_nan=True,
    background_gdf=_ne_land,
)
fig_sig2.savefig(IMAGE_DIR / "fig_hydro_signatures_2.png", dpi=300, bbox_inches="tight")
plt.close(fig_sig2)
print("  Saved fig_hydro_signatures_2.png")

# =============================================================================
# TABLE — OVERALL HYDROLOGICAL STATISTICS
# =============================================================================

print("Computing summary statistics...")

overall_stats = pd.DataFrame(
    {
        "Metric": METRIC_TITLES,
        "Mean": [gauge_analysis[m].mean() for m in KEY_METRICS],
        "Median": [gauge_analysis[m].median() for m in KEY_METRICS],
        "Std": [gauge_analysis[m].std() for m in KEY_METRICS],
        "Min": [gauge_analysis[m].min() for m in KEY_METRICS],
        "Max": [gauge_analysis[m].max() for m in KEY_METRICS],
        "N": [gauge_analysis[m].notna().sum() for m in KEY_METRICS],
    }
)
overall_stats.to_csv(TABLE_DIR / "overall_hydro_statistics.csv", index=False)
print(f"  Saved {TABLE_DIR / 'overall_hydro_statistics.csv'}")

print("\n=== Overall Hydrological Statistics ===")
print(overall_stats.to_string(index=False))

print("\nDone. All figures and tables saved to paper/images/ and paper/tables/.")
