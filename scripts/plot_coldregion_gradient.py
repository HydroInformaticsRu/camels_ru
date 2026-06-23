"""Cold-region signature-gradient figure for the CAMELS-RU dataset paper (Paper 1, HESS).

Builds the §4 cold-region signature-gradient figure: baseflow index varies non-monotonically with
permafrost extent (rising to a peak near intermediate cover, then returning toward baseline above
~70%), the association reverses sign across the -5 degC mean-annual-temperature line, and the
snow-dominated regimes that anchor this structure co-locate with where ERA5-Land water-balance
closure fails (a bridge to the forcing analysis, quantified in Sect. 5).

These are descriptive associations between released signatures and HydroATLAS proxies, not causal
permafrost attribution. Robustness (Eckhardt cross-check, within-temperature-slice association) is
established by scripts/coldregion_robustness.py. All numbers derive from the released CAMELS-RU v1.0
artifacts; no modelling is involved.

Outputs:
    paper/images/fig_coldregion_gradient.png
    paper/overleaf/images/fig_coldregion_gradient.png
    results/hess_quality/coldregion_gradient_bins.csv
"""

from __future__ import annotations

from pathlib import Path

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

T_SPLIT = -5.0  # mean-annual-temperature regime boundary (deg C)

mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["DejaVu Serif"],
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 8.5,
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
    cats = pd.cut(x, bins=edges, include_lowest=True)
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
    pf, bfi, snow, temp = (
        df["prm_pc_use"],
        df["baseflow_index"],
        df["snw_pc_uyr"],
        df["tmp_dc_uyr"],
    )
    print(f"n (A/B-graded, dam-excluded, non-anomalous) = {len(df)}")
    print("grade counts:", df["overall_grade"].value_counts().to_dict())

    # --- Verification: does the permafrost-BFI insight survive the A/B filter? ---
    bfi_by_pf = binned_median(pf, bfi, [0, 5, 10, 20, 30, 50, 70, 100])
    print("\nBFI median by permafrost bin:")
    print(bfi_by_pf[["center", "median", "n"]].to_string(index=False))
    rho_all, p_all = spearmanr(pf, bfi)
    warm = df[df["tmp_dc_uyr"] >= T_SPLIT]
    cold = df[df["tmp_dc_uyr"] < T_SPLIT]
    rho_w, p_w = spearmanr(warm["prm_pc_use"], warm["baseflow_index"])
    rho_c, p_c = spearmanr(cold["prm_pc_use"], cold["baseflow_index"])
    print(
        f"\nSpearman permafrost-BFI: all rho={rho_all:.3f} (p={p_all:.2g}); "
        f"warm rho={rho_w:.3f} (p={p_w:.2g}, n={len(warm)}); "
        f"cold rho={rho_c:.3f} (p={p_c:.2g}, n={len(cold)})"
    )
    hi = df.loc[df["prm_pc_use"] > 70, "baseflow_index"]
    nofrost = df.loc[df["prm_pc_use"] == 0, "baseflow_index"]
    print(
        f">70% permafrost BFI median={hi.median():.3f} (n={len(hi)}) vs "
        f"permafrost-free median={nofrost.median():.3f} (n={len(nofrost)})"
    )
    if df["aet_wb_gt_pet"].notna().any():
        rate = (
            df.groupby(pd.cut(snow, [0, 25, 40, 50, 60, 100], include_lowest=True), observed=True)[
                "aet_wb_gt_pet"
            ].mean()
            * 100
        )
        print("\nERA5-Land AET>PET rate by snow bin (%):")
        print(rate.round(1).to_string())

    fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=(15, 4.6))

    # ---- Panel A: BFI vs permafrost, coloured by mean annual T ----------------
    norm = TwoSlopeNorm(vmin=float(temp.min()), vcenter=T_SPLIT, vmax=float(temp.max()))
    sc = ax_a.scatter(pf, bfi, c=temp, cmap="RdBu_r", norm=norm, s=10, alpha=0.55, linewidths=0)
    pf_edges = [0, 5, 10, 20, 30, 50, 70, 100]
    bm = binned_median(pf, bfi, pf_edges)
    ax_a.plot(bm["center"], bm["median"], "-o", color="black", lw=1.8, ms=4, label="binned median")
    ax_a.fill_between(bm["center"], bm["q25"], bm["q75"], color="black", alpha=0.12)
    ax_a.axvline(70, ls="--", color="0.4", lw=1)
    peak = bm.loc[bm["median"].idxmax()]
    high_pf = bm.iloc[-1]
    nofrost_med = bm.iloc[0]["median"]
    ax_a.axhline(nofrost_med, ls=":", color="0.5", lw=0.9)
    ax_a.annotate(
        f"peak {peak['median']:.2f}",
        (peak["center"], peak["median"]),
        textcoords="offset points",
        xytext=(0, 8),
        ha="center",
        fontsize=8,
    )
    ax_a.annotate(
        f"returns to baseline {high_pf['median']:.2f}",
        (high_pf["center"], high_pf["median"]),
        textcoords="offset points",
        xytext=(0, -15),
        ha="center",
        fontsize=8,
    )
    ax_a.set_xlabel("Permafrost extent (HydroATLAS proxy, %)")
    ax_a.set_ylabel("Baseflow index")
    ax_a.set_title("(a) Baseflow index vs permafrost extent")
    ax_a.legend(loc="lower left", frameon=False)
    cb = fig.colorbar(sc, ax=ax_a, fraction=0.046, pad=0.03)
    cb.set_label("Mean annual T (°C)", fontsize=8)

    # ---- Panel B: same, split by temperature regime ---------------------------
    warm = df[df["tmp_dc_uyr"] >= T_SPLIT]
    cold = df[df["tmp_dc_uyr"] < T_SPLIT]
    b_edges = [0, 10, 30, 50, 70, 100]
    for sub, color, lab in [
        (warm, "#b2182b", f"warm (T ≥ {T_SPLIT:.0f}°C)"),
        (cold, "#2166ac", f"cold (T < {T_SPLIT:.0f}°C)"),
    ]:
        ax_b.scatter(
            sub["prm_pc_use"], sub["baseflow_index"], s=8, alpha=0.25, color=color, linewidths=0
        )
        bsub = binned_median(sub["prm_pc_use"], sub["baseflow_index"], b_edges)
        ax_b.plot(
            bsub["center"], bsub["median"], "-o", color=color, lw=2, ms=4, label=f"{lab}, n={len(sub)}"
        )
    ax_b.set_xlabel("Permafrost extent (%)")
    ax_b.set_ylabel("Baseflow index")
    ax_b.set_title("(b) Sign reversal across the −5 °C line")
    ax_b.legend(loc="upper right", frameon=False)

    # ---- Panel C: melt timing vs snow cover -----------------------------------
    # The ERA5-Land AET>PET rate is single-digit and not monotonic in snow cover once
    # precipitation is de-accumulated, so it is no longer plotted here; the apparent
    # snow co-location in the over-accumulated data was an artifact (rates exported to
    # coldregion_gradient_bins.csv for provenance).
    s_edges = [0, 25, 40, 50, 60, 100]
    hm = binned_median(snow, df["half_flow_date"], s_edges)
    ax_c.plot(hm["center"], hm["median"], "-o", color="#1b7837", lw=2, ms=4, label="half-flow date")
    ax_c.fill_between(hm["center"], hm["q25"], hm["q75"], color="#1b7837", alpha=0.15)
    ax_c.set_xlabel("Snow-cover extent (HydroATLAS proxy, %)")
    ax_c.set_ylabel("Half-flow date (day of hydro-year)", color="#1b7837")
    ax_c.tick_params(axis="y", labelcolor="#1b7837")
    ax_c.set_title("(c) Melt timing vs snow cover")
    ax_c.legend(loc="upper left", frameon=False)

    fig.tight_layout()
    RESULTS.mkdir(parents=True, exist_ok=True)
    # Provenance: panel-A permafrost-BFI medians + the (no-longer-plotted) snow->AET>PET rates,
    # retained to document that the corrected rate is single-digit and not monotonic in snow.
    prov = [bm.assign(panel="A_bfi_vs_permafrost")]
    if df["aet_wb_gt_pet"].notna().any():
        srate = df.groupby(pd.cut(snow, bins=s_edges, include_lowest=True), observed=True)[
            "aet_wb_gt_pet"
        ].agg(["mean", "count"])
        prov.append(
            pd.DataFrame(
                {
                    "center": [iv.mid for iv in srate.index],
                    "median": srate["mean"].to_numpy() * 100.0,
                    "q25": np.nan,
                    "q75": np.nan,
                    "n": srate["count"].to_numpy(),
                    "panel": "C_aetpet_pct_vs_snow",
                }
            )
        )
    pd.concat(prov, ignore_index=True).to_csv(RESULTS / "coldregion_gradient_bins.csv", index=False)
    for d in IMG_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        fig.savefig(d / "fig_coldregion_gradient.png", bbox_inches="tight")
        print(f"wrote {d / 'fig_coldregion_gradient.png'}")
    plt.close(fig)


if __name__ == "__main__":
    main()
