#!/usr/bin/env python3
"""Summarize CAMELS-RU cold-region representativeness and 22-attribute selection.

This script creates small, auditable HESS-support artefacts from the released
attribute table.  It does not introduce new filters beyond the manuscript's
paper-analysis gauge-ID scope; it is meant to back Discussion wording about what
Russia adds to the CAMELS domain and to document the 22 primary HydroATLAS
attributes used in the manuscript.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.static.hydro_atlas_analysis import (  # noqa: E402
    CORRELATED_DROPS,
    FEATURE_DESCRIPTIONS,
)
from src.utils.paper_analysis_scope import filter_paper_analysis_index  # noqa: E402

RELEASE = ROOT / "release" / "CAMELS_RU_v1.0"
ATTRIBUTES = RELEASE / "camels_ru_attributes.csv"
OUT_DIR = ROOT / "results" / "hess_quality"
OUT_STATS = OUT_DIR / "cold_region_representativeness.csv"
OUT_NOTES = OUT_DIR / "cold_region_representativeness_notes.md"
OUT_PRIMARY = OUT_DIR / "hydroatlas_primary_attributes.csv"
OUT_DROPS = OUT_DIR / "hydroatlas_correlated_drops.csv"
OUT_TEX = OUT_DIR / "cold_region_discussion_snippet.tex"


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric column, preserving NaN for absent fields."""
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _count_pct(mask: pd.Series, denom: int) -> tuple[int, float]:
    """Return count and percent of True values."""
    n = int(mask.fillna(False).sum())
    return n, n / denom * 100.0 if denom else np.nan


def _add_threshold_rows(rows: list[dict[str, object]], df: pd.DataFrame) -> None:
    """Append reviewer-facing threshold statistics."""
    denom = int(len(df))
    thresholds = [
        ("snow_cover_proxy_gt25_pct", "snw_pc_uyr", ">", 25, "HydroATLAS snow-cover proxy >25%"),
        ("snow_cover_proxy_gt50_pct", "snw_pc_uyr", ">", 50, "HydroATLAS snow-cover proxy >50%"),
        ("permafrost_proxy_gt0_pct", "prm_pc_use", ">", 0, "HydroATLAS permafrost proxy >0%"),
        ("permafrost_proxy_gt10_pct", "prm_pc_use", ">", 10, "HydroATLAS permafrost proxy >10%"),
        ("permafrost_proxy_gt50_pct", "prm_pc_use", ">", 50, "HydroATLAS permafrost proxy >50%"),
        ("mean_annual_temp_lt0_pct", "tmp_dc_uyr", "<", 0, "HydroATLAS mean annual temperature <0 °C"),
        ("forest_cover_gt50_pct", "for_pc_use", ">", 50, "HydroATLAS forest cover >50%"),
        ("cropland_cover_gt25_pct", "crp_pc_use", ">", 25, "HydroATLAS cropland cover >25%"),
        ("aridity_index_gt1_pct", "ari_ix_uav", ">", 1, "HydroATLAS aridity index >1"),
    ]
    for key, column, op, threshold, label in thresholds:
        values = _numeric(df, column)
        mask = values.gt(threshold) if op == ">" else values.lt(threshold)
        n, pct = _count_pct(mask, denom)
        rows.append(
            {
                "metric": key,
                "label": label,
                "n": n,
                "denominator": denom,
                "value": pct,
                "unit": "% catchments",
            }
        )


def build_representativeness_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute compact cold-region and hydroclimatic representativeness stats."""
    rows: list[dict[str, object]] = [
        {
            "metric": "paper_analysis_hydroatlas_catchments",
            "label": "HydroATLAS-covered catchments in paper-analysis scope",
            "n": int(len(df)),
            "denominator": int(len(df)),
            "value": int(len(df)),
            "unit": "catchments",
        }
    ]
    _add_threshold_rows(rows, df)

    for column, label, unit in [
        ("snw_pc_uyr", "HydroATLAS snow-cover proxy", "%"),
        ("prm_pc_use", "HydroATLAS permafrost proxy", "%"),
        ("tmp_dc_uyr", "HydroATLAS mean annual temperature", "°C"),
        ("pre_mm_uyr", "HydroATLAS annual precipitation", "mm yr^-1"),
        ("pet_mm_uyr", "HydroATLAS annual PET", "mm yr^-1"),
        ("ari_ix_uav", "HydroATLAS aridity index", "unitless"),
        ("for_pc_use", "HydroATLAS forest cover", "%"),
        ("crp_pc_use", "HydroATLAS cropland cover", "%"),
        ("ele_mt_uav", "HydroATLAS elevation", "m"),
    ]:
        values = _numeric(df, column).dropna()
        if values.empty:
            continue
        rows.extend(
            [
                {
                    "metric": f"{column}_median",
                    "label": f"Median {label}",
                    "n": int(values.size),
                    "denominator": int(len(df)),
                    "value": float(values.median()),
                    "unit": unit,
                },
                {
                    "metric": f"{column}_iqr",
                    "label": f"IQR {label}",
                    "n": int(values.size),
                    "denominator": int(len(df)),
                    "value": f"{values.quantile(0.25):.3g}--{values.quantile(0.75):.3g}",
                    "unit": unit,
                },
            ]
        )
    return pd.DataFrame(rows)


def build_attribute_selection(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Document the 22 retained primary attributes and correlated drops."""
    primary_rows = []
    for name, meta in FEATURE_DESCRIPTIONS.items():
        values = _numeric(df, name)
        primary_rows.append(
            {
                "attribute": name,
                "short_label": meta.get("short", name),
                "category": meta.get("category", "uncategorized"),
                "present_in_release": bool(name in df.columns),
                "n_non_missing": int(values.notna().sum()),
                "median": float(values.median()) if values.notna().any() else np.nan,
            }
        )
    drop_rows = []
    candidate_names = [name for name in [*FEATURE_DESCRIPTIONS, *CORRELATED_DROPS] if name in df.columns]
    candidate_corr = df[candidate_names].apply(pd.to_numeric, errors="coerce").corr().abs()
    retained = [name for name in FEATURE_DESCRIPTIONS if name in df.columns]
    retained_corr = df[retained].apply(pd.to_numeric, errors="coerce")
    for name in CORRELATED_DROPS:
        values = _numeric(df, name)
        best_retained_match = ""
        best_retained_abs_r = np.nan
        best_candidate_match = ""
        best_candidate_abs_r = np.nan
        if name in df.columns and retained:
            retained_corrs = retained_corr.corrwith(values).abs().dropna()
            if not retained_corrs.empty:
                best_retained_match = str(retained_corrs.idxmax())
                best_retained_abs_r = float(retained_corrs.max())
        if name in candidate_corr.columns:
            candidate_corrs = candidate_corr[name].drop(index=name, errors="ignore").dropna()
            if not candidate_corrs.empty:
                best_candidate_match = str(candidate_corrs.idxmax())
                best_candidate_abs_r = float(candidate_corrs.max())
        drop_rows.append(
            {
                "dropped_attribute": name,
                "present_in_release": bool(name in df.columns),
                "n_non_missing": int(values.notna().sum()),
                "highest_abs_corr_retained_attribute": best_retained_match,
                "highest_abs_corr_with_retained": best_retained_abs_r,
                "highest_abs_corr_any_candidate_attribute": best_candidate_match,
                "highest_abs_corr_any_candidate": best_candidate_abs_r,
            }
        )
    return pd.DataFrame(primary_rows), pd.DataFrame(drop_rows)


def _value_float(stats: pd.DataFrame, metric: str) -> float:
    """Return a numeric metric value from the stats table."""
    row = stats.loc[stats["metric"].eq(metric)]
    if row.empty:
        raise KeyError(metric)
    return float(row.iloc[0]["value"])


def write_notes(stats: pd.DataFrame, primary: pd.DataFrame, drops: pd.DataFrame) -> None:
    """Write Markdown and LaTeX snippets for manuscript drafting."""
    n_attrs = int(_value_float(stats, "paper_analysis_hydroatlas_catchments"))
    snow25 = _value_float(stats, "snow_cover_proxy_gt25_pct")
    snow50 = _value_float(stats, "snow_cover_proxy_gt50_pct")
    permafrost0 = _value_float(stats, "permafrost_proxy_gt0_pct")
    permafrost50 = _value_float(stats, "permafrost_proxy_gt50_pct")
    temp_below0 = _value_float(stats, "mean_annual_temp_lt0_pct")
    forest50 = _value_float(stats, "forest_cover_gt50_pct")
    precip_median = _value_float(stats, "pre_mm_uyr_median")
    temp_median = _value_float(stats, "tmp_dc_uyr_median")

    all_primary_present = bool(primary["present_in_release"].all())
    lines = [
        "# CAMELS-RU HESS representativeness notes",
        "",
        (
            f"Scope: {n_attrs:,} HydroATLAS-covered catchments in the manuscript "
            "paper-analysis gauge-ID scope."
        ),
        "",
        "## Cold-region representativeness",
        f"- Snow-cover proxy >25%: {snow25:.1f}% of catchments; >50%: {snow50:.1f}%.",
        (
            f"- Permafrost proxy >0%: {permafrost0:.1f}% of catchments; "
            f">50%: {permafrost50:.1f}%."
        ),
        f"- Mean annual temperature below 0 °C: {temp_below0:.1f}% of catchments.",
        f"- Forest cover >50%: {forest50:.1f}% of catchments.",
        (
            f"- Median HydroATLAS annual precipitation: {precip_median:.0f} mm yr^-1; "
            f"median temperature: {temp_median:.1f} °C."
        ),
        "",
        "## Primary attributes",
        (
            f"- Retained primary attributes: {len(primary)}; "
            f"all present in release: {all_primary_present}."
        ),
        f"- Correlated dropped attributes documented: {len(drops)}.",
        (
            "- Use this as the traceability artefact for the 22-primary-attribute "
            "statement; do not imply that removed variables were omitted from the release."
        ),
    ]
    OUT_NOTES.write_text("\n".join(lines) + "\n")

    snippet_parts = [
        "Russia adds a cold-region domain that is weakly represented in existing ",
        "CAMELS-family datasets: within the ",
        f"{n_attrs:,} HydroATLAS-covered catchments in the paper-analysis scope, ",
        f"{snow25:.1f}\\% have a HydroATLAS snow-cover proxy above 25\\% ",
        f"({snow50:.1f}\\% above 50\\%), ",
        f"{permafrost0:.1f}\\% intersect non-zero permafrost proxy coverage ",
        f"({permafrost50:.1f}\\% above 50\\%), and ",
        f"{temp_below0:.1f}\\% have mean annual temperature below 0~$^\\circ$C. ",
        "The median HydroATLAS annual precipitation is ",
        f"{precip_median:.0f}~mm\\,yr$^{{-1}}$, with median mean annual temperature ",
        f"{temp_median:.1f}~$^\\circ$C. These values support the use of CAMELS-RU ",
        "as a cold-region benchmark, but they are HydroATLAS proxy summaries rather ",
        "than process attribution.\n",
    ]
    OUT_TEX.write_text("".join(snippet_parts))


def main() -> None:
    """Build HESS representativeness and primary-attribute artefacts."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    attributes = pd.read_csv(ATTRIBUTES, dtype={"gauge_id": str}).set_index("gauge_id")
    attributes = filter_paper_analysis_index(attributes)

    stats = build_representativeness_stats(attributes)
    primary, drops = build_attribute_selection(attributes)

    stats.to_csv(OUT_STATS, index=False, float_format="%.6g")
    primary.to_csv(OUT_PRIMARY, index=False, float_format="%.6g")
    drops.to_csv(OUT_DROPS, index=False, float_format="%.6g")
    write_notes(stats, primary, drops)

    print(f"Wrote {OUT_STATS.relative_to(ROOT)}")
    print(f"Wrote {OUT_NOTES.relative_to(ROOT)}")
    print(f"Wrote {OUT_PRIMARY.relative_to(ROOT)} ({len(primary)} primary attributes)")
    print(f"Wrote {OUT_DROPS.relative_to(ROOT)} ({len(drops)} correlated drops)")
    print(f"Wrote {OUT_TEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
