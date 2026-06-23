"""Intersection of the 15 hydrograph regimes with the HDBSCAN physiographic end-members.

Joins the *behavioural* classification (seasonal-hydrograph Ward regimes, from
``regenerate_regime_figures.py`` -> ``paper/tables/regime_assignments.csv``) with the
*physiographic* typology (HDBSCAN attribute end-members + an unclassified continuum, from
``cluster_endmembers.py`` -> ``paper/tables/endmember_assignments.csv``) on ``gauge_id``,
then renders one 3-panel figure:

  (a) cross-tabulation heatmap   regime x end-member, coloured by within-regime fraction,
                                 raw counts annotated; title carries the adjusted Rand index
  (b) joint-class map            the most populated regime ∩ end-member types, in space
  (c) agreement map              catchments whose physiography matches the modal end-member
                                 of their regime (concordant) vs not (discordant), vs the
                                 unclassified physiographic continuum

The headline number is the adjusted Rand index (ARI) between the two partitions: a low ARI
means hydrological behaviour and physiographic attributes carve the domain differently, so
attribute-based regionalization will misfit catchments whose regime does not follow their
attributes -- the cold-region caution of Sect. 4 made explicit.

Output: paper/images/fig_regime_endmember_intersection.png  (with --write; else .tmp/)
Inputs: paper/tables/regime_assignments.csv, paper/tables/endmember_assignments.csv,
        data/CAMELS_RU/geometry/camels_gauges.gpkg

Usage: pixi run python scripts/regime_endmember_intersection.py [--write]
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
import pandas as pd
from sklearn.metrics import adjusted_rand_score

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))
from src.plots.paper_maps import _set_extent_from_data, get_russia_projection  # noqa: E402

GEOM_DIR = PROJECT_ROOT / "data" / "CAMELS_RU" / "geometry"
TABLE_DIR = PROJECT_ROOT / "paper" / "tables"
REGIME_CSV = TABLE_DIR / "regime_assignments.csv"
ENDMEMBER_CSV = TABLE_DIR / "endmember_assignments.csv"

# Distinct colours for the top joint (regime ∩ end-member) classes on panel (b).
_JOINT_PALETTE = [
    "#e6194B",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
    "#f032e6",
    "#9A6324",
]
N_TOP_JOINT = 8

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"]})


def load_partitions() -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Join the regime and end-member labels on gauge_id; return (df, gauges)."""
    if not REGIME_CSV.exists():
        sys.exit(
            f"Missing {REGIME_CSV}; run: pixi run python scripts/regenerate_regime_figures.py --write"
        )
    if not ENDMEMBER_CSV.exists():
        sys.exit(f"Missing {ENDMEMBER_CSV}; run: pixi run python scripts/cluster_endmembers.py")

    regime = pd.read_csv(REGIME_CSV, dtype={"gauge_id": str}).set_index("gauge_id")["regime"]
    em = pd.read_csv(ENDMEMBER_CSV, dtype={"gauge_id": str}).set_index("gauge_id")
    df = pd.DataFrame({"regime": regime}).join(em[["end_member", "end_member_name"]], how="inner")

    gauge = gpd.read_file(GEOM_DIR / "camels_gauges.gpkg")
    gauge["gauge_id"] = gauge["gauge_id"].astype(str)
    gauge = gauge.set_index("gauge_id")
    df = df.loc[df.index.intersection(gauge.index)]
    return df, gauge.loc[df.index]


def compute_stats(df: pd.DataFrame) -> dict:
    """ARI, per-regime modal end-member, and concordance fraction (classified gauges only)."""
    classified = df[df["end_member"] != -1]
    ari = float(adjusted_rand_score(classified["regime"], classified["end_member"]))
    modal = classified.groupby("regime")["end_member"].agg(lambda s: s.mode().iloc[0])
    concordant = classified.apply(lambda r: r["end_member"] == modal[r["regime"]], axis=1)
    return {
        "n_total": len(df),
        "n_classified": len(classified),
        "n_continuum": int((df["end_member"] == -1).sum()),
        "ari": ari,
        "modal": modal,
        "concordant_frac": float(concordant.mean()),
        "n_endmembers": int(classified["end_member"].nunique()),
    }


def plot_heatmap(ax, df: pd.DataFrame, ari: float) -> None:
    """Regime x end-member contingency, coloured by within-regime fraction, counts annotated."""
    ct = pd.crosstab(df["regime"], df["end_member_name"])
    # order columns by total size; force the continuum column last
    cont = "Unclassified"
    cols = [c for c in ct.sum().sort_values(ascending=False).index if c != cont]
    if cont in ct.columns:
        cols = cols + [cont]
    ct = ct[cols]
    frac = ct.div(ct.sum(axis=1), axis=0)  # within-regime fraction -> colour

    im = ax.imshow(frac.values, aspect="auto", cmap="magma_r", vmin=0, vmax=1)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(ct.index)))
    ax.set_yticklabels([f"Regime {r}" for r in ct.index], fontsize=8)
    ax.set_xlabel("Physiographic end-member", fontsize=10)
    ax.set_ylabel("Hydrograph regime", fontsize=10)
    for i in range(ct.shape[0]):
        for j in range(ct.shape[1]):
            n = ct.values[i, j]
            if n:
                ax.text(
                    j,
                    i,
                    str(n),
                    ha="center",
                    va="center",
                    fontsize=6.5,
                    color="white" if frac.values[i, j] > 0.5 else "#333333",
                )
    cb = ax.figure.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.set_label("Within-regime fraction", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    ax.set_title(
        f"(a) Regime $\\times$ end-member cross-tabulation "
        f"(adjusted Rand index = {ari:.2f}: behaviour and physiography only partly align)",
        fontsize=10,
    )


def _basemap(ax, gauge: gpd.GeoDataFrame) -> ccrs.CRS:
    """Shared Albers basemap setup for the two map panels."""
    aea = get_russia_projection()
    ax.axis("off")
    _set_extent_from_data(ax, gauge)
    ne = gpd.read_file(GEOM_DIR / "ne_land_clipped.gpkg").to_crs(aea.proj4_init)
    ne.plot(ax=ax, color="#EDEDED", edgecolor="#CCCCCC", linewidth=0.3, zorder=1)
    return ccrs.PlateCarree()


def plot_joint_map(ax, df: pd.DataFrame, gauge: gpd.GeoDataFrame) -> None:
    """Map the most populated regime ∩ end-member joint classes; the rest in grey."""
    data_crs = _basemap(ax, gauge)
    classified = df[df["end_member"] != -1].copy()
    classified["pair"] = [
        f"R{r} ∩ {n}" for r, n in zip(classified["regime"], classified["end_member_name"], strict=True)
    ]
    top = classified["pair"].value_counts().head(N_TOP_JOINT).index.tolist()

    rest = df.index.difference(classified.index[classified["pair"].isin(top)])
    g_rest = gauge.loc[rest]
    ax.scatter(
        g_rest.geometry.x,
        g_rest.geometry.y,
        s=4,
        c="#DcDcDc",
        edgecolors="none",
        zorder=2,
        transform=data_crs,
    )
    handles = []
    for i, pair in enumerate(top):
        ids = classified.index[classified["pair"] == pair]
        g = gauge.loc[ids]
        col = _JOINT_PALETTE[i % len(_JOINT_PALETTE)]
        ax.scatter(
            g.geometry.x,
            g.geometry.y,
            s=12,
            c=col,
            edgecolors="white",
            linewidths=0.2,
            alpha=0.9,
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
                label=f"{pair} (n={len(ids)})",
            )
        )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        fontsize=7,
        framealpha=0.9,
        ncol=2,
        columnspacing=1.0,
        handletextpad=0.3,
    )
    ax.set_title(f"(b) Largest joint regime $\\cap$ end-member types ({N_TOP_JOINT} shown)", fontsize=10)


def plot_agreement_map(ax, df: pd.DataFrame, gauge: gpd.GeoDataFrame, stats: dict) -> None:
    """Concordant (physiography = regime's modal end-member) vs discordant vs continuum."""
    data_crs = _basemap(ax, gauge)
    modal = stats["modal"]

    def status(row: pd.Series) -> str:
        if row["end_member"] == -1:
            return "continuum"
        return "concordant" if row["end_member"] == modal[row["regime"]] else "discordant"

    cat = df.apply(status, axis=1)
    styles = {
        "concordant": ("#117733", 11, f"Concordant (n={int((cat == 'concordant').sum())})"),
        "discordant": ("#CC6677", 11, f"Discordant (n={int((cat == 'discordant').sum())})"),
        "continuum": ("#BBBBBB", 5, f"Unclassified continuum (n={int((cat == 'continuum').sum())})"),
    }
    handles = []
    for key in ("continuum", "discordant", "concordant"):  # continuum first = drawn underneath
        col, size, lab = styles[key]
        g = gauge.loc[df.index[cat == key]]
        ax.scatter(
            g.geometry.x,
            g.geometry.y,
            s=size,
            c=col,
            edgecolors="none" if key == "continuum" else "white",
            linewidths=0.2,
            alpha=0.85,
            zorder=2 if key == "continuum" else 3,
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
                label=lab,
            )
        )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        fontsize=7.5,
        framealpha=0.9,
        ncol=1,
        handletextpad=0.3,
    )
    ax.set_title(
        f"(c) Behaviour--physiography agreement "
        f"({stats['concordant_frac']:.0%} of classified gauges concordant)",
        fontsize=10,
    )


def main(write: bool) -> None:
    """Join the partitions, compute the agreement statistics, render the 3-panel figure."""
    df, gauge = load_partitions()
    stats = compute_stats(df)

    aea = get_russia_projection()
    fig = plt.figure(figsize=(15, 13))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.05, 1.0], hspace=0.28, wspace=0.06)
    ax_heat = fig.add_subplot(gs[0, :])
    ax_joint = fig.add_subplot(gs[1, 0], projection=aea)
    ax_agree = fig.add_subplot(gs[1, 1], projection=aea)

    plot_heatmap(ax_heat, df, stats["ari"])
    plot_joint_map(ax_joint, df, gauge)
    plot_agreement_map(ax_agree, df, gauge, stats)

    dest = (PROJECT_ROOT / "paper" / "images") if write else (PROJECT_ROOT / ".tmp" / "cluster_diag")
    dest.mkdir(parents=True, exist_ok=True)
    suffix = "" if write else "_test"
    out = dest / f"fig_regime_endmember_intersection{suffix}.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")

    print("\n" + "=" * 64)
    print("REGIME x END-MEMBER INTERSECTION (values for sections/04_regimes_signatures.tex):")
    print(f"  - gauges in both partitions: {stats['n_total']:,}")
    print(
        f"  - classified (end-member) : {stats['n_classified']:,} ({stats['n_endmembers']} end-members)"
    )
    print(f"  - unclassified continuum  : {stats['n_continuum']:,}")
    print(f"  - adjusted Rand index     : {stats['ari']:.2f}")
    print(f"  - concordant fraction     : {stats['concordant_frac']:.0%}")
    print("=" * 64)


if __name__ == "__main__":
    main(write="--write" in sys.argv)
