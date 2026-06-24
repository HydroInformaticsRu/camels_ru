"""Physiographic catchment end-members for the CAMELS-RU supplementary material.

Replaces the earlier forced k=15 Ward attribute clustering (silhouette 0.194),
which imposed discrete classes on what is, in fact, a continuum. Multi-paradigm
diagnostics (gap statistic, Hopkins, cross-scaler ARI, HDBSCAN noise fraction)
showed Russian catchment attribute-space is a continuum with a few dense
end-members rather than well-separated clusters.

This script therefore detects *end-members* by density (HDBSCAN) and leaves the
diffuse majority explicitly *unclassified*, instead of partitioning everything:

    physiographic+climate attributes (socioeconomic/sparse dropped)
        -> quantile transform (robust to zero-inflation)
        -> PCA (90% variance)
        -> HDBSCAN(min_cluster_size=40)  -> 16 end-members + ~15% continuum

Outputs (all tracked, regenerable on a fresh clone with data/ mounted):
    paper/images/fig_endmember_map.png        Albers map, end-members + continuum
    paper/tables/endmember_summary.tex        LaTeX summary table
    paper/tables/endmember_assignments.csv    per-gauge end-member label
    paper/tables/endmember_profiles.csv       per-end-member attribute profile

Usage:
    pixi run python scripts/cluster_endmembers.py
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
import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import QuantileTransformer

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))
from src.plots.paper_maps import _set_extent_from_data, get_russia_projection  # noqa: E402
from src.static.hydro_atlas_analysis import (  # noqa: E402
    CORRELATED_DROPS,
    filter_hydroatlas_features,
)
from src.utils.paper_analysis_scope import (  # noqa: E402
    filter_paper_analysis_index,
)

DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
GEOM_DIR = DATA_DIR / "geometry"
ATTR_PATH = DATA_DIR / "attributes" / "hydro_atlas_cis_camels.csv"
IMAGE_DIR = PROJECT_ROOT / "paper" / "images"
TABLE_DIR = PROJECT_ROOT / "paper" / "tables"

AREA_LIMIT_KM2 = 50_000
MIN_CLUSTER_SIZE = 40  # -> 16 end-members + ~15% unclassified continuum
#                        (HDBSCAN density hierarchy has no stable 15-cut; 40->16,
#                         41->14. 16 is the nearest cut to the chosen ~15 tier.)
SEED = 0

# Socioeconomic / heavily zero-inflated attributes: management signals and sparse
# fields that inject noise into a *physiographic* typology. Dropped by design.
SOCIO_OR_SPARSE = [
    "gdp_ud_sav",  # GDP
    "urb_pc_use",  # urban extent
    "ire_pc_use",  # irrigated cropland
    "gla_pc_use",  # glacier (97% zeros)
    "pac_pc_use",  # protected area
    "ppd_pk_uav",  # population density
]

# Priority order for naming an end-member from its standout (high) z-score attrs.
_NAME_PRIORITY = {
    "prm_pc_use": "Permafrost",
    "snw_pc_uyr": "Snow",
    "ele_mt_uav": "Highland",
    "kar_pc_use": "Karst",
    "lka_pc_use": "Lake",
    "inu_pc_ult": "Inundated",
    "gwt_cm_sav": "Deep-GW",
    "pre_mm_uyr": "Humid",
    "aet_mm_uyr": "High-ET",
    "pet_mm_uyr": "High-PET",
    "for_pc_use": "Forested",
    "crp_pc_use": "Cropland",
    "pst_pc_use": "Pasture",
    "cly_pc_uav": "Clay",
    "slt_pc_uav": "Silty",
    "snd_pc_uav": "Sandy",
}

# Human-readable raw-attribute columns for the summary table.
_TABLE_ATTRS = {
    "ele_mt_uav": "Elev. (m)",
    "pre_mm_uyr": "Precip. (mm/yr)",
    "snw_pc_uyr": "Snow (%)",
    "prm_pc_use": "Perm. (%)",
    "for_pc_use": "Forest (%)",
    "crp_pc_use": "Crop (%)",
    "kar_pc_use": "Karst (%)",
}

# Hand-reviewed final end-member names, overriding the auto-generated placeholders
# (keyed by the deterministic auto-name). Each was checked against the per-end-member
# attribute standouts so no label leads with an attribute that is not actually elevated;
# approved 2026-06-24. Auto-names not listed here are kept verbatim.
FINAL_NAMES = {
    "High-PET / Cropland (pasture)": "Cropland / Pasture",
    "Karst / Lake": "Karst (lowland)",
    "Highland / Karst (high-et)": "Upland (high-AET)",
    "Permafrost / Snow (karst, highland)": "Permafrost / Snow (upland karst)",
    "High-PET / Cropland": "Cropland (high-PET)",
    "Permafrost / Snow": "Permafrost / Snow (highland)",
    "Karst / High-ET": "Karst (high-PET)",
    "Inundated / Forested": "Floodplain (sandy)",
    "Highland / Deep-GW": "Highland / Pasture",
    "High-ET / High-PET": "Lowland (diffuse)",
    "Permafrost / Snow (karst)": "Karst / Forest (upland)",
    "Highland / Karst": "Alpine karst",
    "Humid / High-ET": "Humid / Forested",
    "Permafrost / Snow (forested)": "Snow / Forest (karst)",
    # kept verbatim: "Permafrost / Snow (lake)", "Permafrost / Snow (sandy)"
}


def load_features() -> tuple[pd.DataFrame, list[str]]:
    """Load the physiographic+climate attribute matrix for the paper-analysis scope."""
    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg").set_index("gauge_id")
    ws.index = ws.index.astype(str)
    ws = filter_paper_analysis_index(ws)
    ws = ws.loc[ws["area_km2"] < AREA_LIMIT_KM2]

    hydro = pd.read_csv(ATTR_PATH, index_col="gauge_id", dtype={"gauge_id": str})
    idx = ws.index.intersection(hydro.index)

    subset, _ = filter_hydroatlas_features(hydro, idx)
    subset = subset.drop(columns=[c for c in CORRELATED_DROPS if c in subset.columns])
    subset = subset.drop(columns=[c for c in SOCIO_OR_SPARSE if c in subset.columns])
    features = subset.columns.tolist()
    subset = subset.fillna(subset.median())
    print(f"Gauges: {len(subset)}  physiographic features: {len(features)}")
    return subset, features


def name_end_member(zrow: pd.Series, used: set[str]) -> str:
    """Auto-generate a placeholder end-member name from its standout attributes.

    Top-2 standout attributes (canonical order) plus a parenthetical qualifier
    when a sibling already took that pair. These are deterministic starting
    points, not final labels — the table carries the raw attribute medians so the
    names can be revised by hand.
    """
    standout = [k for k in zrow[zrow > 0.2].index if k in _NAME_PRIORITY]
    by_priority = sorted(standout, key=lambda k: list(_NAME_PRIORITY).index(k))
    base = [_NAME_PRIORITY[k] for k in by_priority[:2]] or ["Mixed"]
    name = " / ".join(base)
    if name in used:
        # disambiguate with the most distinctive extra attributes (highest z),
        # adding a second qualifier if one is not enough to separate siblings
        extras = [
            _NAME_PRIORITY[k]
            for k in zrow.sort_values(ascending=False).index
            if k in _NAME_PRIORITY and _NAME_PRIORITY[k] not in base and zrow[k] > 0.2
        ]
        for take in (1, 2):
            if extras:
                name = f"{' / '.join(base)} ({', '.join(e.lower() for e in extras[:take])})"
            if name not in used:
                break
    suffix = 2
    stem = name
    while name in used:  # final guard: numeric suffix, never a stray glyph
        name = f"{stem} #{suffix}"
        suffix += 1
    used.add(name)
    return name


def cluster(subset: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Quantile -> PCA(90%) -> HDBSCAN. Returns (labels, probs, silhouette, stability)."""
    xq = QuantileTransformer(
        output_distribution="normal", random_state=SEED, n_quantiles=500
    ).fit_transform(subset[features].values)
    xp = PCA(n_components=0.90, random_state=SEED).fit_transform(xq)
    hdb = HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE).fit(xp)
    labels = hdb.labels_
    core = labels != -1
    sil = float(silhouette_score(xp[core], labels[core])) if core.sum() else float("nan")

    # resampling stability (ARI on co-clustered points)
    rng = np.random.default_rng(SEED)
    aris = []
    for _ in range(20):
        pick = rng.choice(len(xp), int(0.85 * len(xp)), replace=False)
        sub = HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE).fit_predict(xp[pick])
        both = (sub != -1) & (labels[pick] != -1)
        if both.sum() > 50:
            aris.append(adjusted_rand_score(labels[pick][both], sub[both]))
    n_em = len(set(labels)) - (1 if -1 in labels else 0)
    print(
        f"HDBSCAN(min_cluster_size={MIN_CLUSTER_SIZE}): {n_em} end-members, "
        f"{(labels == -1).mean():.0%} unclassified | silhouette(cores)={sil:.3f} "
        f"| stability ARI={np.mean(aris):.3f}±{np.std(aris):.3f}"
    )
    return labels, hdb.probabilities_, sil, float(np.mean(aris))


def build_profiles(subset, features, labels, probs) -> pd.DataFrame:
    """Per-end-member: name, n, mean membership, raw-attribute medians."""
    z = (subset[features] - subset[features].mean()) / subset[features].std()
    z["lab"] = labels
    used: set[str] = set()
    rows = []
    for c in sorted(x for x in set(labels) if x != -1):
        zmean = z[z["lab"] == c][features].mean()
        rows.append(
            {
                "end_member": int(c),
                "name": name_end_member(zmean, used),
                "n": int((labels == c).sum()),
                "mean_membership": round(float(probs[labels == c].mean()), 3),
                **{a: round(float(subset.loc[labels == c, a].median()), 1) for a in _TABLE_ATTRS},
            }
        )
    df = pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)
    return df


def write_table(profiles: pd.DataFrame, n_uncl: int, sil: float, stability: float) -> None:
    """LaTeX summary table (supersedes geo_clusters_summary.tex)."""
    cols = list(_TABLE_ATTRS)
    header = (
        "ID & End-member & N & Memb. & "
        + " & ".join(_TABLE_ATTRS[c].replace("%", "\\%") for c in cols)
        + " \\\\"
    )
    lines = [
        "\\begin{table*}[htbp]",
        "\\centering",
        "\\caption{Physiographic catchment end-members of CAMELS-RU detected by "
        "density-based clustering (HDBSCAN) of quantile-transformed HydroATLAS "
        "attributes. Values are per-end-member medians. ``Memb.'' is the mean HDBSCAN "
        "membership probability of the end-member's gauges (1 = core). A further "
        f"{n_uncl} gauges form an unclassified continuum (no robust end-member).}}",
        "\\label{tab:endmembers}",
        "\\small",
        "\\begin{tabular}{clrr" + "r" * len(cols) + "}",
        "\\toprule",
        header,
        "\\midrule",
    ]
    for i, r in profiles.iterrows():
        vals = " & ".join(f"{r[c]:g}" for c in cols)
        lines.append(f"{i + 1} & {r['name']} & {r['n']} & {r['mean_membership']:.2f} & {vals} \\\\")
    lines += [
        "\\midrule",
        f"-- & Unclassified continuum & {n_uncl} & -- & " + " & ".join("--" for _ in cols) + " \\\\",
        "\\bottomrule",
        "\\end{tabular}",
        "\\begin{tablenotes}",
        "\\item Pipeline: 16 physiographic+climate attributes (socioeconomic/sparse "
        "fields excluded) $\\rightarrow$ quantile transform $\\rightarrow$ PCA (90\\% "
        f"variance) $\\rightarrow$ HDBSCAN (min\\_cluster\\_size = {MIN_CLUSTER_SIZE}).",
        f"\\item Mean silhouette of end-member cores = {sil:.2f}; resampling stability "
        f"(adjusted Rand index, 20$\\times$ at 85\\%) = {stability:.2f}. The attribute "
        "space is a continuum: a forced k-way partition is not supported (see Supplement), "
        "so the diffuse majority is reported as unclassified rather than assigned.",
        "\\end{tablenotes}",
        "\\end{table*}",
    ]
    (TABLE_DIR / "endmember_summary.tex").write_text("\n".join(lines) + "\n")
    print(f"Wrote {TABLE_DIR / 'endmember_summary.tex'}")


def write_map(subset, labels, profiles) -> None:
    """Albers Equal-Area Conic map matching the gauge-network figure style."""
    gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
    gauge["gauge_id"] = gauge["gauge_id"].astype(str)
    gauge = gauge.set_index("gauge_id").loc[subset.index].reset_index()
    gauge["lab"] = labels

    aea = get_russia_projection()
    data_crs = ccrs.PlateCarree()
    # 8 maximally-distinct hues x marker shape -> 24 unique (colour, marker) keys, so the
    # 16 end-members never collide. The previous 10-colour list was indexed `i % len`, which
    # wrapped and gave 6 end-members a colour identical to another's (illegible legend).
    palette = [
        "#E6194B",  # red
        "#4363D8",  # blue
        "#3CB44B",  # green
        "#F58231",  # orange
        "#911EB4",  # purple
        "#F032E6",  # magenta
        "#9A6324",  # brown
        "#42D4F4",  # cyan
    ]
    markers = ["o", "^", "s"]  # circle / triangle / square -> shape disambiguates re-used hues

    fig = plt.figure(figsize=(9.0, 5.5))
    ax = fig.add_subplot(1, 1, 1, projection=aea)
    ax.axis("off")
    _set_extent_from_data(ax, gauge)
    ne = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg")
    ne.to_crs(aea.proj4_init).plot(ax=ax, color="#EDEDED", edgecolor="#CCCCCC", linewidth=0.3, zorder=1)

    uncl = gauge[gauge["lab"] == -1]
    ax.scatter(
        uncl.geometry.x,
        uncl.geometry.y,
        s=3,
        c="#D9D9D9",
        alpha=0.7,
        edgecolors="none",
        zorder=2,
        transform=data_crs,
    )
    handles = []
    for i, r in profiles.iterrows():
        sub = gauge[gauge["lab"] == r["end_member"]]
        col = palette[i % len(palette)]
        mk = markers[i // len(palette)]
        ax.scatter(
            sub.geometry.x,
            sub.geometry.y,
            s=9,
            c=col,
            marker=mk,
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
                marker=mk,
                color="none",
                markerfacecolor=col,
                markersize=7.5,
                linestyle="None",
                label=f"{r['name']} (n={r['n']})",
            )
        )
    handles.append(
        Line2D(
            [],
            [],
            marker="o",
            color="none",
            markerfacecolor="#D9D9D9",
            markersize=6,
            linestyle="None",
            label=f"Unclassified (n={len(uncl)})",
        )
    )
    # legend below the map so it never occludes the dense European cluster
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        fontsize=8.0,
        framealpha=0.9,
        ncol=4,
        columnspacing=1.0,
        handletextpad=0.3,
    )
    fig.savefig(IMAGE_DIR / "fig_endmember_map.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {IMAGE_DIR / 'fig_endmember_map.png'}")


def main() -> None:
    """Run the end-member pipeline and write all tracked artifacts."""
    subset, features = load_features()
    labels, probs, sil, stability = cluster(subset, features)
    profiles = build_profiles(subset, features, labels, probs)
    profiles["name"] = profiles["name"].map(lambda n: FINAL_NAMES.get(n, n))  # hand-reviewed labels
    n_uncl = int((labels == -1).sum())

    print("\nEnd-members (largest first):")
    for _, r in profiles.iterrows():
        print(f"  {r['name']:34s} n={r['n']:4d}  memb={r['mean_membership']:.2f}")
    print(f"  {'Unclassified continuum':34s} n={n_uncl:4d}")

    pd.DataFrame({"gauge_id": subset.index, "end_member": labels}).merge(
        profiles[["end_member", "name"]], on="end_member", how="left"
    ).rename(columns={"name": "end_member_name"}).fillna({"end_member_name": "Unclassified"}).to_csv(
        TABLE_DIR / "endmember_assignments.csv", index=False
    )
    profiles.to_csv(TABLE_DIR / "endmember_profiles.csv", index=False)
    print(f"Wrote {TABLE_DIR / 'endmember_assignments.csv'} + endmember_profiles.csv")

    write_table(profiles, n_uncl, sil, stability)
    write_map(subset, labels, profiles)


if __name__ == "__main__":
    main()
