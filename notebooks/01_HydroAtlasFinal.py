"""CAMELS-RU catchment attributes and clustering for the HESS manuscript.

Produces figures for Section 6 (catchment attributes) and Section 7.3
(brief benchmark classification as a usage example).

Figures:
    fig_cluster_heatmap.png   — Sec 6+7.3: cluster centroid profiles
    fig_cluster_pca.png       — Sec 7.3: PCA biplot + dendrogram
    fig_cluster_map.png       — Sec 7.3: spatial distribution (no borders)

Tables:
    paper/tables/cluster_assignments.csv
    paper/tables/cluster_centroids_norm.csv
    paper/tables/cluster_centroids_raw.csv
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import warnings

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_samples,
    silhouette_score,
)

sys.path.append(str(Path(__file__).parent.parent))
from src.static.hydro_atlas_analysis import (
    CORRELATED_DROPS,
    FEATURE_DESCRIPTIONS,
    filter_hydroatlas_features,
    get_cluster_colors,
    get_cluster_markers,
    name_cluster,
)
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
        "figure.dpi": 100,
        "savefig.dpi": 300,
        "axes.labelsize": 10,
        "axes.titlesize": 11,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 8,
    }
)

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
GEOM_DIR = DATA_DIR / "geometry"
ATTR_PATH = DATA_DIR / "attributes" / "hydro_atlas_cis_camels.csv"
IMAGE_DIR = PROJECT_ROOT / "paper" / "images"
TABLE_DIR = PROJECT_ROOT / "paper" / "tables"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

N_CLUSTERS = 15
AREA_LIMIT_KM2 = 50_000  # HydroATLAS features average out in very large basins

# ══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════

ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
ws.set_index("gauge_id", inplace=True)
ws.index = ws.index.astype(str)

gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
gauge.set_index("gauge_id", inplace=True)
gauge.index = gauge.index.astype(str)

release_scope = paper_analysis_scope_summary(ws.index)
ws = filter_paper_analysis_index(ws)
gauge = filter_paper_analysis_index(gauge)

# Filter to catchments where HydroATLAS attributes are meaningful
ws_filtered = ws.loc[ws["area_km2"] < AREA_LIMIT_KM2]
gauge_filtered = gauge.loc[ws_filtered.index.intersection(gauge.index)]

print(f"Total release catchments: {release_scope.n_total}")
print(
    "Paper-analysis gauge-ID scope: "
    f"include {release_scope.n_included}, exclude {release_scope.n_excluded} "
    f"(ID length >= {release_scope.excluded_min_id_length})"
)
print(PAPER_ANALYSIS_EXCLUSION_NOTE)
print(f"After <{AREA_LIMIT_KM2:,} km² filter: {len(ws_filtered)}")

# ── Load HydroATLAS attributes ──────────────────────────────────────────────
hydro_data = pd.read_csv(ATTR_PATH, index_col="gauge_id", dtype={"gauge_id": str})

mutual_idx = gauge_filtered.index.intersection(hydro_data.index)
gauge_filtered = gauge_filtered.loc[mutual_idx]

print(f"Gauges with HydroATLAS data: {len(mutual_idx)}")

# ── Feature selection ────────────────────────────────────────────────────────
hydro_subset, selected_features = filter_hydroatlas_features(hydro_data, mutual_idx)

# Min-max scaling to [0, 1]
hydro_scaled = (hydro_subset - hydro_subset.min()) / (hydro_subset.max() - hydro_subset.min())

# Drop correlated features
to_drop = [f for f in CORRELATED_DROPS if f in hydro_scaled.columns]
hydro_scaled = hydro_scaled.drop(to_drop, axis=1)
features = hydro_scaled.columns.tolist()

print(f"Selected {len(features)} features after dropping {len(to_drop)} correlated")
print(f"Features: {features}")

# ══════════════════════════════════════════════════════════════════════════════
# HIERARCHICAL CLUSTERING (Ward, k={N_CLUSTERS})
# ══════════════════════════════════════════════════════════════════════════════

Z = linkage(hydro_scaled.values, method="ward", metric="euclidean")
labels = fcluster(Z, t=N_CLUSTERS, criterion="maxclust")

hydro_scaled["cluster"] = labels
gauge_filtered["cluster"] = labels

# Centroids (normalized and raw)
centroids_norm = hydro_scaled.groupby("cluster")[features].mean()
hydro_subset["cluster"] = labels
centroids_raw = hydro_subset.groupby("cluster")[features].mean()

# ── Validation metrics ───────────────────────────────────────────────────────
X = hydro_scaled[features].values
sil_avg = silhouette_score(X, labels)
sil_per_sample = silhouette_samples(X, labels)
ch = calinski_harabasz_score(X, labels)
db = davies_bouldin_score(X, labels)

print(f"\nClustering validation (k={N_CLUSTERS}):")
print(f"  Silhouette:       {sil_avg:.3f}")
print(f"  Calinski-Harabasz: {ch:.1f}")
print(f"  Davies-Bouldin:   {db:.3f}")

# ── Cluster naming ───────────────────────────────────────────────────────────
cluster_names = {}
for cid in range(1, N_CLUSTERS + 1):
    cluster_names[cid] = name_cluster(centroids_norm.loc[cid], centroids_raw.loc[cid])

print(f"\nCluster assignments (k={N_CLUSTERS}):")
for cid in range(1, N_CLUSTERS + 1):
    n = (labels == cid).sum()
    sil = sil_per_sample[labels == cid].mean()
    print(f"  {cid:2d}. {cluster_names[cid]:<40s} n={n:4d}  sil={sil:.3f}")

# ── PCA ──────────────────────────────────────────────────────────────────────
pca = PCA(n_components=min(10, len(features)))
pca_coords = pca.fit_transform(X)
var_explained = pca.explained_variance_ratio_
cum_var = np.cumsum(var_explained)

print("\nPCA variance explained:")
for i in range(min(5, len(var_explained))):
    print(f"  PC{i + 1}: {var_explained[i] * 100:.1f}% (cumulative: {cum_var[i] * 100:.1f}%)")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — Cluster centroid heatmap  (Section 6 + 7.3)
# ══════════════════════════════════════════════════════════════════════════════

# Build labels
short_names = [FEATURE_DESCRIPTIONS.get(f, {}).get("short", f) for f in features]
cluster_sizes = {cid: int((labels == cid).sum()) for cid in range(1, N_CLUSTERS + 1)}

heatmap_data = centroids_norm.copy()
heatmap_data.columns = short_names

# X-axis: "C1 Cropland\n(n=228)" — short first-component name directly on axis
short_cluster_names = {}
for cid in heatmap_data.index:
    full = cluster_names[cid]
    first_part = full.split(" / ")[0] if " / " in full else full
    base = re.sub(r"\s*\(.*?\)", "", first_part)
    short_cluster_names[cid] = base

heatmap_data.index = [
    f"C{cid} {short_cluster_names[cid]}\n(n={cluster_sizes[cid]})" for cid in heatmap_data.index
]

fig, ax = plt.subplots(figsize=(7.5, 7.0))
sns.heatmap(
    heatmap_data.T,
    cmap="RdYlBu_r",
    center=0.5,
    vmin=0,
    vmax=1,
    annot=True,
    fmt=".2f",
    annot_kws={"size": 6.5},
    cbar_kws={"label": "Normalized value (0\u20131)", "shrink": 0.75},
    linewidths=0.4,
    ax=ax,
)
ax.set_xlabel("")
ax.set_ylabel("")
ax.set_title(
    f"Catchment attribute cluster profiles (k={N_CLUSTERS}, Ward linkage)",
    fontsize=10,
    fontweight="bold",
    pad=8,
)
ax.tick_params(axis="x", rotation=60, labelsize=6.5)
ax.tick_params(axis="y", labelsize=8.5)

fig.tight_layout()
fig.savefig(IMAGE_DIR / "fig_cluster_heatmap.png", dpi=300, bbox_inches="tight")
plt.show()
print("Saved: fig_cluster_heatmap.png")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 2 — PCA biplot + dendrogram  (Section 7.3)
# ══════════════════════════════════════════════════════════════════════════════

colors_hc = get_cluster_colors(N_CLUSTERS)
markers_hc = get_cluster_markers(N_CLUSTERS)

fig, (ax_dendro, ax_pca) = plt.subplots(1, 2, figsize=(7.5, 4.0), gridspec_kw={"width_ratios": [1, 1.3]})

# (a) Dendrogram
dendrogram(
    Z,
    ax=ax_dendro,
    above_threshold_color="#808080",
    color_threshold=Z[-N_CLUSTERS + 1, 2],
    no_labels=True,
)
ax_dendro.axhline(
    y=Z[-N_CLUSTERS + 1, 2],
    color="red",
    linestyle="--",
    linewidth=1.5,
    label=f"Cut at k={N_CLUSTERS}",
)
ax_dendro.set_xlabel("Catchments")
ax_dendro.set_ylabel("Ward distance")
ax_dendro.set_title("(a) Dendrogram", fontsize=10, fontweight="bold", loc="left")
ax_dendro.legend(fontsize=7, loc="upper right")
ax_dendro.grid(alpha=0.15, axis="y", linestyle="--")

# (b) PCA biplot — use numbered labels matching heatmap
for cid in range(1, N_CLUSTERS + 1):
    mask = labels == cid
    # Short name for legend: "C1" etc.
    ax_pca.scatter(
        pca_coords[mask, 0],
        pca_coords[mask, 1],
        c=colors_hc[cid - 1],
        marker=markers_hc[cid - 1],
        s=18,
        alpha=0.65,
        edgecolors="none",
        label=f"C{cid}",
    )

ax_pca.set_xlabel(f"PC1 ({var_explained[0] * 100:.1f}%)")
ax_pca.set_ylabel(f"PC2 ({var_explained[1] * 100:.1f}%)")
ax_pca.set_title("(b) PCA biplot", fontsize=10, fontweight="bold", loc="left")
ax_pca.axhline(y=0, color="k", linestyle="--", linewidth=0.3, alpha=0.3)
ax_pca.axvline(x=0, color="k", linestyle="--", linewidth=0.3, alpha=0.3)
ax_pca.legend(
    title="Cluster",
    fontsize=6,
    title_fontsize=7,
    ncol=5,
    loc="upper right",
    framealpha=0.85,
    markerscale=1.5,
    handletextpad=0.2,
    columnspacing=0.4,
)
ax_pca.grid(alpha=0.15, linestyle="--")

fig.tight_layout()
fig.savefig(IMAGE_DIR / "fig_cluster_pca.png", dpi=300, bbox_inches="tight")
plt.show()
print("Saved: fig_cluster_pca.png")

# ══════════════════════════════════════════════════════════════════════════════
# FIGURE 3 — Cluster spatial map  (Section 7.3, no borders)
# ══════════════════════════════════════════════════════════════════════════════

fig, ax = plt.subplots(figsize=(7.5, 4.5))

for cid in range(1, N_CLUSTERS + 1):
    subset = gauge_filtered[gauge_filtered["cluster"] == cid]
    ax.scatter(
        subset.geometry.x,
        subset.geometry.y,
        c=colors_hc[cid - 1],
        marker=markers_hc[cid - 1],
        s=14,
        alpha=0.7,
        edgecolors="none",
        label=f"C{cid} (n={cluster_sizes[cid]})",
    )

ax.set_xlabel("Longitude (\u00b0E)")
ax.set_ylabel("Latitude (\u00b0N)")
ax.set_title(
    f"Spatial distribution of catchment clusters (k={N_CLUSTERS}, n={len(gauge_filtered)})",
    fontsize=10,
    fontweight="bold",
    loc="left",
)
# Latitude-corrected aspect (cos(55deg) for Russia's center latitude)
ax.set_aspect(1.0 / np.cos(np.radians(55)))
ax.grid(alpha=0.15, linestyle="--")

# Compact legend: "C1 (n=228)" etc. — full cluster names in LaTeX caption
# Place inside plot in lower-right where point density is lowest
ax.legend(
    fontsize=5.5,
    ncol=5,
    loc="lower right",
    framealpha=0.9,
    markerscale=1.5,
    handletextpad=0.2,
    columnspacing=0.5,
    edgecolor="0.8",
)

fig.savefig(IMAGE_DIR / "fig_cluster_map.png", dpi=300, bbox_inches="tight")
plt.show()
print("Saved: fig_cluster_map.png")

# ══════════════════════════════════════════════════════════════════════════════
# EXPORT TABLES
# ══════════════════════════════════════════════════════════════════════════════

# Cluster assignments per gauge
assign_df = pd.DataFrame(
    {
        "gauge_id": hydro_scaled.index,
        "cluster_id": labels,
        "cluster_name": [cluster_names[c] for c in labels],
        "silhouette": sil_per_sample,
    }
)
assign_df.to_csv(TABLE_DIR / "cluster_assignments.csv", index=False)

# Centroids
centroids_norm.to_csv(TABLE_DIR / "cluster_centroids_norm.csv")
centroids_raw.to_csv(TABLE_DIR / "cluster_centroids_raw.csv")

print(f"\nExported to {TABLE_DIR}:")
print(f"  cluster_assignments.csv  ({len(assign_df)} gauges)")
print(f"  cluster_centroids_norm.csv  ({N_CLUSTERS} × {len(features)})")
print(f"  cluster_centroids_raw.csv   ({N_CLUSTERS} × {len(features)})")
print(f"\nAll figures saved to {IMAGE_DIR}")
