#!/usr/bin/env python3
"""Stratify CAMELS-RU water-balance diagnostics for HESS review.

The main HESS audit already computes product-specific Budyko and water-balance
AET diagnostics.  This script turns the per-gauge audit tables into small,
reviewer-facing strata by catchment area and cold-region proxies so the
manuscript can explain *where* physical-consistency failures occur without
launching a full hydrological-model benchmark.

Important interpretation guardrail: snow, permafrost, and temperature strata are
HydroATLAS-derived proxies.  They support descriptive HESS discussion, not causal
permafrost attribution.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.switch_backend("Agg")

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release" / "CAMELS_RU_v1.0"
AUDIT_DIR = ROOT / "results" / "hess_quality"
BUDYKO_PER_GAUGE = AUDIT_DIR / "budyko_per_gauge_product.csv"
AET_PER_GAUGE = AUDIT_DIR / "aet_per_gauge_product.csv"
ATTRIBUTES = RELEASE / "camels_ru_attributes.csv"

OUT_SUMMARY = AUDIT_DIR / "water_balance_strata.csv"
OUT_FOCUS = AUDIT_DIR / "water_balance_strata_focus.csv"
OUT_TEX = AUDIT_DIR / "water_balance_strata_focus.tex"
OUT_NOTES = AUDIT_DIR / "water_balance_strata_notes.md"
OUT_PNG = ROOT / "paper" / "images" / "fig_water_balance_strata.png"
OVERLEAF_OUT_PNG = ROOT / "paper" / "overleaf" / "images" / "fig_water_balance_strata.png"

PRODUCT_ORDER = ["ERA5-Land", "MSWEP", "GPCP"]
PRODUCT_COLORS = {
    # Colorblind-safe Okabe-Ito-inspired palette.
    "ERA5-Land": "#D55E00",
    "MSWEP": "#0072B2",
    "GPCP": "#009E73",
}

ATTRIBUTE_COLS = [
    "gauge_id",
    "dor_pc_pva",
    "snw_pc_uyr",
    "prm_pc_use",
    "tmp_dc_uyr",
    "ari_ix_uav",
    "lat",
    "lon",
]

STRATUM_COLUMNS = {
    "all": "all",
    "area_class": "area_class",
    "snow_fraction_proxy": "snow_fraction_proxy",
    "permafrost_proxy": "permafrost_proxy",
    "mean_annual_temp_class": "mean_annual_temp_class",
    "aridity_class": "aridity_class",
}

STRATUM_ORDER = {
    "all": ["all"],
    "area_class": ["<50", "50-500", "500-5k", "5k-50k"],
    "snow_fraction_proxy": ["0", "0-10", "10-50", ">50"],
    "permafrost_proxy": ["0", "0-10", "10-50", ">50"],
    "mean_annual_temp_class": ["<=-5", "-5-0", "0-5", ">5"],
    "aridity_class": ["<0.65", "0.65-1", "1-2", ">2"],
}


def _pct(numer: int | float, denom: int | float) -> float:
    """Return a percentage, preserving NaN for empty denominators."""
    return float(numer) / float(denom) * 100.0 if denom else np.nan


def _as_bool(series: pd.Series) -> pd.Series:
    """Coerce bool/string bool columns from CSV to a Boolean Series."""
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def _ordered_pct_bin(values: pd.Series) -> pd.Categorical:
    """Bin percentage-like HydroATLAS proxy values into compact labels."""
    numeric = pd.to_numeric(values, errors="coerce")
    labels = np.select(
        [
            numeric.eq(0),
            numeric.gt(0) & numeric.le(10),
            numeric.gt(10) & numeric.le(50),
            numeric.gt(50),
        ],
        ["0", "0-10", "10-50", ">50"],
        default="missing",
    )
    return pd.Categorical(labels, categories=["0", "0-10", "10-50", ">50", "missing"], ordered=True)


def _add_strata(df: pd.DataFrame) -> pd.DataFrame:
    """Add area and HydroATLAS-proxy strata to a per-gauge diagnostic table."""
    out = df.copy()
    out["all"] = "all"
    out["area_class"] = pd.cut(
        pd.to_numeric(out["area_km2"], errors="coerce"),
        bins=[-np.inf, 50, 500, 5_000, 50_000],
        labels=STRATUM_ORDER["area_class"],
        right=False,
    )
    out["snow_fraction_proxy"] = _ordered_pct_bin(out["snw_pc_uyr"])
    out["permafrost_proxy"] = _ordered_pct_bin(out["prm_pc_use"])
    out["mean_annual_temp_class"] = pd.cut(
        pd.to_numeric(out["tmp_dc_uyr"], errors="coerce"),
        bins=[-np.inf, -5, 0, 5, np.inf],
        labels=STRATUM_ORDER["mean_annual_temp_class"],
        right=False,
    )
    out["aridity_class"] = pd.cut(
        pd.to_numeric(out["ari_ix_uav"], errors="coerce"),
        bins=[-np.inf, 0.65, 1.0, 2.0, np.inf],
        labels=STRATUM_ORDER["aridity_class"],
        right=False,
    )
    out["dor_pc_pva"] = pd.to_numeric(out["dor_pc_pva"], errors="coerce")
    out["regulation_proxy_class"] = np.select(
        [out["dor_pc_pva"].eq(0), out["dor_pc_pva"].gt(0)],
        ["dam_excluded", "regulated_proxy"],
        default="missing_regulation_proxy",
    )
    return out


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load per-gauge HESS audit outputs and merge HydroATLAS proxy columns."""
    missing = [path for path in [BUDYKO_PER_GAUGE, AET_PER_GAUGE, ATTRIBUTES] if not path.exists()]
    if missing:
        joined = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        raise SystemExit(f"Missing inputs: {joined}. Run scripts/hess_quality_audit.py first.")

    attrs = pd.read_csv(ATTRIBUTES, usecols=lambda col: col in ATTRIBUTE_COLS)
    for col in ATTRIBUTE_COLS:
        if col not in attrs.columns:
            attrs[col] = np.nan
    attrs["gauge_id"] = attrs["gauge_id"].astype(str)

    budyko = pd.read_csv(BUDYKO_PER_GAUGE)
    aet = pd.read_csv(AET_PER_GAUGE)
    for frame in [budyko, aet]:
        frame["gauge_id"] = frame["gauge_id"].astype(str)
        frame["product"] = pd.Categorical(frame["product"], categories=PRODUCT_ORDER, ordered=True)
        frame["is_release_anomalous"] = _as_bool(frame["is_release_anomalous"])

    budyko = _add_strata(budyko.merge(attrs, on="gauge_id", how="left"))
    aet = _add_strata(aet.merge(attrs, on="gauge_id", how="left"))

    budyko["budyko_energy_violation"] = (
        pd.to_numeric(budyko["evaporative_index"], errors="coerce")
        > pd.to_numeric(budyko["aridity_index"], errors="coerce")
    )
    budyko["budyko_envelope_violation"] = (
        pd.to_numeric(budyko["evaporative_index"], errors="coerce")
        > np.minimum(
            pd.to_numeric(budyko["aridity_index"], errors="coerce"),
            1.0,
        )
    )
    budyko["q_gt_p"] = pd.to_numeric(budyko["evaporative_index"], errors="coerce") < 0.0
    aet["aet_wb_gt_pet"] = _as_bool(aet["aet_wb_gt_pet"])
    aet["aet_wb_lt_zero"] = _as_bool(aet["aet_wb_lt_zero"])
    return budyko, aet


def _scope_mask(df: pd.DataFrame, scope: str) -> pd.Series:
    """Return the row mask for a named manuscript-analysis scope."""
    clean = ~df["is_release_anomalous"]
    dor = pd.to_numeric(df["dor_pc_pva"], errors="coerce")
    if scope == "release_clean":
        return clean
    if scope == "dam_excluded_clean":
        return clean & dor.eq(0)
    if scope == "regulated_proxy_clean":
        return clean & dor.gt(0)
    if scope == "unknown_regulation_clean":
        return clean & dor.isna()
    raise ValueError(f"Unknown scope: {scope}")


def _median_or_nan(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return float(numeric.median()) if not numeric.empty else np.nan


def _rows_for_stratum(
    budyko: pd.DataFrame,
    aet: pd.DataFrame,
    scope: str,
    group_name: str,
    group_col: str,
    levels: Iterable[str],
) -> list[dict[str, object]]:
    """Build summary rows for one scope x stratum group."""
    rows: list[dict[str, object]] = []
    b_scope = _scope_mask(budyko, scope)
    a_scope = _scope_mask(aet, scope)
    for stratum in levels:
        for product in PRODUCT_ORDER:
            b = budyko.loc[
                b_scope
                & budyko["product"].eq(product)
                & budyko[group_col].astype(str).eq(stratum)
            ].dropna(subset=["aridity_index", "evaporative_index"])
            a = aet.loc[
                a_scope & aet["product"].eq(product) & aet[group_col].astype(str).eq(stratum)
            ].dropna(subset=["aet_wb_mm_yr", "pet_gleam_mm_yr", "aet_gleam_mm_yr"])
            if b.empty and a.empty:
                continue
            rows.append(
                {
                    "scope": scope,
                    "stratum_group": group_name,
                    "stratum": stratum,
                    "product": product,
                    "n_budyko": int(len(b)),
                    "q_gt_p_n": int(b["q_gt_p"].sum()) if not b.empty else 0,
                    "q_gt_p_pct": _pct(int(b["q_gt_p"].sum()), len(b)),
                    "budyko_energy_violation_n": int(b["budyko_energy_violation"].sum())
                    if not b.empty
                    else 0,
                    "budyko_energy_violation_pct": _pct(
                        int(b["budyko_energy_violation"].sum()), len(b)
                    ),
                    "budyko_envelope_violation_n": int(b["budyko_envelope_violation"].sum())
                    if not b.empty
                    else 0,
                    "budyko_envelope_violation_pct": _pct(
                        int(b["budyko_envelope_violation"].sum()), len(b)
                    ),
                    "median_aridity_index": _median_or_nan(b["aridity_index"]),
                    "median_evaporative_index": _median_or_nan(b["evaporative_index"]),
                    "n_aet": int(len(a)),
                    "aet_wb_gt_pet_n": int(a["aet_wb_gt_pet"].sum()) if not a.empty else 0,
                    "aet_wb_gt_pet_pct": _pct(int(a["aet_wb_gt_pet"].sum()), len(a)),
                    "aet_wb_lt_zero_n": int(a["aet_wb_lt_zero"].sum()) if not a.empty else 0,
                    "aet_wb_lt_zero_pct": _pct(int(a["aet_wb_lt_zero"].sum()), len(a)),
                    "median_q_mm_yr": _median_or_nan(a["q_mm_yr"]),
                    "median_p_mm_yr": _median_or_nan(a["p_mm_yr"]),
                    "median_aet_wb_mm_yr": _median_or_nan(a["aet_wb_mm_yr"]),
                    "median_aet_wb_div_gleam": _median_or_nan(a["aet_wb_div_gleam"]),
                }
            )
    return rows


def build_summary(budyko: pd.DataFrame, aet: pd.DataFrame) -> pd.DataFrame:
    """Create a long water-balance stratification summary table."""
    rows: list[dict[str, object]] = []
    for scope in [
        "release_clean",
        "dam_excluded_clean",
        "regulated_proxy_clean",
        "unknown_regulation_clean",
    ]:
        for group_name, group_col in STRATUM_COLUMNS.items():
            rows.extend(
                _rows_for_stratum(
                    budyko,
                    aet,
                    scope=scope,
                    group_name=group_name,
                    group_col=group_col,
                    levels=STRATUM_ORDER[group_name],
                )
            )
    return pd.DataFrame(rows)


def _plot_metric(
    ax: plt.Axes,
    focus: pd.DataFrame,
    group: str,
    metric: str,
    title: str,
    ylabel: str,
    panel_label: str,
) -> None:
    """Draw one grouped-bar panel for a categorical stratum diagnostic."""
    group_rows = focus.loc[focus["stratum_group"].eq(group)].copy()
    present = set(group_rows.loc[group_rows[metric].notna(), "stratum"].astype(str))
    levels = [level for level in STRATUM_ORDER[group] if level in present]
    x = np.arange(len(levels), dtype=float)
    width = 0.22
    offsets = np.linspace(-width, width, len(PRODUCT_ORDER))

    for offset, product in zip(offsets, PRODUCT_ORDER, strict=True):
        product_rows = group_rows.loc[group_rows["product"].eq(product)].set_index("stratum")
        values = [float(product_rows[metric].get(level, np.nan)) for level in levels]
        ax.bar(
            x + offset,
            values,
            width=width,
            label=product,
            color=PRODUCT_COLORS[product],
            edgecolor="white",
            linewidth=0.6,
        )

    n_col = "n_budyko" if "budyko" in metric or metric == "q_gt_p_pct" else "n_aet"
    n_labels = []
    for level in levels:
        counts = pd.to_numeric(
            group_rows.loc[group_rows["stratum"].astype(str).eq(level), n_col],
            errors="coerce",
        ).dropna()
        n_labels.append(f"{level}\n(n={int(counts.min()):,})" if not counts.empty else level)

    ax.set_xticks(x, n_labels)
    ax.set_title(f"{panel_label} {title}", fontsize=9.5, fontweight="bold", loc="left")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_ylim(bottom=0)


def plot_summary(summary: pd.DataFrame) -> None:
    """Write the HESS water-balance strata figure."""
    focus = summary.loc[summary["scope"].eq("dam_excluded_clean")].copy()
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.titlesize": 9.5,
            "axes.labelsize": 8.5,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
        }
    )
    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.25), constrained_layout=True, sharey=False)
    _plot_metric(
        axes[0],
        focus,
        "area_class",
        "q_gt_p_pct",
        "Mean (P-Q)/P < 0 by catchment area",
        "Failure rate (% gauges)",
        "(a)",
    )
    _plot_metric(
        axes[1],
        focus,
        "snow_fraction_proxy",
        "budyko_envelope_violation_pct",
        "Budyko envelope by snow proxy",
        "Failure rate (% gauges)",
        "(b)",
    )
    _plot_metric(
        axes[2],
        focus,
        "snow_fraction_proxy",
        "aet_wb_gt_pet_pct",
        "AET$_{wb}$ > PET by snow proxy",
        "Exceedance rate (% gauges)",
        "(c)",
    )
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.14))
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    plt.close(fig)
    if OVERLEAF_OUT_PNG.parent.exists():
        shutil.copy2(OUT_PNG, OVERLEAF_OUT_PNG)


def _write_notes(summary: pd.DataFrame) -> None:
    """Write a compact reviewer-facing interpretation note."""
    focus = summary.loc[summary["scope"].eq("dam_excluded_clean")].copy()
    overall = focus.loc[focus["stratum_group"].eq("all")].copy()

    def format_overall(metric: str) -> str:
        parts = []
        for product in PRODUCT_ORDER:
            row = overall.loc[overall["product"].eq(product)]
            if row.empty:
                continue
            parts.append(f"{product}: {float(row.iloc[0][metric]):.1f}%")
        return "; ".join(parts)

    def top_row(group: str, metric: str) -> str:
        candidates = focus.loc[focus["stratum_group"].eq(group)].dropna(subset=[metric])
        if candidates.empty:
            return "not available"
        row = candidates.sort_values(metric, ascending=False).iloc[0]
        n_col = "n_budyko" if "budyko" in metric or metric == "q_gt_p_pct" else "n_aet"
        return (
            f"{row['product']} / {group}={row['stratum']}: "
            f"{float(row[metric]):.1f}% (n={int(row[n_col])})"
        )

    lines = [
        "# Water-balance stratification notes",
        "",
        (
            "Scope: cleaned, non-anomalous CAMELS-RU gauges with HydroATLAS "
            "`dor_pc_pva == 0`; this is a regulation proxy screen, not a "
            "verified natural-basin classification."
        ),
        "",
        "## Overall dam/regulation-screened rates",
        f"- Negative evaporative-index closure failures [(P-Q)/P < 0]: {format_overall('q_gt_p_pct')}.",
        f"- Budyko-envelope failures: {format_overall('budyko_envelope_violation_pct')}.",
        f"- AET_wb > GLEAM PET: {format_overall('aet_wb_gt_pet_pct')}.",
        f"- AET_wb < 0: {format_overall('aet_wb_lt_zero_pct')}.",
        "",
        "## Highest descriptive strata",
        f"- Negative evaporative-index closure by area: {top_row('area_class', 'q_gt_p_pct')}.",
        (
            "- Budyko-envelope by snow proxy: "
            f"{top_row('snow_fraction_proxy', 'budyko_envelope_violation_pct')}."
        ),
        (
            "- AET_wb > GLEAM PET by snow proxy: "
            f"{top_row('snow_fraction_proxy', 'aet_wb_gt_pet_pct')}."
        ),
        "",
        "## Manuscript use",
        (
            "Use this as a descriptive HESS support table/figure for where "
            "physical-consistency diagnostics fail. Do not phrase snow/permafrost "
            "bins as causal attribution without an explicit independent "
            "permafrost/snow analysis."
        ),
    ]
    OUT_NOTES.write_text("\n".join(lines) + "\n")


def main() -> None:
    """Build CSV, LaTeX, notes, and figure outputs."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    budyko, aet = _load_inputs()
    summary = build_summary(budyko, aet)
    focus_cols = [
        "scope",
        "stratum_group",
        "stratum",
        "product",
        "n_budyko",
        "q_gt_p_pct",
        "budyko_envelope_violation_pct",
        "n_aet",
        "aet_wb_gt_pet_pct",
        "aet_wb_lt_zero_pct",
        "median_p_mm_yr",
        "median_aet_wb_div_gleam",
    ]
    focus = summary.loc[
        summary["scope"].eq("dam_excluded_clean")
        & summary["stratum_group"].isin(
            ["all", "area_class", "snow_fraction_proxy", "permafrost_proxy"]
        ),
        focus_cols,
    ].copy()

    summary.to_csv(OUT_SUMMARY, index=False, float_format="%.6g")
    focus.to_csv(OUT_FOCUS, index=False, float_format="%.6g")
    focus.to_latex(OUT_TEX, index=False, escape=True, float_format=lambda value: f"{value:.1f}")
    plot_summary(summary)
    _write_notes(summary)

    overall = focus.loc[focus["stratum_group"].eq("all")]
    era5 = overall.loc[overall["product"].eq("ERA5-Land")].iloc[0]
    mswep = overall.loc[overall["product"].eq("MSWEP")].iloc[0]
    print(f"Wrote {OUT_SUMMARY.relative_to(ROOT)}")
    print(f"Wrote {OUT_FOCUS.relative_to(ROOT)}")
    print(f"Wrote {OUT_PNG.relative_to(ROOT)}")
    if OVERLEAF_OUT_PNG.exists():
        print(f"Copied {OVERLEAF_OUT_PNG.relative_to(ROOT)}")
    print(
        "Dam-excluded overall AET_wb > PET: "
        f"ERA5-Land {float(era5['aet_wb_gt_pet_pct']):.1f}% / "
        f"MSWEP {float(mswep['aet_wb_gt_pet_pct']):.1f}%"
    )


if __name__ == "__main__":
    main()
