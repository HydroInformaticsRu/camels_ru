"""Cold-region signature-gradient figure for the CAMELS-RU dataset paper (ESSD).

Builds the Sect. 7 figure. Cold-season yield, measured directly as the winter flow
fraction (mean Jan-Mar flow over mean annual flow, observed days only), declines
monotonically with permafrost extent. The Lyne-Hollick baseflow index does not track it:
with alpha in [0.9, 0.98] the filter has a 10-50 day recession constant, so it reads a
multi-week snowmelt recession as baseflow and instead traces hydrograph smoothness
(rho = -0.93 with q_cv over this subset). Panels (a) and (b) put the two side by side on
identical bins, which is the reusability point: in nival and permafrost regimes the BFI
is not a groundwater-contribution fraction and the winter flow fraction is what
cold-season work needs.

These are descriptive associations between released signatures and HydroATLAS proxies,
not causal permafrost attribution. Gauges are screened on the released winter_coverage
column, because the archive omits under-ice values at many gauges and the ratio is only
as trustworthy as the winter coverage behind it. All numbers derive from the released
CAMELS-RU v1.0 artifacts; no modelling is involved.

Outputs:
    paper/images/fig_coldregion_gradient.pdf
    paper/overleaf/images/fig_coldregion_gradient.pdf
    results/hess_quality/coldregion_gradient_bins.csv
"""

from __future__ import annotations

from pathlib import Path
import shutil

import matplotlib as mpl
from matplotlib.colors import Normalize
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release" / "CAMELS_RU_v1.0"
RESULTS = ROOT / "results" / "hess_quality"
IMG_DIRS = [ROOT / "paper" / "images", ROOT / "paper" / "overleaf" / "images"]

MIN_WINTER_COVERAGE = 0.95  # released winter_coverage: share of Dec-Mar days observed
Y_CLIP_A = 1.2  # panel (a) axis limit; the tail above it is clipped from view, not dropped


# Set type at the final 160 mm publication width.
FS = 8

mpl.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "pdf.fonttype": 42,
        "figure.dpi": 150,
        "savefig.dpi": 400,
        "axes.labelsize": FS,
        "axes.titlesize": FS,
        "xtick.labelsize": FS,
        "ytick.labelsize": FS,
        "legend.fontsize": FS,
    }
)


def load_data() -> pd.DataFrame:
    """Load cleaned, dam-excluded signatures joined to cold-region attributes."""
    sig = pd.read_csv(RELEASE / "camels_ru_signatures.csv")
    sig["gauge_id"] = sig["gauge_id"].astype(str)
    att = pd.read_csv(RELEASE / "camels_ru_attributes.csv")
    att["gauge_id"] = att["gauge_id"].astype(str)
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    summary["gauge_id"] = summary["gauge_id"].astype(str)

    att_cols = ["gauge_id", "dor_pc_pva", "snw_pc_uyr", "prm_pc_use", "tmp_dc_uyr"]
    df = sig.merge(att[att_cols], on="gauge_id", how="inner")
    df = df.merge(summary[["gauge_id", "overall_grade"]], on="gauge_id", how="left")
    # Restrict to high-quality discharge (Grade A and B only), dam-excluded, non-anomalous.
    df = df[
        (~df["is_anomalous"].astype(bool))
        & (df["dor_pc_pva"] == 0)
        & (df["overall_grade"].isin(["A", "B"]))
    ].copy()
    # A winter flow fraction built on a record that omits most of its winters is not a
    # measurement of winter yield, so screen on the coverage column the release ships.
    df = df[(df["winter_coverage"] >= MIN_WINTER_COVERAGE) & df["winter_flow_ratio"].notna()]

    # Optional ERA5-Land water-balance-failure flag for the forcing bridge (panel C).
    aet_path = RESULTS / "aet_per_gauge_product.csv"
    if aet_path.exists():
        aet = pd.read_csv(aet_path)
        aet["gauge_id"] = aet["gauge_id"].astype(str)
        era = aet[aet["product"] == "ERA5-Land"][["gauge_id", "aet_wb_gt_pet"]]
        df = df.merge(era, on="gauge_id", how="left")
    else:
        df["aet_wb_gt_pet"] = np.nan
    return df


def binned_median(x: pd.Series, y: pd.Series, edges: list[float]) -> pd.DataFrame:
    """Median (+IQR, count) of y within bins of x defined by edges."""
    # Area-weighted HydroATLAS percentages can overshoot their nominal range by a float
    # ulp (prm_pc_use maxes at 100.00000000000004), which pd.cut would drop as NaN.
    finite = np.isfinite(x) & np.isfinite(y)
    cats = pd.cut(x[finite].clip(edges[0], edges[-1]), bins=edges, include_lowest=True)
    g = y[finite].groupby(cats, observed=False)
    out = pd.DataFrame(
        {
            "center": [iv.mid for iv in g.median().index],
            "median": g.median().to_numpy(),
            "q25": g.quantile(0.25).to_numpy(),
            "q75": g.quantile(0.75).to_numpy(),
            "n": g.size().to_numpy(),
        }
    )
    return out


def main() -> None:
    """Build and save the cold-region signature-gradient figure (Grade A/B gauges)."""
    df = load_data()
    pf, wff, bfi, snow, temp = (
        df["prm_pc_use"],
        df["winter_flow_ratio"],
        df["baseflow_index"],
        df["snw_pc_uyr"],
        df["tmp_dc_uyr"],
    )
    print(f"n (A/B, dam-excluded, non-anomalous, winter_coverage >= {MIN_WINTER_COVERAGE}) = {len(df)}")
    print("grade counts:", df["overall_grade"].value_counts().to_dict())

    pf_edges = [0, 5, 10, 20, 30, 50, 70, 100]
    wm = binned_median(pf, wff, pf_edges)
    bm = binned_median(pf, bfi, pf_edges)

    # The two signatures move in opposite directions across the same gradient. Report both,
    # because that contrast is the point of the panel pair.
    rho_w, p_w = spearmanr(pf, wff)
    rho_b, p_b = spearmanr(pf, bfi)
    rho_smooth, _ = spearmanr(bfi, df["q_cv"])
    print(f"\nSpearman permafrost vs winter flow ratio: rho={rho_w:.3f} (p={p_w:.2g})")
    print(f"Spearman permafrost vs baseflow index      : rho={rho_b:.3f} (p={p_b:.2g})")
    print(f"Spearman baseflow index vs q_cv            : rho={rho_smooth:.3f}")
    print("\nWinter flow ratio by permafrost bin:")
    print(wm[["center", "median", "n"]].round(3).to_string(index=False))
    print("\nBaseflow index by permafrost bin:")
    print(bm[["center", "median", "n"]].round(3).to_string(index=False))

    fig = plt.figure(figsize=(160 / 25.4, 110 / 25.4))
    grid = fig.add_gridspec(
        3,
        3,
        height_ratios=[2.1, 0.28, 0.80],
        left=0.085,
        right=0.98,
        bottom=0.045,
        top=0.92,
        hspace=0.75,
        wspace=0.50,
    )
    ax_a, ax_b, ax_c = [fig.add_subplot(grid[0, i]) for i in range(3)]

    # ---- Panel A: winter flow fraction vs permafrost -------------------------
    norm = Normalize(vmin=float(temp.min()), vmax=float(temp.max()))
    sc = ax_a.scatter(pf, wff, c=temp, cmap="RdBu_r", norm=norm, s=2.5, alpha=0.55, linewidths=0)
    ax_a.plot(wm["center"], wm["median"], "-o", color="black", lw=1.0, ms=2.5, label="binned median")
    ax_a.fill_between(wm["center"], wm["q25"], wm["q75"], color="black", alpha=0.12, label="IQR")
    # Clip the axis, not the data: a long upper tail (winter flow above the annual mean at
    # spring-fed gauges) would otherwise squash the binned medians into the bottom third.
    n_clipped = int((wff > Y_CLIP_A).sum())
    ax_a.set_ylim(0, Y_CLIP_A)
    print(f"panel (a): {n_clipped} of {len(wff)} points above the {Y_CLIP_A} axis limit")
    ax_a.set_xlabel("Permafrost extent (%)")
    ax_a.set_ylabel("Winter flow ratio")
    ax_a.set_title("(a) Winter flow", loc="left", fontsize=9, pad=5)
    legend_ax = fig.add_subplot(grid[1, 1:])
    legend_ax.axis("off")
    handles, labels = ax_a.get_legend_handles_labels()
    legend_ax.legend(handles, labels, loc="center", ncol=2, frameon=False)
    cax = fig.add_subplot(grid[1, 0])
    cb = fig.colorbar(sc, cax=cax, orientation="horizontal")
    cb.set_label("(a) Mean annual T (°C)", fontsize=FS)
    cb.ax.tick_params(labelsize=FS, length=2)

    # ---- Panel B: the baseflow index over the same bins ----------------------
    ax_b.scatter(pf, bfi, s=2.5, alpha=0.35, color="0.45", linewidths=0)
    ax_b.plot(bm["center"], bm["median"], "-o", color="#b2182b", lw=1.0, ms=2.5, label="binned median")
    ax_b.fill_between(bm["center"], bm["q25"], bm["q75"], color="#b2182b", alpha=0.12, label="IQR")
    ax_b.set_ylim(bottom=0)
    ax_b.set_xlabel("Permafrost extent (%)")
    ax_b.set_ylabel("Baseflow index")
    ax_b.set_title("(b) Baseflow index", loc="left", fontsize=9, pad=5)

    # ---- Panel C: melt timing vs snow cover ----------------------------------
    s_edges = [0, 25, 40, 50, 60, 100]
    hm = binned_median(snow, df["half_flow_date"], s_edges)
    ax_c.plot(hm["center"], hm["median"], "-o", color="#1b7837", lw=1.0, ms=2.5, label="binned median")
    ax_c.fill_between(hm["center"], hm["q25"], hm["q75"], color="#1b7837", alpha=0.15, label="IQR")
    ax_c.set_xlabel("Snow-cover extent (%)")
    ax_c.set_ylabel("Half-flow date (hydrological day)")
    ax_c.set_title("(c) Half-flow date", loc="left", fontsize=9, pad=5)

    # Counts occupy their own aligned row, never the scatter or IQR region.
    for i, bins in enumerate((wm, bm, hm)):
        missing = len(df) - int(bins["n"].sum())
        counts = ", ".join(str(int(n)) for n in bins["n"])
        footer = fig.add_subplot(grid[2, i])
        footer.axis("off")
        detail = (
            f"ρ = {rho_w:+.2f}; off-axis: {n_clipped}"
            if i == 0
            else f"ρ = {rho_b:+.2f}"
            if i == 1
            else "Day 1 = 1 October"
        )
        footer.text(
            0,
            1,
            f"{detail}\n"
            f"Finite: {int(bins['n'].sum()):,}; missing: {missing}\n"
            f"Bin n, left to right:\n{counts}",
            va="top",
            fontsize=FS,
            linespacing=1.6,
        )
        bins["n_missing_pairs"] = missing
    print("Half-flow date by snow-cover bin:")
    print(hm[["center", "median", "n"]].round(3).to_string(index=False))

    RESULTS.mkdir(parents=True, exist_ok=True)
    prov = pd.concat(
        [
            wm.assign(panel="A_winter_flow_ratio_vs_permafrost"),
            bm.assign(panel="B_bfi_vs_permafrost"),
            hm.assign(panel="C_half_flow_date_vs_snow"),
        ],
        ignore_index=True,
    )
    prov.to_csv(RESULTS / "coldregion_gradient_bins.csv", index=False)
    first, *rest = IMG_DIRS  # save once, copy identical delivered files
    first.mkdir(parents=True, exist_ok=True)
    # Vector PDF (scatter/line figure); CreationDate stripped for reproducible bytes.
    fig.savefig(first / "fig_coldregion_gradient.pdf", metadata={"CreationDate": None})
    print(f"wrote {first / 'fig_coldregion_gradient.pdf'}")
    for d in rest:
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first / "fig_coldregion_gradient.pdf", d / "fig_coldregion_gradient.pdf")
        print(f"wrote {d / 'fig_coldregion_gradient.pdf'}")
    plt.close(fig)


if __name__ == "__main__":
    main()
