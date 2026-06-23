"""Verify paper macros against the released CAMELS-RU v1.0 dataset.

Produces a drift report for values that must be reflected in paper/overleaf/macros.tex
against the values computed directly from release/CAMELS_RU_v1.0/.

Run: pixi run python scripts/verify_macros.py
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for _p in (REPO, SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from coldregion_robustness import T_SPLIT, load_subset, shape_stats  # noqa: E402

from src.utils.paper_analysis_scope import (  # noqa: E402
    is_paper_analysis_excluded_gauge_id,
    paper_analysis_scope_summary,
)

RELEASE = REPO / "release" / "CAMELS_RU_v1.0"
RESULTS_HESS = REPO / "results" / "hess_quality"
PAPER = REPO / "paper"
MACROS = PAPER / "overleaf" / "macros.tex"

# Seven CAMELS-RU-derived columns appended to the 281 canonical HydroATLAS attributes in
# camels_ru_attributes.csv (used to derive \nattributesfull = 281 and \nattributescols = 288).
DERIVED_ATTR_COLS = (
    "ws_area",
    "acc",
    "height_bs",
    "lat",
    "lon",
    "area_fraction_used",
    "n_hydroatlas_polygons",
)


def section(title: str) -> None:
    """Print a report section heading."""
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


_FAILURES: list[str] = []


def kv(label: str, paper: str, actual: str, match: bool | None = None) -> None:
    """Print a labelled paper-versus-data comparison row; record drifts for the exit code."""
    mark = "OK " if match else ("DRIFT" if match is False else "  ? ")
    print(f"[{mark}] {label:40s}  paper={paper:25s}  actual={actual}")
    if match is False:
        _FAILURES.append(label)


def parse_macros() -> dict[str, str]:
    r"""Parse ``\newcommand{\name}{value}`` definitions from macros.tex into {name: value}."""
    text = MACROS.read_text(encoding="utf-8")
    pattern = r"\\newcommand\{\\([A-Za-z]+)\}\{((?:[^{}]|\{[^{}]*\})*)\}"
    return {m.group(1): m.group(2) for m in re.finditer(pattern, text)}


def macro_num(raw: str) -> float:
    r"""Extract the leading signed number from a macro value (strips {,}, \%, units, \xspace)."""
    s = raw.replace("\\xspace", "").replace("\\%", "").replace("{,}", "").replace(",", "")
    s = s.replace("−", "-")  # unicode minus -> ASCII
    m = re.search(r"[+-]?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else float("nan")


def check_macro(macros: dict[str, str], name: str, actual: float, fmt: str = "{:.1f}") -> None:
    """Compare the macros.tex value of ``name`` against a freshly computed value (3-way lock)."""
    exp_s = fmt.format(macro_num(macros.get(name, "nan")))
    act_s = fmt.format(actual)
    kv(name, exp_s, act_s, match=(exp_s == act_s))


def check_val(label: str, expected: str, actual: str) -> None:
    """Gate a hardcoded in-text value (no macro) against the recomputed value."""
    kv(label, expected, actual, match=(expected == actual))


def check_aet_macros(macros: dict[str, str]) -> None:
    """Reconcile the AET>PET headline macros + in-text Budyko trios against the audit table."""
    section("BUDYKO / AET ADEQUACY (results/hess_quality/budyko_aet_table.csv)")
    table = RESULTS_HESS / "budyko_aet_table.csv"
    if not table.exists():
        print("  SKIP — budyko_aet_table.csv absent (gitignored); run scripts/hess_quality_audit.py")
        return
    budyko = pd.read_csv(table).set_index("product")
    era5, mswep, gpcp = budyko.loc["ERA5-Land"], budyko.loc["MSWEP"], budyko.loc["GPCP"]
    check_macro(macros, "aetgtpeterafive", float(era5["aet_wb_gt_pet_pct"]), "{:.1f}")
    check_macro(macros, "aetgtpetmswep", float(mswep["aet_wb_gt_pet_pct"]), "{:.1f}")
    check_macro(macros, "aetgtpetgpcp", float(gpcp["aet_wb_gt_pet_pct"]), "{:.1f}")
    check_macro(macros, "naetcheckgauges", float(era5["aet_area_ge_50_n"]), "{:.0f}")
    # In-text hardcoded trios (§5.4, no macro) — gate against the audit table so they cannot drift.
    check_val(
        "in-text energy-viol E/M/G %",
        "8.1/2.0/3.4",
        f"{era5['energy_violation_pct']:.1f}/"
        f"{mswep['energy_violation_pct']:.1f}/{gpcp['energy_violation_pct']:.1f}",
    )
    check_val(
        "in-text aridity median E/M/G",
        "0.91/1.02/0.92",
        f"{era5['median_aridity_index']:.2f}/"
        f"{mswep['median_aridity_index']:.2f}/{gpcp['median_aridity_index']:.2f}",
    )
    check_val(
        "in-text evaporative median E/M/G",
        "0.67/0.61/0.66",
        f"{era5['median_evaporative_index']:.2f}/"
        f"{mswep['median_evaporative_index']:.2f}/{gpcp['median_evaporative_index']:.2f}",
    )


def check_coldregion_macros(macros: dict[str, str]) -> None:
    """Reconcile the §4.3 cold-region macros against a fresh recompute + the committed verdict."""
    section("COLD-REGION ROBUSTNESS (coldregion_robustness.py + verdict.txt)")
    cr = load_subset()
    warm = cr[cr["tmp_dc_uyr"] >= T_SPLIT]
    cold = cr[cr["tmp_dc_uyr"] < T_SPLIT]
    cr_shape = shape_stats(cr["prm_pc_use"], cr["baseflow_index"])
    rho_warm = float(spearmanr(warm["prm_pc_use"], warm["baseflow_index"])[0])
    rho_cold = float(spearmanr(cold["prm_pc_use"], cold["baseflow_index"])[0])
    # 9 of 10 cold-region macros recompute from release; the Eckhardt agreement needs the
    # (gitignored) verdict, so guard it for fresh clones rather than crashing.
    check_macro(macros, "ncoldregiongauges", len(cr), "{:.0f}")
    check_macro(macros, "ncoldregionwarm", len(warm), "{:.0f}")
    check_macro(macros, "ncoldregioncold", len(cold), "{:.0f}")
    check_macro(macros, "bfipermafrostbaseline", cr_shape["baseline_med"], "{:.2f}")
    check_macro(macros, "bfipermafrostpeak", cr_shape["peak_med"], "{:.2f}")
    check_macro(macros, "bfipermafrosthigh", cr_shape["high_med"], "{:.2f}")
    check_macro(macros, "rhopermafrostwarm", rho_warm, "{:.2f}")
    check_macro(macros, "rhopermafrostcold", rho_cold, "{:.2f}")
    verdict_path = RESULTS_HESS / "coldregion_robustness_verdict.txt"
    if verdict_path.exists():
        m_agree = re.search(r"agreement\s*=\s*([+-]?\d+\.\d+)", verdict_path.read_text())
        agreement = float(m_agree.group(1)) if m_agree else float("nan")
        check_macro(macros, "bfieckhardtagreement", agreement, "{:.2f}")
    else:
        print(
            "  SKIP bfieckhardtagreement — verdict.txt absent (gitignored); run coldregion_robustness.py"
        )


def check_discharge_fill_macros(macros: dict[str, str]) -> None:
    """Lock the discharge gap-fill macros against quality_flag==1 in discharge.nc."""
    section("DISCHARGE GAP-FILL (quality_flag in camels_ru_discharge.nc)")
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as qds:
        qf = qds["quality_flag"].values
        n_fill = int((qf == 1).sum())
        n_present = int((qf != 3).sum())
    fill_pct = 100.0 * n_fill / n_present if n_present else float("nan")
    check_macro(macros, "ndischargefilldays", n_fill, "{:,.0f}")
    check_macro(macros, "ndischargefillpct", fill_pct, "{:.2f}")


def report_drift_summary() -> None:
    """Print the drift summary; exit non-zero if any checked macro drifted from the data."""
    section("DRIFT SUMMARY")
    if _FAILURES:
        print(f"  {len(_FAILURES)} drift(s): {', '.join(_FAILURES)}")
        print(f"\nCross-reference with {MACROS.relative_to(REPO)}")
        sys.exit(1)
    print("  No drift — all checked macros reproduce from release + audit artifacts.")
    print(f"\nDone. Cross-reference with {MACROS.relative_to(REPO)}")


def main() -> None:
    """Run all macro consistency checks against the release bundle."""
    section("COUNTS")
    macros = parse_macros()

    attrs = pd.read_csv(RELEASE / "camels_ru_attributes.csv")
    gauge_summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    year_grades = pd.read_csv(RELEASE / "camels_ru_year_grades.csv")
    sig_summary = pd.read_csv(RELEASE / "camels_ru_signatures_summary.csv")
    sigs = pd.read_csv(RELEASE / "camels_ru_signatures.csv")
    boundaries = gpd.read_file(RELEASE / "camels_ru_boundaries.gpkg")

    n_attrs = len(attrs)
    n_boundaries = len(boundaries)
    n_graded = len(gauge_summary)
    n_year_grades = len(year_grades)
    n_signatures_defined = len(sig_summary)
    n_sig_rows = len(sigs)
    n_sig_clean = (
        int((~sigs["is_anomalous"].astype(bool)).sum()) if "is_anomalous" in sigs.columns else n_sig_rows
    )
    n_sig_anomalous = n_sig_rows - n_sig_clean
    paper_scope = paper_analysis_scope_summary(boundaries["gauge_id"].astype(str))
    paper_attr_scope = paper_analysis_scope_summary(attrs["gauge_id"].astype(str))

    # Ground truth for \ndischarge: gauges in discharge.nc with any non-NaN value
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as qds:
        q_has_data = (~np.isnan(qds["discharge_mm"])).any(dim="time")
        n_with_data = int(q_has_data.sum().values)
    n_ungraded = n_with_data - n_graded

    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as wds:
        wl_has_data = (~np.isnan(wds["water_level_cm"])).any(dim="time")
        n_waterlevel = int(wl_has_data.sum().values)
        wl_coord = "gauge_id" if "gauge_id" in wds.coords else "gauge"
        wl_ids = pd.Series(wds[wl_coord].values.astype(str))
        wl_in_analysis = ~wl_ids.map(is_paper_analysis_excluded_gauge_id).to_numpy()
        n_waterlevel_analysis = int((wl_has_data.values.astype(bool) & wl_in_analysis).sum())

    kv(
        "ntotal (boundaries.gpkg polygons)",
        "3,353",
        f"{n_boundaries}",
        match=n_boundaries == 3353,
    )
    kv(
        "nattrsgauges (attributes.csv rows)",
        "3,339",
        f"{n_attrs} (HydroATLAS-covered)",
        match=n_attrs == 3339,
    )
    kv(
        "ndischarge (discharge.nc gauges w/ any data)",
        "2,170",
        f"{n_with_data}",
        match=n_with_data == 2170,
    )
    kv(
        "ngraded (gauge_summary rows)",
        "2,067",
        f"{n_graded}",
        match=n_graded == 2067,
    )
    kv(
        "nungraded (data but no grade)",
        "103",
        f"{n_ungraded}",
        match=n_ungraded == 103,
    )
    kv(
        "year_grades rows",
        "2,067",
        f"{n_year_grades}",
        match=n_year_grades == 2067,
    )

    # ERA5-Land temperature gap-fill provenance: \nforcingfillgauges must equal the
    # number of rows shipped in camels_ru_forcing_notes.csv (all domain-edge gauges).
    forcing_notes = pd.read_csv(RELEASE / "camels_ru_forcing_notes.csv")
    check_macro(macros, "nforcingfillgauges", float(len(forcing_notes)), "{:.0f}")
    kv(
        "nwaterlevel (water_level.nc gauges w/ any data)",
        "2,989",
        f"{n_waterlevel}",
        match=n_waterlevel == 2989,
    )
    kv(
        "npaperanalysiscatchments (ID length < 7)",
        "3,201",
        f"{paper_scope.n_included}",
        match=paper_scope.n_included == 3201 and paper_scope.n_excluded == 152,
    )
    kv(
        "npaperanalysisattrsgauges",
        "3,187",
        f"{paper_attr_scope.n_included}",
        match=paper_attr_scope.n_included == 3187 and paper_attr_scope.n_excluded == 152,
    )
    kv(
        "npaperanalysisexcluded",
        "152",
        f"{paper_scope.n_excluded}",
        match=paper_scope.n_excluded == 152,
    )
    kv(
        "nwaterlevelanalysis",
        "2,837",
        f"{n_waterlevel_analysis}",
        match=n_waterlevel_analysis == 2837,
    )
    check_macro(macros, "nsignatures", float(n_signatures_defined), "{:.0f}")

    # Attribute-count macros, guarded so the abstract/§3/table literals cannot drift:
    #   \nattributescols = all CSV columns minus gauge_id (288)
    #   \nattributesfull = those minus the 7 CAMELS-RU-derived columns (281 HydroATLAS)
    #   \nattributes     = rows in the curated primary-subset table (22)
    n_attr_cols_total = len(attrs.columns) - 1  # exclude gauge_id
    n_derived_present = sum(c in attrs.columns for c in DERIVED_ATTR_COLS)
    check_macro(macros, "nattributescols", float(n_attr_cols_total), "{:.0f}")
    check_macro(macros, "nattributesfull", float(n_attr_cols_total - n_derived_present), "{:.0f}")
    attr_table_text = (PAPER / "overleaf" / "tables" / "hydroatlas_attributes.tex").read_text(
        encoding="utf-8"
    )
    n_primary_attrs = len(re.findall(r"[a-z]{3}\\_[a-z]{2}\\_[a-z]{3}", attr_table_text))
    check_macro(macros, "nattributes", float(n_primary_attrs), "{:.0f}")
    kv(
        "nsigngauges (signatures.csv cleaned)",
        "1,845",
        f"{n_sig_clean} (raw={n_sig_rows}, anomalous={n_sig_anomalous})",
        match=n_sig_clean == 1845,
    )

    section("GAUGE QUALITY BREAKDOWN (from year_grades.csv)")
    cols = [c for c in year_grades.columns if c.isdigit()]
    year_grades["all_A"] = year_grades[cols].apply(lambda r: all(v == "A" for v in r.dropna()), axis=1)
    strict_a = int(year_grades["all_A"].sum())
    kv("nhighquality (Grade A: every year A)", "849", f"{strict_a}", match=strict_a == 849)
    for g in ["A", "B", "C", "D", "F"]:
        n_g = int((gauge_summary["overall_grade"] == g).sum())
        kv(f"ngrade{g}", f"{ {'A': 849, 'B': 883, 'C': 148, 'D': 173, 'F': 14}[g] }", f"{n_g}")

    section("CATCHMENT AREA STATISTICS (boundaries.gpkg area_km2)")
    areas = boundaries["area_km2"].dropna()
    kv("minarea", "0.49", f"{areas.min():.2f}", match=abs(areas.min() - 0.49) < 0.01)
    kv(
        "maxarea",
        "2,670,000",
        f"{areas.max():,.0f}",
        match=abs(areas.max() - 2_670_000) < 500,
    )
    kv("meanarea", "78,217", f"{areas.mean():,.0f}", match=abs(areas.mean() - 78217) < 5)
    kv("medianarea", "2,817", f"{areas.median():,.0f}", match=abs(areas.median() - 2817) < 5)

    section("GEOGRAPHIC EXTENT (boundaries.gpkg total_bounds)")
    minlon, minlat, maxlon, maxlat = boundaries.total_bounds
    kv("minlat", "41.2", f"{minlat:.2f}", match=abs(minlat - 41.2) < 0.1)
    kv("maxlat", "73.0", f"{maxlat:.2f}", match=abs(maxlat - 73.0) < 0.1)
    kv("minlon", "19.9", f"{minlon:.2f}", match=abs(minlon - 19.9) < 0.1)
    kv("maxlon", "178.3", f"{maxlon:.2f}", match=abs(maxlon - 178.3) < 0.1)

    section("AREAL ERROR DISTRIBUTION (boundaries.gpkg area_diff_perc)")
    aep = boundaries["area_diff_perc"].dropna().abs()
    n_ref = len(aep)
    aep_trim = aep[aep <= 100]
    check_macro(macros, "nwithreference", n_ref, "{:.0f}")
    kv(
        "meanerror (|err|<=100% trim mean)",
        "5.1%",
        f"{aep_trim.mean():.2f}%",
        match=abs(aep_trim.mean() - 5.1) < 0.3,
    )
    kv("median |err| (no trim)", "-", f"{aep.median():.2f}%")
    kv(
        "withinfive (no trim)",
        "77%",
        f"{(aep < 5).mean() * 100:.1f}%",
        match=abs((aep < 5).mean() * 100 - 77) < 2,
    )
    kv(
        "withinten (no trim)",
        "87%",
        f"{(aep < 10).mean() * 100:.1f}%",
        match=abs((aep < 10).mean() * 100 - 87) < 2,
    )

    section("SIGNATURE SUMMARY (signatures_summary.csv)")
    print(sig_summary.to_string(index=False))

    section("SIGNATURE STATISTICS (derived from signatures.csv)")
    # Compute both means and medians on the released 1845-subset
    for col in [
        "q_mean",
        "baseflow_index",
        "fdc_slope",
        "half_flow_date",
        "aridity_index",
        "evaporative_index",
        "runoff_ratio",
    ]:
        if col in sigs.columns:
            s = sigs[col].dropna()
            print(
                f"  {col:22s}  n={len(s):<6d}  mean={s.mean():8.3f}  "
                f"median={s.median():8.3f}  min={s.min():8.3f}  max={s.max():8.3f}"
            )

    section("DAM-EXCLUDED BROAD-ANALYSIS MACROS")
    dam_attrs = attrs[["gauge_id", "dor_pc_pva", "snw_pc_uyr", "prm_pc_use"]].copy()
    dam_merged = sigs.merge(dam_attrs, on="gauge_id", how="left")
    dam_merged["dor_pc_pva"] = pd.to_numeric(dam_merged["dor_pc_pva"], errors="coerce")
    clean = ~dam_merged["is_anomalous"].astype(bool)
    dam_free = clean & dam_merged["dor_pc_pva"].eq(0)
    regulated = clean & dam_merged["dor_pc_pva"].gt(0)
    unknown_regulation = clean & dam_merged["dor_pc_pva"].isna()
    water_balance_dam_free = dam_free & dam_merged[
        ["runoff_ratio", "aridity_index", "evaporative_index"]
    ].notna().all(axis=1)
    half_flow_dam_free = dam_free & dam_merged["half_flow_date"].notna()
    kv("ndamfreesigngauges", "1,800", f"{int(dam_free.sum()):,}", match=int(dam_free.sum()) == 1800)
    kv(
        "nregulatedsigngauges",
        "43",
        f"{int(regulated.sum()):,}",
        match=int(regulated.sum()) == 43,
    )
    kv(
        "nunknownregulation",
        "2",
        f"{int(unknown_regulation.sum()):,}",
        match=int(unknown_regulation.sum()) == 2,
    )
    kv(
        "nwaterbaldamfree",
        "1,800",
        f"{int(water_balance_dam_free.sum()):,}",
        match=int(water_balance_dam_free.sum()) == 1800,
    )
    kv(
        "nhalfflowdamfree",
        "1,600",
        f"{int(half_flow_dam_free.sum()):,}",
        match=int(half_flow_dam_free.sum()) == 1600,
    )
    median_expectations = {
        "mediandamfreedischarge": ("q_mean", 0.697, "{:.3f}"),
        "mediandamfreerunoffratio": ("runoff_ratio", 0.333, "{:.3f}"),
        "mediandamfreebaseflowindex": ("baseflow_index", 0.555, "{:.3f}"),
        "mediandamfreefdcslope": ("fdc_slope", 2.370, "{:.3f}"),
        "mediandamfreehalfflowday": ("half_flow_date", 214.0, "{:.0f}"),
        "mediandamfreesnowcover": ("snw_pc_uyr", 45.8, "{:.1f}"),
        "mediandamfreepermafrost": ("prm_pc_use", 0.04, "{:.2f}"),
    }
    for macro_name, (column, expected, fmt) in median_expectations.items():
        actual = float(dam_merged.loc[dam_free, column].dropna().median())
        kv(
            macro_name,
            fmt.format(expected),
            fmt.format(actual),
            match=fmt.format(actual) == fmt.format(expected),
        )

    section("PAPER-ANALYSIS PRECIPITATION TABLES")
    precip_table = pd.read_csv(PAPER / "tables" / "precip_dataset_comparison.csv")
    expected_precip = {
        "ERA5-Land": (3201, 705, 225),
        "MSWEP": (3201, 609, 217),
        "GPCP": (3201, 657, 206),
    }
    for _, row in precip_table.iterrows():
        dataset = str(row["Dataset"])
        exp_n, exp_mean, exp_std = expected_precip[dataset]
        kv(
            f"{dataset} N gauges",
            f"{exp_n:,}",
            f"{int(row['N gauges']):,}",
            match=int(row["N gauges"]) == exp_n,
        )
        kv(
            f"{dataset} mean annual P",
            f"{exp_mean}",
            f"{int(row['Mean annual P (mm/yr)'])}",
            match=int(row["Mean annual P (mm/yr)"]) == exp_mean,
        )
        kv(
            f"{dataset} std annual P",
            f"{exp_std}",
            f"{int(row['Std annual P (mm/yr)'])}",
            match=int(row["Std annual P (mm/yr)"]) == exp_std,
        )

    corr_table = pd.read_csv(PAPER / "tables" / "precip_inter_dataset_corr.csv")
    expected_corr = {
        "ERA5-Land vs MSWEP": (3201, 0.915, 0.265),
        "ERA5-Land vs GPCP": (3201, 0.664, 0.126),
        "MSWEP vs GPCP": (3201, 0.725, -0.138),
    }
    for _, row in corr_table.iterrows():
        comparison = str(row["Comparison"])
        exp_n, exp_r, exp_bias = expected_corr[comparison]
        kv(
            f"{comparison} N gauges",
            f"{exp_n:,}",
            f"{int(row['N gauges']):,}",
            match=int(row["N gauges"]) == exp_n,
        )
        kv(
            f"{comparison} mean r",
            f"{exp_r:.3f}",
            f"{float(row['Mean r']):.3f}",
            match=f"{float(row['Mean r']):.3f}" == f"{exp_r:.3f}",
        )
        kv(
            f"{comparison} mean bias",
            f"{exp_bias:.3f}",
            f"{float(row['Mean bias (mm/day)']):.3f}",
            match=f"{float(row['Mean bias (mm/day)']):.3f}" == f"{exp_bias:.3f}",
        )

    section("FORCING NETCDF SUMMARY")
    forcing_nc = RELEASE / "camels_ru_forcing.nc"
    with xr.open_dataset(forcing_nc) as ds:
        print(f"  dims: {dict(ds.sizes)}")
        print(f"  vars: {list(ds.data_vars)}")
        print(f"  time range: {ds.time.min().values} → {ds.time.max().values}")
        n_gauges_forcing = ds.sizes.get("gauge_id", ds.sizes.get("gauge", -1))
        print(f"  gauge count (forcing): {n_gauges_forcing}")

        # Annual means
        if "pr_mswep" in ds.data_vars or "mswep" in ds.data_vars:
            p_var = "pr_mswep" if "pr_mswep" in ds.data_vars else "mswep"
            annual_mean = ds[p_var].resample(time="1YE").sum().mean(dim="time")
            print(f"  MSWEP annual mean (across gauges): {float(annual_mean.mean()):.1f} mm/yr")

    section("DISCHARGE NETCDF SUMMARY")
    discharge_nc = RELEASE / "camels_ru_discharge.nc"
    with xr.open_dataset(discharge_nc) as ds:
        print(f"  dims: {dict(ds.sizes)}")
        print(f"  vars: {list(ds.data_vars)}")
        print(f"  time range: {ds.time.min().values} → {ds.time.max().values}")
        n_gauges_q = ds.sizes.get("gauge_id", ds.sizes.get("gauge", -1))
        print(f"  gauge count (discharge): {n_gauges_q}")

    section("ARCHIVE SIZE")
    total_bytes = sum(p.stat().st_size for p in RELEASE.rglob("*") if p.is_file())
    total_gb = total_bytes / 1e9
    total_gib = total_bytes / 1024**3
    print(f"  uncompressed total: {total_gb:.2f} GB / {total_gib:.2f} GiB ({total_bytes:,} bytes)")

    # Try to get gzipped size if we can find the bundle
    zenodo_dir = REPO / "data" / "zenodo" if (REPO / "data").is_symlink() else None
    if zenodo_dir and zenodo_dir.exists():
        for tarball in zenodo_dir.glob("*.tar.gz"):
            gb = tarball.stat().st_size / 1024**3
            print(f"  {tarball.name}: {gb:.2f} GB gzipped")

    check_aet_macros(macros)
    check_coldregion_macros(macros)
    check_discharge_fill_macros(macros)

    section("AUTHORITATIVE VALUES FOR MACROS.TEX")
    print(f"  ntotal               = {n_attrs:,} (3,339 HydroATLAS-covered catchments)")
    print("                         OR 3,353 if 'total delineated' is intended")
    print(
        f"  npaperanalysiscatchments = {paper_scope.n_included:,} "
        f"({paper_scope.n_excluded} gauge-ID excluded)"
    )
    print(f"  npaperanalysisattrsgauges = {paper_attr_scope.n_included:,}")
    print(f"  ndischarge           = {n_with_data:,}")
    print(f"  nwaterlevel          = {n_waterlevel:,}")
    print(f"  nwaterlevelanalysis  = {n_waterlevel_analysis:,}")
    print(f"  nhighquality         = {strict_a:,}")
    print(f"  nsignatures          = {n_signatures_defined}")
    print(f"  nsigngauges          = {n_sig_clean:,}")
    print(f"  archive size (unc.)  = {total_gb:.2f} GB")

    report_drift_summary()


if __name__ == "__main__":
    main()
