"""Robustness checks gating the §4 cold-region permafrost-BFI claim (Paper 1, HESS).

The triad decision record
(docs/dialogues/triad/2026-06-16-permafrost-bfi-s4-framing-triad/) commits two checks
*before* the §4 prose is written, because the sign-reversal claim is gated on them:

1. Temperature-stratified association. Within narrow mean-annual-temperature slices,
   does baseflow index still vary with permafrost extent? If the permafrost-BFI signal
   survives within homogeneous-temperature strata, it is not merely a mislabelled
   temperature effect (addresses the permafrost-temperature collinearity confounder).
   Reported with bootstrap confidence intervals on bin medians.

2. Eckhardt cross-check. The released BFI is a Lyne-Hollick ensemble; Lyne-Hollick is
   suspected of under-separating baseflow in flashy permafrost regimes. We recompute BFI
   with an independent two-parameter Eckhardt filter on the same gauges and ask whether
   the non-monotonic (inverted-U) shape and the -5 degC sign reversal persist. If the
   inverted-U inverts or flattens under Eckhardt, the §4 lead text drops the reversal and
   keeps only the warm-arm rise plus the §5 forcing bridge (the pre-registered kill switch).

Subset: Grade A/B, dam-excluded (dor_pc_pva==0), non-anomalous. All inputs are released
CAMELS-RU v1.0 artifacts; no modelling. This is a descriptive robustness diagnostic, not
causal permafrost attribution.

Outputs:
    results/hess_quality/coldregion_robustness_strata.csv   (filter x T-slice x pf-bin medians + CIs)
    results/hess_quality/coldregion_robustness_verdict.txt   (the kill-switch verdict)
"""

from __future__ import annotations

from pathlib import Path

import numba
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release" / "CAMELS_RU_v1.0"
RESULTS = ROOT / "results" / "hess_quality"

T_SPLIT = -5.0  # mean-annual-temperature regime boundary (deg C)
PF_EDGES = [0, 5, 10, 20, 30, 50, 70, 100]  # permafrost-extent bins (%)
T_SLICES = [(-15.0, -5.0), (-5.0, 0.0), (0.0, 3.0), (3.0, 6.0)]  # narrow MAT slices (deg C)
ECKHARDT_BFI_MAX = 0.80  # standard for perennial streams, porous aquifers (Eckhardt 2005)
LH_ALPHA_BOUNDS = [
    0.90,
    0.94,
    0.98,
]  # Lyne-Hollick alpha-sweep bounds + midpoint (released: U[0.90,0.98])
N_BOOT = 2000
RNG = np.random.default_rng(1996)


def load_subset() -> pd.DataFrame:
    """Load the Grade A/B, dam-excluded, non-anomalous subset with cold-region attributes."""
    sig = pd.read_csv(RELEASE / "camels_ru_signatures.csv")
    sig["gauge_id"] = sig["gauge_id"].astype(str)
    att = pd.read_csv(RELEASE / "camels_ru_attributes.csv")
    att["gauge_id"] = att["gauge_id"].astype(str)
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    summary["gauge_id"] = summary["gauge_id"].astype(str)

    att_cols = ["gauge_id", "dor_pc_pva", "snw_pc_uyr", "prm_pc_use", "tmp_dc_uyr"]
    df = sig.merge(att[att_cols], on="gauge_id", how="inner")
    df = df.merge(summary[["gauge_id", "overall_grade"]], on="gauge_id", how="left")
    df = df[
        (~df["is_anomalous"].astype(bool))
        & (df["dor_pc_pva"] == 0)
        & (df["overall_grade"].isin(["A", "B"]))
    ].copy()
    return df


def boot_median_ci(values: np.ndarray, n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """Median and 95% bootstrap CI (percentile method) for a sample."""
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return (np.nan, np.nan, np.nan)
    idx = RNG.integers(0, len(values), size=(n_boot, len(values)))
    meds = np.median(values[idx], axis=1)
    return (float(np.median(values)), float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5)))


@numba.jit(nopython=True)
def _eckhardt_bfi(discharge: np.ndarray, alpha: float, bfi_max: float) -> float:
    """Eckhardt (2005) two-parameter recursive digital baseflow filter; returns BFI.

    b_t = ((1 - bfi_max) * a * b_{t-1} + (1 - a) * bfi_max * Q_t) / (1 - a * bfi_max),
    constrained to b_t <= Q_t. Forward pass, b_0 = Q_0.
    """
    n = len(discharge)
    if n == 0:
        return np.nan
    base = np.empty(n, dtype=np.float64)
    base[0] = discharge[0]
    denom = 1.0 - alpha * bfi_max
    for t in range(1, n):
        b = ((1.0 - bfi_max) * alpha * base[t - 1] + (1.0 - alpha) * bfi_max * discharge[t]) / denom
        if b > discharge[t]:
            b = discharge[t]
        if b < 0.0:
            b = 0.0
        base[t] = b
    mean_q = np.mean(discharge)
    if mean_q == 0.0:
        return 0.0
    return np.mean(base) / mean_q


def recession_alpha(discharge: np.ndarray) -> float:
    """Per-gauge daily recession constant a = median(Q_t / Q_{t-1}) on recession days.

    Clipped to [0.90, 0.99]; falls back to 0.98 when recession data are insufficient.
    """
    q = discharge
    prev, cur = q[:-1], q[1:]
    mask = (cur < prev) & (prev > 0) & np.isfinite(prev) & np.isfinite(cur)
    if mask.sum() < 30:
        return 0.98
    ratios = cur[mask] / prev[mask]
    a = float(np.median(ratios))
    return min(0.99, max(0.90, a))


def eckhardt_bfi_for_gauges(gauge_ids: list[str]) -> pd.Series:
    """Recompute BFI with the Eckhardt filter from released daily discharge (mm/day)."""
    ds = xr.open_dataset(RELEASE / "camels_ru_discharge.nc")
    q_all = ds["discharge_mm"]
    gc = "gauge_id" if "gauge_id" in ds.coords else "gauge"
    avail = set(ds[gc].values.astype(str))
    out: dict[str, float] = {}
    for gid in gauge_ids:
        if gid not in avail:
            out[gid] = np.nan
            continue
        series = q_all.sel({gc: gid}).to_numpy().astype(np.float64)
        series = series[np.isfinite(series)]
        if len(series) < 365:
            out[gid] = np.nan
            continue
        alpha = recession_alpha(series)
        out[gid] = _eckhardt_bfi(series, alpha, ECKHARDT_BFI_MAX)
    ds.close()
    return pd.Series(out, name="bfi_eckhardt")


def lh_bfi_for_gauges_at_alphas(gauge_ids: list[str], alphas: list[float]) -> pd.DataFrame:
    """Recompute Lyne-Hollick BFI at fixed alpha values from released daily discharge.

    The released BFI is the mean over 1000 alpha~U[0.90,0.98]; recomputing at the sweep
    bounds (and midpoint) tests whether the cold-region inverted-U is an artefact of the
    alpha distribution or a parameter-insensitive shape. Uses the same 3-pass, 30-reflect
    Lyne-Hollick engine that produced the released signature (src/hydro/base_flow.py).
    """
    import sys

    sys.path.append(str(ROOT))
    from src.hydro.base_flow import _single_bfi_calculation

    ds = xr.open_dataset(RELEASE / "camels_ru_discharge.nc")
    q_all = ds["discharge_mm"]
    gc = "gauge_id" if "gauge_id" in ds.coords else "gauge"
    avail = set(ds[gc].values.astype(str))
    cols = [f"bfi_lh_a{a:g}" for a in alphas]
    out: dict[str, dict[str, float]] = {}
    for gid in gauge_ids:
        rec = dict.fromkeys(cols, np.nan)
        if gid in avail:
            series = q_all.sel({gc: gid}).to_numpy().astype(np.float64)
            series = series[np.isfinite(series)]
            if len(series) >= 365:
                for a, col in zip(alphas, cols, strict=True):
                    bfi, _ = _single_bfi_calculation(series, a, 3, 30)
                    rec[col] = float(bfi)
        out[gid] = rec
    ds.close()
    res = pd.DataFrame.from_dict(out, orient="index")
    res.index.name = "gauge_id"
    return res.reset_index()


def shape_stats(pf: pd.Series, bfi: pd.Series) -> dict[str, float]:
    """Inverted-U descriptors: baseline (0% pf), peak (30-50%), high (>70%) median BFI."""
    base = bfi[pf == 0]
    peak = bfi[(pf >= 30) & (pf < 50)]
    high = bfi[pf > 70]
    return {
        "baseline_med": float(base.median()),
        "baseline_n": int(base.notna().sum()),
        "peak_med": float(peak.median()),
        "peak_n": int(peak.notna().sum()),
        "high_med": float(high.median()),
        "high_n": int(high.notna().sum()),
    }


def alpha_sensitivity(
    df: pd.DataFrame, warm: pd.DataFrame, cold: pd.DataFrame
) -> tuple[dict[float, dict[str, float]], dict[float, tuple[float, float]]]:
    """Inverted-U shape and warm/cold pf-BFI rho at each fixed Lyne-Hollick alpha.

    Tests whether the released ensemble-mean inverted-U is a parameter-insensitive shape
    or an artefact of the alpha distribution (Check 3 of the robustness diagnostic).
    """
    print("\n=== CHECK 3: Lyne-Hollick alpha-sensitivity (released filter parameter) ===")
    print("  released BFI = mean over 1000 alpha~U[0.90,0.98]; recompute at sweep bounds:")
    alpha_shapes: dict[float, dict[str, float]] = {}
    alpha_revs: dict[float, tuple[float, float]] = {}
    for a in LH_ALPHA_BOUNDS:
        col = f"bfi_lh_a{a:g}"
        shp = shape_stats(df["prm_pc_use"], df[col])
        rw = spearmanr(warm["prm_pc_use"], warm[col], nan_policy="omit")[0]
        rc = spearmanr(cold["prm_pc_use"], cold[col], nan_policy="omit")[0]
        alpha_shapes[a] = shp
        alpha_revs[a] = (rw, rc)
        print(
            f"    alpha={a:.2f}: baseline={shp['baseline_med']:.3f} peak={shp['peak_med']:.3f} "
            f"high={shp['high_med']:.3f} | warm rho={rw:+.3f} cold rho={rc:+.3f}"
        )
    return alpha_shapes, alpha_revs


def main() -> None:
    """Run both robustness checks and write the stratified table + kill-switch verdict."""
    df = load_subset()
    print(f"n (A/B-graded, dam-excluded, non-anomalous) = {len(df)}")
    print("grade counts:", df["overall_grade"].value_counts().to_dict())

    # --- Check 1: temperature-stratified permafrost-BFI association (released LH BFI) ----
    print("\n=== CHECK 1: within-T-slice permafrost-BFI association (Lyne-Hollick) ===")
    rows: list[dict[str, object]] = []
    for lo, hi in T_SLICES:
        sl = df[(df["tmp_dc_uyr"] >= lo) & (df["tmp_dc_uyr"] < hi)]
        if len(sl) < 20:
            print(f"  T[{lo:+.0f},{hi:+.0f}) n={len(sl)} (skipped, too few)")
            continue
        rho, p = spearmanr(sl["prm_pc_use"], sl["baseflow_index"])
        print(f"  T[{lo:+.0f},{hi:+.0f}) n={len(sl):4d}  Spearman(pf,BFI) rho={rho:+.3f} (p={p:.2g})")
        cats = pd.cut(sl["prm_pc_use"], bins=PF_EDGES, include_lowest=True)
        for iv, grp in sl.groupby(cats, observed=True):
            med, lo_ci, hi_ci = boot_median_ci(grp["baseflow_index"].to_numpy())
            rows.append(
                {
                    "filter": "lyne_hollick",
                    "t_slice": f"[{lo:+.0f},{hi:+.0f})",
                    "pf_bin": str(iv),
                    "pf_center": iv.mid,
                    "bfi_median": med,
                    "ci_lo": lo_ci,
                    "ci_hi": hi_ci,
                    "n": int(grp["baseflow_index"].notna().sum()),
                }
            )

    # --- Check 2: Eckhardt cross-check -------------------------------------------------
    print("\n=== CHECK 2: Eckhardt-filter BFI recomputation ===")
    gids = df["gauge_id"].tolist()
    eck = eckhardt_bfi_for_gauges(gids)
    df = df.merge(eck.rename_axis("gauge_id").reset_index(), on="gauge_id", how="left")
    n_eck = int(df["bfi_eckhardt"].notna().sum())
    print(f"  Eckhardt BFI computed for {n_eck}/{len(df)} gauges (BFImax={ECKHARDT_BFI_MAX})")
    corr = df[["baseflow_index", "bfi_eckhardt"]].corr(method="spearman").iloc[0, 1]
    print(f"  Spearman(LH-BFI, Eckhardt-BFI) = {corr:+.3f}")

    lh_shape = shape_stats(df["prm_pc_use"], df["baseflow_index"])
    eck_shape = shape_stats(df["prm_pc_use"], df["bfi_eckhardt"])
    print("\n  Inverted-U shape (median BFI by permafrost band):")
    print(
        f"    Lyne-Hollick: baseline={lh_shape['baseline_med']:.3f} "
        f"peak={lh_shape['peak_med']:.3f} high={lh_shape['high_med']:.3f}"
    )
    print(
        f"    Eckhardt    : baseline={eck_shape['baseline_med']:.3f} "
        f"peak={eck_shape['peak_med']:.3f} high={eck_shape['high_med']:.3f}"
    )

    # --- Check 3: Lyne-Hollick alpha-sensitivity (within the released filter) -----------
    lh_alpha = lh_bfi_for_gauges_at_alphas(gids, LH_ALPHA_BOUNDS)
    df = df.merge(lh_alpha, on="gauge_id", how="left")

    warm = df[df["tmp_dc_uyr"] >= T_SPLIT]
    cold = df[df["tmp_dc_uyr"] < T_SPLIT]
    rho_w_lh = spearmanr(warm["prm_pc_use"], warm["baseflow_index"])[0]
    rho_c_lh = spearmanr(cold["prm_pc_use"], cold["baseflow_index"])[0]
    rho_w_e = spearmanr(warm["prm_pc_use"], warm["bfi_eckhardt"], nan_policy="omit")[0]
    rho_c_e = spearmanr(cold["prm_pc_use"], cold["bfi_eckhardt"], nan_policy="omit")[0]
    print("\n  Sign reversal across -5 degC (Spearman pf-BFI):")
    print(f"    Lyne-Hollick: warm={rho_w_lh:+.3f} (n={len(warm)}) cold={rho_c_lh:+.3f} (n={len(cold)})")
    print(f"    Eckhardt    : warm={rho_w_e:+.3f}  cold={rho_c_e:+.3f}")

    alpha_shapes, alpha_revs = alpha_sensitivity(df, warm, cold)

    for filt, col in [("eckhardt", "bfi_eckhardt")]:
        for lo, hi in T_SLICES:
            sl = df[(df["tmp_dc_uyr"] >= lo) & (df["tmp_dc_uyr"] < hi)]
            if len(sl) < 20:
                continue
            cats = pd.cut(sl["prm_pc_use"], bins=PF_EDGES, include_lowest=True)
            for iv, grp in sl.groupby(cats, observed=True):
                med, lo_ci, hi_ci = boot_median_ci(grp[col].to_numpy())
                rows.append(
                    {
                        "filter": filt,
                        "t_slice": f"[{lo:+.0f},{hi:+.0f})",
                        "pf_bin": str(iv),
                        "pf_center": iv.mid,
                        "bfi_median": med,
                        "ci_lo": lo_ci,
                        "ci_hi": hi_ci,
                        "n": int(grp[col].notna().sum()),
                    }
                )

    # --- Verdict ------------------------------------------------------------------------
    def _is_hump(s: dict[str, float]) -> bool:
        return s["peak_med"] > s["baseline_med"] and s["peak_med"] > s["high_med"]

    def _shape_str(s: dict[str, float]) -> str:
        return (
            f"(baseline {s['baseline_med']:.3f} / peak {s['peak_med']:.3f} / high {s['high_med']:.3f})"
        )

    inverted_u_lh = _is_hump(lh_shape)
    inverted_u_eck = _is_hump(eck_shape)
    reversal_lh = (rho_w_lh > 0) and (rho_c_lh < 0)
    reversal_eck = (rho_w_e > 0) and (rho_c_e < 0)
    hump_msg = "YES" if inverted_u_eck else "NO -> drop tail, keep warm-arm rise only"
    rev_msg = (
        "YES -> reversal may stay in §4 body"
        if reversal_eck
        else "NO -> drop reversal from §4 lead text"
    )
    alpha_hump_all = all(_is_hump(alpha_shapes[a]) for a in LH_ALPHA_BOUNDS)
    alpha_rev_all = all(alpha_revs[a][0] > 0 and alpha_revs[a][1] < 0 for a in LH_ALPHA_BOUNDS)
    alpha_msg = (
        "YES" if alpha_hump_all and alpha_rev_all else "NO -> ensemble mean masks alpha-sensitivity"
    )
    verdict = [
        "COLD-REGION PERMAFROST-BFI ROBUSTNESS VERDICT",
        "=" * 48,
        f"subset n = {len(df)} (Grade A/B, dam-excluded, non-anomalous)",
        "",
        "Inverted-U (peak > baseline AND peak > high):",
        f"  Lyne-Hollick : {inverted_u_lh}  {_shape_str(lh_shape)}",
        f"  Eckhardt     : {inverted_u_eck}  {_shape_str(eck_shape)}",
        "",
        "Sign reversal across -5 degC (warm rho>0 AND cold rho<0):",
        f"  Lyne-Hollick : {reversal_lh}  (warm {rho_w_lh:+.3f} / cold {rho_c_lh:+.3f})",
        f"  Eckhardt     : {reversal_eck}  (warm {rho_w_e:+.3f} / cold {rho_c_e:+.3f})",
        "",
        f"Spearman(LH, Eckhardt) BFI agreement = {corr:+.3f}",
        "",
        "Alpha-sensitivity (Lyne-Hollick parameter; released = mean over U[0.90,0.98]):",
        f"  inverted-U holds at every alpha in {LH_ALPHA_BOUNDS}? {alpha_hump_all}",
        f"  sign reversal holds at every alpha? {alpha_rev_all}",
        *[
            f"    alpha={a:.2f}: baseline {alpha_shapes[a]['baseline_med']:.3f} / "
            f"peak {alpha_shapes[a]['peak_med']:.3f} / high {alpha_shapes[a]['high_med']:.3f} "
            f"(warm {alpha_revs[a][0]:+.3f} / cold {alpha_revs[a][1]:+.3f})"
            for a in LH_ALPHA_BOUNDS
        ],
        "",
        "KILL-SWITCH:",
        f"  inverted-U survives Eckhardt? {hump_msg}",
        f"  sign reversal survives Eckhardt? {rev_msg}",
        f"  shape survives the alpha-sweep bounds? {alpha_msg}",
    ]
    verdict_txt = "\n".join(verdict)
    print("\n" + verdict_txt)

    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(RESULTS / "coldregion_robustness_strata.csv", index=False)
    (RESULTS / "coldregion_robustness_verdict.txt").write_text(verdict_txt + "\n")
    print(f"\nwrote {RESULTS / 'coldregion_robustness_strata.csv'}")
    print(f"wrote {RESULTS / 'coldregion_robustness_verdict.txt'}")


if __name__ == "__main__":
    main()
