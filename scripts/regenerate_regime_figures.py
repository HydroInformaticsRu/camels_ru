"""Regenerate both seasonal-hydrograph regime figures from current release data.

Standalone replacement for the regime cells of notebooks/02 (whose original
discharge folders no longer exist). Reconstructs NB02's recipe from the canonical
release discharge (camels_ru_discharge.nc -> discharge_mm, the mm/day variable
NB02 used) and regenerates BOTH regime figures from one clustering so they stay
consistent:

    paper/images/hydrograph_clusters_15.png   per-regime normalised hydrographs
    paper/images/hydro_clusters_15_map.png     spatial map (Albers, no borders)

Recipe (NB02): per-gauge median (month, day) seasonal cycle of discharge_mm;
drop gauges with seasonal max >= 50 mm/day; min-max normalise each gauge to
[0,1]; append min-max-normalised lat/lon; Ward linkage (Euclidean) cut at 15.
Regimes are renumbered by descending size (regime 1 = largest) so figure labels
and the "largest regimes" reference are stable.

NOTE 1: coordinates are min-max-normalised, per the manuscript (Sect. 4). NB02's
code appended RAW lat/lon, which let longitude (range ~141) dominate the 366
[0,1] shape features and made the "regime" clustering ~spatial (ARI 0.64 vs
coords-only, 0.15 vs shape-only) -- contradicting the stated shape-based method.
The fix restores a genuinely shape-driven clustering (ARI 0.70 vs shape-only).

NOTE 2: the current release yields ~1,700 gauges, not the 1,443 of the retired
"decent"-folder pipeline, so this clustering supersedes the committed figures.
Manuscript numbers to update are printed at the end. Default writes to .tmp;
pass --write to emit into paper/images/.
"""

from __future__ import annotations

from pathlib import Path
import sys

import cartopy.crs as ccrs
import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
import xarray as xr

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))
from src.plots.paper_maps import _set_extent_from_data, get_russia_projection  # noqa: E402

GEOM_DIR = PROJECT_ROOT / "data" / "CAMELS_RU" / "geometry"
DISCHARGE_NC = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_discharge.nc"
N_CLUSTERS = 15
AREA_LIMIT_KM2 = 50_000
MAX_SEASONAL_MM_DAY = 50

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"]})


def build_seasonal_matrix() -> tuple[pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame]:
    """Return (clustering matrix [gauge x days+coords], normalised seasonal [day x gauge], gauges)."""
    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg").set_index("gauge_id")
    ws.index = ws.index.astype(str)
    area_col = "area_km2" if "area_km2" in ws.columns else "area"
    ws = ws.loc[ws[area_col] < AREA_LIMIT_KM2]

    gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg").set_index("gauge_id")
    gauge.index = gauge.index.astype(str)

    ds = xr.open_dataset(DISCHARGE_NC)
    q = ds["discharge_mm"].to_pandas().T
    q.columns = q.columns.astype(str)
    q = q[[g for g in ws.index if g in q.columns and g in gauge.index]]
    q.index = pd.to_datetime(q.index)

    seasonal = q.groupby([q.index.month, q.index.day]).median()
    seasonal = seasonal.dropna(axis=1, how="all")
    seasonal = seasonal.loc[:, seasonal.max() < MAX_SEASONAL_MM_DAY]
    norm = (seasonal - seasonal.min()) / (seasonal.max() - seasonal.min())

    clust = norm.T.copy()
    lat = np.array([gauge.loc[g, "geometry"].y for g in clust.index])
    lon = np.array([gauge.loc[g, "geometry"].x for g in clust.index])
    # min-max-normalise coordinates to [0,1] (manuscript Sect. 4): they then act as a
    # gentle spatial-coherence penalty rather than dominating the Euclidean distance.
    # NB02's code appended RAW lat/lon, which made the clustering ~spatial (ARI 0.64
    # vs coords-only, 0.15 vs shape-only) and contradicted the stated shape-based method.
    clust["lat"] = (lat - lat.min()) / (lat.max() - lat.min())
    clust["lon"] = (lon - lon.min()) / (lon.max() - lon.min())
    clust = clust.dropna()
    norm = norm[clust.index]
    return clust, norm, gauge


def cluster_by_size(clust: pd.DataFrame) -> pd.Series:
    """Ward + fcluster, then renumber 1..K by descending member count."""
    z = linkage(clust.values, method="ward", metric="euclidean")
    raw = fcluster(z, t=N_CLUSTERS, criterion="maxclust")
    order = pd.Series(raw).value_counts().index.tolist()  # largest first
    remap = {old: new for new, old in enumerate(order, start=1)}
    return pd.Series([remap[v] for v in raw], index=clust.index, name="regime")


def plot_map(gauge: gpd.GeoDataFrame, labels: pd.Series, out: Path) -> None:
    """Albers Equal-Area Conic regime map in the standard paper-map style."""
    gdf = gauge.loc[labels.index].copy()
    gdf["regime"] = labels.values
    aea = get_russia_projection()
    data_crs = ccrs.PlateCarree()
    cmap = plt.get_cmap("tab20", N_CLUSTERS)

    fig = plt.figure(figsize=(9.0, 5.5))
    ax = fig.add_subplot(1, 1, 1, projection=aea)
    ax.axis("off")
    _set_extent_from_data(ax, gdf)
    ne = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    ne.to_crs(aea.proj4_init).plot(ax=ax, color="#EDEDED", edgecolor="#CCCCCC", linewidth=0.3, zorder=1)

    handles = []
    for c in range(1, N_CLUSTERS + 1):
        sub = gdf[gdf["regime"] == c]
        col = cmap(c - 1)
        ax.scatter(
            sub.geometry.x,
            sub.geometry.y,
            s=10,
            color=col,
            alpha=0.85,
            edgecolors="white",
            linewidths=0.2,
            zorder=3,
            transform=data_crs,
        )
        handles.append(
            Line2D(
                [],
                [],
                marker="o",
                color="none",
                markerfacecolor=col,
                markersize=6,
                linestyle="None",
                label=f"Regime {c} (n={len(sub)})",
            )
        )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        fontsize=7.5,
        framealpha=0.9,
        ncol=5,
        columnspacing=1.0,
        handletextpad=0.3,
    )
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def plot_hydrographs(norm: pd.DataFrame, labels: pd.Series, out: Path) -> None:
    """3x5 grid of per-regime normalised seasonal hydrographs (faint gauges + median)."""
    fig, axes = plt.subplots(3, 5, figsize=(20, 10))
    axes = axes.flatten()
    day = np.arange(norm.shape[0])
    for c in range(1, N_CLUSTERS + 1):
        ax = axes[c - 1]
        members = labels.index[labels == c]
        sub = norm[members]
        for g in sub.columns:
            ax.plot(day, sub[g].to_numpy(), color="#4477AA", alpha=0.2, linewidth=0.5)
        ax.plot(
            day, sub.median(axis=1).to_numpy(), color="crimson", linewidth=2.5, label="Regime median"
        )
        ax.set_xlim(0, 365)
        ax.set_ylim(0, 1)
        ax.set_yticks(np.arange(0, 1.25, 0.25))
        ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))
        ax.grid(alpha=0.3)
        if (c - 1) % 5 == 0:
            ax.set_ylabel("Normalised runoff [0-1]")
        if c - 1 >= 10:
            ax.set_xlabel("Day of year")
        ax.set_title(f"Regime {c} — {len(members)} gauges", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def main(write: bool) -> None:
    """Build the clustering and regenerate both regime figures consistently."""
    clust, norm, gauge = build_seasonal_matrix()
    labels = cluster_by_size(clust)
    sizes = labels.value_counts().sort_index()
    n = len(labels)

    img = PROJECT_ROOT / "paper" / "images"
    tmp = PROJECT_ROOT / ".tmp" / "cluster_diag"
    dest = img if write else tmp
    dest.mkdir(parents=True, exist_ok=True)
    suffix = "" if write else "_test"
    plot_map(gauge, labels, dest / f"hydro_clusters_15_map{suffix}.png")
    plot_hydrographs(norm, labels, dest / f"hydrograph_clusters_15{suffix}.png")

    print("\n" + "=" * 64)
    print("MANUSCRIPT NUMBERS TO UPDATE (sections/04_regimes_signatures.tex):")
    print(f"  - gauge count entering classification: 1,443  ->  {n:,}")
    big3 = sizes.sort_values(ascending=False).head(3)
    print(
        f"  - 'Clusters 1, 5, and 6 are the largest' -> 'Regimes 1, 2, and 3' "
        f"(now the 3 largest by construction: n={big3.tolist()})"
    )
    print(f"  - per-regime sizes (regime: n): {sizes.to_dict()}")
    print("=" * 64)


if __name__ == "__main__":
    main(write="--write" in sys.argv)
