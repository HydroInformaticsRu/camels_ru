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
from matplotlib.colors import TwoSlopeNorm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release" / "CAMELS_RU_v1.0"
RESULTS = ROOT / "results" / "hess_quality"
IMG_DIRS = [ROOT / "paper" / "images", ROOT / "paper" / "overleaf" / "images"]

T_COLOUR_CENTRE = -5.0  # colour-scale midpoint only; no analysis is stratified on it
MIN_WINTER_COVERAGE = 0.95  # released winter_coverage: share of Dec-Mar days observed
Y_CLIP_A = 1.2  # panel (a) axis limit; the tail above it is clipped from view, not dropped
N_BOOT = 2000
# Seed matches scripts/coldregion_robustness.py so the panel-A bin-median CIs are reproducible
# and consistent with the robustness table.
BOOT_RNG = np.random.default_rng(1996)


def _boot_median_ci(values: np.ndarray, n_boot: int = N_BOOT) -> tuple[float, float]:
    """95% percentile bootstrap CI for a sample median (matches coldregion_robustness.py)."""
    v = values[np.isfinite(values)]
    if len(v) < 3:
        return (np.nan, np.nan)
    idx = BOOT_RNG.integers(0, len(v), size=(n_boot, len(v)))
    meds = np.median(v[idx], axis=1)
    return (float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5)))


# ESSD editor pre-review font floor: this figure prints at \textwidth from a 15in-wide
# source (~0.46x shrink), so text must start at >=18pt to clear 7pt in the final PDF.
FS = 18

mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["DejaVu Serif"],
        "figure.dpi": 150,
        "savefig.dpi": 300,
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
    cats = pd.cut(x.clip(edges[0], edges[-1]), bins=edges, include_lowest=True)
    g = y.groupby(cats, observed=True)
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

    # Modest width increase (was 15in) plus constrained_layout: fig.tight_layout() doesn't
    # reserve space for the colorbar or reflow around the font-floor bump below, causing
    # panel titles to run into each other and axis labels to clip at the saved image edges.
    fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=(16, 5.0), constrained_layout=True)

    # ---- Panel A: winter flow fraction vs permafrost -------------------------
    norm = TwoSlopeNorm(vmin=float(temp.min()), vcenter=T_COLOUR_CENTRE, vmax=float(temp.max()))
    sc = ax_a.scatter(pf, wff, c=temp, cmap="RdBu_r", norm=norm, s=10, alpha=0.55, linewidths=0)
    cats_a = pd.cut(pf.clip(0, 100), bins=pf_edges, include_lowest=True)
    ci_map = {iv.mid: _boot_median_ci(sub.to_numpy()) for iv, sub in wff.groupby(cats_a, observed=True)}
    wm["ci_lo"] = [ci_map.get(c, (np.nan, np.nan))[0] for c in wm["center"]]
    wm["ci_hi"] = [ci_map.get(c, (np.nan, np.nan))[1] for c in wm["center"]]
    ax_a.plot(wm["center"], wm["median"], "-o", color="black", lw=1.8, ms=4, label="binned median")
    ax_a.fill_between(wm["center"], wm["q25"], wm["q75"], color="black", alpha=0.12, label="IQR")
    ax_a.errorbar(
        wm["center"],
        wm["median"],
        yerr=[wm["median"] - wm["ci_lo"], wm["ci_hi"] - wm["median"]],
        fmt="none",
        ecolor="black",
        elinewidth=1.1,
        capsize=3,
        zorder=5,
        label="95% bootstrap CI",
    )
    first_bin, last_bin = wm.iloc[0], wm.iloc[-1]
    # First bin sits right at the left spine (center=2.5 on a 0-100 axis); centered-above
    # placement at floor-clearing size pushed "0.45" into the 0.6 y-tick and "n=776" past
    # the spine. Anchored to the right of the point instead, clear of both.
    ax_a.annotate(
        f"{first_bin['median']:.2f}\nn={int(first_bin['n'])}",
        (first_bin["center"], first_bin["median"]),
        textcoords="offset points",
        xytext=(12, 0),
        ha="left",
        va="center",
        fontsize=FS,
    )
    ax_a.annotate(
        f"{last_bin['median']:.2f}\nn={int(last_bin['n'])}",
        (last_bin["center"], last_bin["median"]),
        textcoords="offset points",
        xytext=(0, 12),
        ha="center",
        fontsize=FS,
    )
    # Clip the axis, not the data: a long upper tail (winter flow above the annual mean at
    # spring-fed gauges) would otherwise squash the binned medians into the bottom third.
    n_clipped = int((wff > Y_CLIP_A).sum())
    ax_a.set_ylim(0, Y_CLIP_A)
    print(f"panel (a): {n_clipped} of {len(wff)} points above the {Y_CLIP_A} axis limit")
    ax_a.set_xlabel("Permafrost extent (HydroATLAS proxy, %)")
    # Rotated at 18pt, "Winter flow ratio (mean Jan-Mar Q / mean annual Q)" is taller than
    # the panel itself and clips at both ends; the definition moves to the caption, matching
    # panel (b)'s bare "Baseflow index" label.
    ax_a.set_ylabel("Winter flow ratio")
    ax_a.set_title(f"(a) Winter flow ratio ($\\rho$ = {rho_w:+.2f})", loc="left")
    ax_a.legend(loc="upper right", frameon=False)
    # Vertical inset in panel (a)'s sparse mid-right interior: the previous full-width
    # horizontal bar below the panel forced a dead white band under panels (b)/(c),
    # since only (a) carries a colorbar.
    # Horizontal inset in the empty center of panel (a), below the legend: the data hug
    # the left edge and the bottom, the right edge carries the legend and the endpoint
    # annotation, so this is the one region where bar, ticks, and label all fit clear.
    cax = ax_a.inset_axes([0.40, 0.60, 0.42, 0.045])
    cb = fig.colorbar(sc, cax=cax, orientation="horizontal")
    cb.set_label("Mean annual T (\u00b0C)", fontsize=FS - 2)
    cb.ax.tick_params(labelsize=FS - 4)

    # ---- Panel B: the baseflow index over the same bins ----------------------
    ax_b.scatter(pf, bfi, s=10, alpha=0.35, color="0.45", linewidths=0)
    ax_b.plot(bm["center"], bm["median"], "-o", color="#b2182b", lw=2, ms=4, label="binned median")
    ax_b.fill_between(bm["center"], bm["q25"], bm["q75"], color="#b2182b", alpha=0.12, label="IQR")
    # Per-bin counts dropped: the bins and gauges are identical to panel (a)'s, whose
    # endpoint annotations already carry the range (n=776 down to n=43); seven red
    # numbers over the data read as clutter for no added information.
    ax_b.set_ylim(bottom=0)
    ax_b.set_xlabel("Permafrost extent (%)")
    ax_b.set_ylabel("Baseflow index")
    # Shortened from "..., same gauges (...)" — too wide for one panel at floor size;
    # "same gauges" is already established by the panel (a)/(b) pairing and caption.
    ax_b.set_title(f"(b) Baseflow index ($\\rho$ = {rho_b:+.2f})", loc="left")
    ax_b.legend(loc="lower right", frameon=False)

    # ---- Panel C: melt timing vs snow cover ----------------------------------
    s_edges = [0, 25, 40, 50, 60, 100]
    hm = binned_median(snow, df["half_flow_date"], s_edges)
    ax_c.plot(hm["center"], hm["median"], "-o", color="#1b7837", lw=2, ms=4, label="binned median")
    ax_c.fill_between(hm["center"], hm["q25"], hm["q75"], color="#1b7837", alpha=0.15, label="IQR")
    ax_c.set_xlabel("Snow-cover extent (HydroATLAS proxy, %)")
    # Same clipping issue as panel (a)'s label; "day of hydrological year" moves to the
    # caption, "DOY" is the standard abbreviation.
    ax_c.set_ylabel("Half-flow date (DOY)")
    ax_c.set_title("(c) Half-flow date by snow-cover extent", loc="left")
    # Lower right is the empty corner: the median line and IQR band climb through the
    # upper left, where the legend previously sat on top of the shading.
    ax_c.legend(loc="lower right", frameon=False)

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
    first, *rest = IMG_DIRS  # save once, copy: repeated tight saves differ by a few pixels
    first.mkdir(parents=True, exist_ok=True)
    # Vector PDF (scatter/line figure); CreationDate stripped for reproducible bytes.
    fig.savefig(
        first / "fig_coldregion_gradient.pdf", bbox_inches="tight", metadata={"CreationDate": None}
    )
    print(f"wrote {first / 'fig_coldregion_gradient.pdf'}")
    for d in rest:
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first / "fig_coldregion_gradient.pdf", d / "fig_coldregion_gradient.pdf")
        print(f"wrote {d / 'fig_coldregion_gradient.pdf'}")
    plt.close(fig)


if __name__ == "__main__":
    main()
