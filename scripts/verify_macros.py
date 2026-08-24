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

from coldregion_robustness import load_subset  # noqa: E402

# Must match scripts/plot_coldregion_gradient.py: the macros are checked against the same
# subset the figure plots, not a differently screened one.
MIN_WINTER_COVERAGE = 0.95

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
    match = None if match is None else bool(match)  # numpy bools would dodge the `is False` test
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
    r"""Extract the leading signed number from a macro value (strips {,}, \,, \%, units, \xspace)."""
    s = (
        raw.replace("\\xspace", "")
        .replace("\\%", "")
        .replace("{,}", "")
        .replace("\\,", "")
        .replace(",", "")
    )
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
    """Reconcile the Table 7 water-balance macros against paper/tables/forcing_water_balance.csv."""
    section("FORCING WATER BALANCE (paper/tables/forcing_water_balance.csv)")
    table = PAPER / "tables" / "forcing_water_balance.csv"
    if not table.exists():
        print("  SKIP — forcing_water_balance.csv absent; run scripts/generate_budyko_figure.py")
        return
    wb = pd.read_csv(table).set_index("product")
    for product, suffix in (("ERA5-Land", "erafive"), ("MSWEP", "mswep"), ("GPCP", "gpcp")):
        row = wb.loc[product]
        check_macro(macros, f"qpmedian{suffix}", float(row["median_runoff_ratio"]), "{:.3f}")
        check_macro(macros, f"qpgtone{suffix}", float(row["runoff_ratio_gt_1_pct"]), "{:.1f}")
        check_macro(macros, f"aetgtpet{suffix}", float(row["aet_wb_gt_pet_pct"]), "{:.1f}")
        check_macro(macros, f"budykobelow{suffix}", float(row["below_budyko_pct"]), "{:.1f}")
        check_macro(macros, f"budykodep{suffix}", float(row["median_budyko_departure"]), "{:+.3f}")
    check_macro(macros, "nwaterbalgauges", float(wb["n_gauges"].iloc[0]), "{:.0f}")


def check_coldregion_macros(macros: dict[str, str]) -> None:
    """Reconcile the Sect. 7 cold-region macros against a fresh recompute from the release."""
    section("COLD-REGION GRADIENT (release signatures + attributes)")
    cr = load_subset()
    # The figure screens on the released winter_coverage column; recompute on the same subset
    # or the macros would be checked against a different sample than the one plotted.
    cr = cr[(cr["winter_coverage"] >= MIN_WINTER_COVERAGE) & cr["winter_flow_ratio"].notna()]
    edges = [0, 5, 10, 20, 30, 50, 70, 100]
    cats = pd.cut(cr["prm_pc_use"].clip(0, 100), bins=edges, include_lowest=True)
    wff_med = cr["winter_flow_ratio"].groupby(cats, observed=True).median()
    bfi_med = cr["baseflow_index"].groupby(cats, observed=True).median()
    rho_winter = float(spearmanr(cr["prm_pc_use"], cr["winter_flow_ratio"], nan_policy="omit")[0])
    rho_bfi = float(spearmanr(cr["prm_pc_use"], cr["baseflow_index"], nan_policy="omit")[0])
    rho_qcv = float(spearmanr(cr["baseflow_index"], cr["q_cv"], nan_policy="omit")[0])

    check_macro(macros, "ncoldregiongauges", len(cr), "{:.0f}")
    check_macro(macros, "ncoldregionclipped", float((cr["winter_flow_ratio"] > 1.2).sum()), "{:.0f}")
    check_macro(macros, "winterratiobaseline", float(wff_med.iloc[0]), "{:.2f}")
    check_macro(macros, "winterratiohigh", float(wff_med.iloc[-1]), "{:.2f}")
    check_macro(macros, "bfipermafrostbaseline", float(bfi_med.iloc[0]), "{:.2f}")
    check_macro(macros, "bfipermafrostpeak", float(bfi_med.max()), "{:.2f}")
    check_macro(macros, "bfipermafrosthigh", float(bfi_med.iloc[-1]), "{:.2f}")
    # Signed macros carry a LaTeX $...$ wrapper, so compare the rendered string.
    for name, value in (
        ("rhopermafrostwinter", rho_winter),
        ("rhopermafrostbfi", rho_bfi),
        ("rhobfiqcv", rho_qcv),
    ):
        check_val(name, macros.get(name, "").replace("\\xspace", ""), f"${value:+.2f}$")
    verdict_path = RESULTS_HESS / "coldregion_robustness_verdict.txt"
    if verdict_path.exists():
        m_agree = re.search(r"agreement\s*=\s*([+-]?\d+\.\d+)", verdict_path.read_text())
        agreement = float(m_agree.group(1)) if m_agree else float("nan")
        check_macro(macros, "bfieckhardtagreement", agreement, "{:.2f}")
    else:
        print(
            "  SKIP bfieckhardtagreement — verdict.txt absent (gitignored); run coldregion_robustness.py"
        )


def check_winter_gap_macros(
    macros: dict[str, str], gauge_summary: pd.DataFrame, gap: pd.Series, severe: pd.Series
) -> None:
    """Lock the Sect. 4.1.1 winter-gap counts and their per-grade shares."""
    check_macro(macros, "nwintergap", float(gap.sum()), "{:.0f}")
    check_macro(macros, "nwintergapsevere", float(severe.sum()), "{:.0f}")
    grade_of = gauge_summary.set_index(gauge_summary["gauge_id"].astype(str))["overall_grade"]
    gap_grades = grade_of.reindex(gap.index[gap]).value_counts()
    for g in ["A", "B", "C", "D", "F"]:
        share = 100.0 * gap_grades.get(g, 0) / (grade_of == g).sum()
        check_macro(macros, f"wintergappct{g}", share, "{:.0f}")


def check_flag_frequency_table(macros: dict[str, str], year_grades: pd.DataFrame) -> None:
    """Lock the Table 3 share-of-years literals to paper/tables/flag_frequencies.csv."""
    section("FLAG FREQUENCIES (paper/tables/flag_frequencies.csv vs tables/quality_flags.tex)")
    freq = pd.read_csv(PAPER / "tables" / "flag_frequencies.csv")
    cols = [c for c in year_grades.columns if c.isdigit()]
    check_macro(macros, "nassessedyears", float(year_grades[cols].notna().sum().sum()), "{:,.0f}")
    check_val(
        "flag census assessed years",
        str(int(freq["n_assessed_years"].iloc[0])),
        str(int(year_grades[cols].notna().sum().sum())),
    )
    share = freq.set_index("flag")["share_pct"]
    tex = (PAPER / "overleaf" / "tables" / "quality_flags.tex").read_text()
    for m in re.finditer(
        r"^& \\texttt\{([^}]*)\}\s*&\s*(?:Minor|Major|Critical)\s*&.*?& ([\d.]+) \\\\$", tex, re.M
    ):
        name = m.group(1).replace("\\allowbreak ", "").replace("\\_", "_")
        check_val(f"Table 3 {name}", f"{share.get(name, 0.0):.1f}", m.group(2))


def blank_interior_years(year_grades: pd.DataFrame) -> tuple[int, int]:
    """Count unassessed hydro-years between the first and last graded year of each gauge."""
    grid = year_grades.set_index(year_grades.columns[0]).notna().to_numpy()
    n_blank = 0
    n_gauges = 0
    for mask in grid:
        idx = np.flatnonzero(mask)
        if len(idx) == 0:
            continue
        inner = ~mask[idx[0] : idx[-1] + 1]
        if inner.any():
            n_blank += int(inner.sum())
            n_gauges += 1
    return n_blank, n_gauges


def check_discharge_fill_macros(macros: dict[str, str]) -> None:
    """Lock the discharge gap-fill macros against quality_flag==1 in discharge.nc."""
    section("DISCHARGE GAP-FILL (quality_flag in camels_ru_discharge.nc)")
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as qds:
        qf = qds["quality_flag"].values
        n_fill = int((qf == 1).sum())
        n_present = int((qf != 3).sum())
    fill_pct = 100.0 * n_fill / n_present if n_present else float("nan")
    check_macro(macros, "ndischargefilldays", n_fill, "{:,.0f}")
    check_macro(macros, "ndischargefillpct", fill_pct, "{:.3f}")
    section("WATER-LEVEL PROVENANCE (quality_flag in camels_ru_water_level.nc)")
    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as wds:
        wf = wds["quality_flag"].values
    n_present = int((wf != 3).sum())
    check_macro(macros, "nwaterlevelfilldays", float((wf == 1).sum()), "{:,.0f}")
    check_macro(macros, "nwaterlevelzerodays", float((wf == 2).sum()), "{:,.0f}")
    check_macro(macros, "nwaterlevelzeropct", 100.0 * (wf == 2).sum() / n_present, "{:.1f}")
    check_macro(macros, "nwaterlevelzerogauges", float((wf == 2).any(axis=1).sum()), "{:.0f}")


def check_water_balance_screen_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 4.1.2 water-balance-screen macros against the released signatures CSV."""
    section("WATER-BALANCE SCREEN (signatures + gauge_summary)")
    sig = pd.read_csv(RELEASE / "camels_ru_signatures.csv")
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    sig["gauge_id"] = sig["gauge_id"].astype(str)
    summary["gauge_id"] = summary["gauge_id"].astype(str)
    clean = sig[~sig["is_anomalous"].astype(bool)].drop_duplicates("gauge_id")
    flagged = clean[clean["water_balance_screen"].astype(bool)].merge(
        summary[["gauge_id", "overall_grade"]], on="gauge_id", how="left"
    )
    check_macro(macros, "nwaterbalscreen", float(len(flagged)), "{:.0f}")
    check_macro(
        macros, "nwaterbalscreengradea", float((flagged["overall_grade"] == "A").sum()), "{:.0f}"
    )
    check_macro(macros, "maxrunoffratio", float(flagged["runoff_ratio"].max()), "{:.1f}")


def check_precip_caption_macros(macros: dict[str, str]) -> None:
    """Lock the six Fig. 5 caption numbers against their provenance CSV."""
    section("FIG. 5 CAPTION (paper/tables/precip_comparison_caption.csv)")
    table = PAPER / "tables" / "precip_comparison_caption.csv"
    if not table.exists():
        print("  SKIP — run scripts/regenerate_precip_comparison_figure.py --caption-only")
        return
    row = pd.read_csv(table).iloc[0]
    for macro_name, column in (
        ("dperamswepmean", "mean_d_era5_mswep"),
        ("dpgpcpmswepmean", "mean_d_gpcp_mswep"),
        ("pctgpcpwetterwest", "pct_gpcp_wetter_west60"),
        ("dpgpcpwest", "mean_d_gpcp_west60"),
        ("pctgpcpdriereast", "pct_gpcp_drier_east100140"),
        ("dpgpcpeast", "mean_d_gpcp_east100140"),
    ):
        check_macro(macros, macro_name, float(row[column]), "{:.0f}")


def check_nested_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 6.5 nested mass-balance macros against the per-pair provenance CSV."""
    section("NESTED MASS BALANCE (paper/tables/nested_mass_balance.csv)")
    table = PAPER / "tables" / "nested_mass_balance.csv"
    if not table.exists():
        print("  SKIP — run scripts/nested_mass_balance.py")
        return
    df = pd.read_csv(table, dtype={"up": str, "down": str})
    fail = df["v_ratio"] <= 1
    informative = df["area_ratio"] <= 2
    big = df["area_ratio"] > 5
    yield_ratio = df["v_ratio"] / df["area_ratio"]
    check_macro(macros, "nnestedpairs", float(len(df)), "{:.0f}")
    check_macro(macros, "pctnestedpass", float(100.0 * (~fail).mean()), "{:.1f}")
    check_macro(macros, "nnestedviolations", float(fail.sum()), "{:.0f}")
    check_macro(macros, "nnestedviolbig", float((fail & (df["area_ratio"] > 2)).sum()), "{:.0f}")
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    summary["gauge_id"] = summary["gauge_id"].astype(str)
    grade = summary.set_index("gauge_id")["overall_grade"]
    check_macro(
        macros, "nnestedviolgradea", float((df.loc[fail, "up"].map(grade) == "A").sum()), "{:.0f}"
    )
    check_macro(macros, "nnestedinformative", float(informative.sum()), "{:.0f}")
    check_macro(macros, "pctnestedinformativefail", float(100.0 * fail[informative].mean()), "{:.1f}")
    check_macro(macros, "pctnestedbigshare", float(100.0 * big.mean()), "{:.1f}")
    check_macro(macros, "pctnestedbigfail", float(100.0 * fail[big].mean()), "{:.1f}")
    check_macro(macros, "nnestedgauges", float(pd.concat([df["up"], df["down"]]).nunique()), "{:.0f}")
    check_macro(macros, "nestedyieldlow", float(100.0 * (yield_ratio < 0.5).mean()), "{:.1f}")
    check_macro(macros, "nestedyieldhigh", float(100.0 * (yield_ratio > 2).mean()), "{:.1f}")
    strat = PAPER / "tables" / "nested_stratification.csv"
    if strat.exists():
        s = pd.read_csv(strat)
        check_val(
            "stratification CSV total pairs",
            str(len(df)),
            str(int(s.loc[s["band"] == "All", "n_pairs"].iloc[0])),
        )
    else:
        print("  SKIP stratification CSV — run scripts/nested_mass_balance.py --table-only")


def check_spike_threshold_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 4.1.1 spike-threshold sensitivity against its provenance CSV."""
    section("SPIKE THRESHOLD SENSITIVITY (paper/tables/spike_threshold_sensitivity.csv)")
    table = PAPER / "tables" / "spike_threshold_sensitivity.csv"
    if not table.exists():
        print("  SKIP — run scripts/spike_threshold_sensitivity.py")
        return
    df = pd.read_csv(table).set_index("sigma_threshold")
    check_macro(macros, "spikeflagfive", float(df.loc[5.0, "pct_flagged"]), "{:.0f}%")
    check_macro(macros, "spikeflageight", float(df.loc[8.0, "pct_flagged"]), "{:.0f}%")


def check_stage_screen_encoding_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 8.2 encoding counts against what np.unique actually returns.

    The screen is defined on the full catchment grid, so the file carries more -1 values
    than the water-level gauges that could not be tested; both numbers are correct in
    their own scope and Sect. 8.2 describes the file.
    """
    section("STAGE-SCREEN ENCODING (water_level.nc)")
    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as ds:
        screen = ds["stage_discharge_screen"].values
        gauge_type = ds["gauge_type"].values
    check_macro(macros, "nstagescreenunassessed", float((screen == -1).sum()), "{:.0f}")
    check_macro(macros, "nnowaterlevel", float((gauge_type == -1).sum()), "{:.0f}")


def check_grade_regime_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 4.1.2 grade--regime macros against the release CSVs.

    Recomputed here rather than read from paper/tables/grade_regime.csv, so the
    lock is against the data and not against the provenance script's own output.
    """
    section("GRADE--REGIME CONFOUND (gauge_summary + attributes)")
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    attrs = pd.read_csv(RELEASE / "camels_ru_attributes.csv")
    df = summary.merge(attrs[["gauge_id", "snw_pc_uyr", "prm_pc_use"]], on="gauge_id", how="left")
    df["prm_pc_use"] = df["prm_pc_use"].clip(0, 100)
    is_a = df["overall_grade"] == "A"

    check_macro(macros, "gradeApct", 100.0 * is_a.mean(), "{:.0f}")
    covered = df["snw_pc_uyr"].notna().sum()
    check_macro(macros, "ngradebandcovered", float(covered), "{:.0f}")

    # Sect. 9 states cold-region coverage as counts rather than a superlative, so lock them.
    check_macro(macros, "npermafrosttwenty", float((df["prm_pc_use"] > 20).sum()), "{:.0f}")
    check_macro(macros, "npermafrosteighty", float((df["prm_pc_use"] > 80).sum()), "{:.0f}")

    low_snow = df["snw_pc_uyr"] < 20
    high_snow = df["snw_pc_uyr"] >= 50
    check_macro(macros, "nlowsnow", float(low_snow.sum()), "{:.0f}")
    check_macro(macros, "gradeAlowsnow", 100.0 * is_a[low_snow].mean(), "{:.0f}")
    check_macro(macros, "gradeAhighsnow", 100.0 * is_a[high_snow].mean(), "{:.0f}")
    check_macro(
        macros,
        "gradeBlowsnow",
        100.0 * (df.loc[low_snow, "overall_grade"] == "B").mean(),
        "{:.0f}",
    )

    no_pf = df["prm_pc_use"] == 0
    mid_pf = (df["prm_pc_use"] > 0) & (df["prm_pc_use"] <= 20)
    high_pf = df["prm_pc_use"] >= 80
    check_macro(macros, "nhighpermafrostgraded", float(high_pf.sum()), "{:.0f}")
    check_macro(macros, "gradeAnopermafrost", 100.0 * is_a[no_pf].mean(), "{:.0f}")
    check_macro(macros, "gradeAmidpermafrost", 100.0 * is_a[mid_pf].mean(), "{:.0f}")
    check_macro(macros, "gradeAhighpermafrost", 100.0 * is_a[high_pf].mean(), "{:.0f}")
    check_macro(
        macros,
        "gradeDFhighpermafrost",
        100.0 * df.loc[high_pf, "overall_grade"].isin(["D", "F"]).mean(),
        "{:.0f}",
    )


def check_plausibility_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 4.1.2 grade-vs-plausibility macros and the stage valid range.

    The stage bounds were hard-coded in Sect. 8.2 and drifted to a pre-rebuild value
    (-499 against an actual -434, then 0.5 after the out-of-range fills were reverted);
    they are recomputed here so a rebuild cannot desynchronise them again.
    """
    section("GRADE VS PLAUSIBILITY + WATER-LEVEL RANGE")
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as qds:
        anomaly = pd.Series(
            qds["specific_discharge_anomaly"].values,
            index=[str(g) for g in qds["gauge_id"].values],
        )
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    summary["gauge_id"] = summary["gauge_id"].astype(str)
    flagged = summary[summary["gauge_id"].isin(set(anomaly[anomaly == 1].index))]
    check_macro(
        macros, "nanomalygradeab", float(flagged["overall_grade"].isin(["A", "B"]).sum()), "{:.0f}"
    )
    check_macro(macros, "nanomalygradea", float((flagged["overall_grade"] == "A").sum()), "{:.0f}")

    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as wds:
        stage = wds["water_level_cm"].values
        flag = wds["quality_flag"].values
    # After the repair no altered value may sit outside its gauge's observed range, and
    # no stage may be negative: both were true of the v1.0 build and are what the
    # reversion removed. Assert them rather than only reporting the bounds.
    n_negative = int((np.isfinite(stage) & (stage < 0)).sum())
    check_val("water-level negatives", "0", str(n_negative))
    observed = np.where(flag == 0, stage, np.nan)
    stage_min, obs_min = float(np.nanmin(stage)), float(np.nanmin(observed))
    check_val("stage min (cm)", "0.50", f"{stage_min:.2f}")
    # The point of the repair: the released stage is bounded by what was observed.
    check_val("stage min == observed min", "True", str(abs(stage_min - obs_min) < 1e-6))
    # \nwlreverted is not recomputable post-repair (the reverted values are gone), so it
    # is locked by scripts/repair_water_level_fills.py --dry-run against the backup, not here.


def check_stage_discharge_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 6.4 stage--discharge macros against the release flag and provenance CSV."""
    section("STAGE--DISCHARGE CONSISTENCY (stage_discharge_screen + provenance CSV)")
    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as wds:
        screen = wds["stage_discharge_screen"].values
        gauge_type = wds["gauge_type"].values
    check_macro(macros, "nstageweak", float((screen == 1).sum()), "{:.0f}")
    check_macro(macros, "nstageunassessed", float(((gauge_type >= 0) & (screen == -1)).sum()), "{:.0f}")

    csv = REPO / "paper" / "tables" / "stage_discharge.csv"
    if not csv.exists():
        print("  SKIP rho macros — stage_discharge.csv absent; run stage_discharge_consistency.py")
        return
    sd = pd.read_csv(csv)
    river = sd[sd["gauge_type"] == 0].dropna(subset=["rho_open_water"])
    check_macro(macros, "nstagedischarge", float(len(river)), "{:.0f}")
    check_macro(macros, "rhostagemedian", river["rho_open_water"].median(), "{:.2f}")
    check_macro(macros, "rhostagemedianallyear", river["rho_all"].dropna().median(), "{:.2f}")
    check_macro(macros, "pctstagestrong", 100.0 * (river["rho_open_water"] >= 0.9).mean(), "{:.0f}")
    check_macro(macros, "pctstagegood", 100.0 * (river["rho_open_water"] >= 0.8).mean(), "{:.0f}")
    check_macro(macros, "nstageinverted", float((river["rho_open_water"] <= -0.5).sum()), "{:.0f}")


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
        q_present = ~np.isnan(qds["discharge_mm"])
        q_has_data = q_present.any(dim="time")
        n_with_data = int(q_has_data.sum().values)
        q_coord = "gauge_id" if "gauge_id" in qds.coords else "gauge"
        q_ids = qds[q_coord].values.astype(str)
        q_obs_days = pd.Series(q_present.sum(dim="time").values, index=q_ids)
        q_anomaly_ids = set(q_ids[qds["specific_discharge_anomaly"].values == 1])
        n_q_anomaly = len(q_anomaly_ids)
        q_months = pd.DatetimeIndex(qds["time"].values).month
        q_summer = q_present.values[:, q_months.isin([6, 7, 8, 9])].mean(axis=1)
        q_winter = q_present.values[:, q_months.isin([12, 1, 2, 3])].mean(axis=1)
    n_ungraded = n_with_data - n_graded
    # Winter-gap gauges (Sect. 4.1.1): summer coverage > 80 % but under half of Dec-Mar days
    winter_gap = pd.Series((q_summer > 0.8) & (q_winter < 0.5), index=q_ids)
    winter_gap_severe = winter_gap & pd.Series(q_winter < 0.2, index=q_ids)

    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as wds:
        wl_has_data = (~np.isnan(wds["water_level_cm"])).any(dim="time")
        n_waterlevel = int(wl_has_data.sum().values)
        wl_coord = "gauge_id" if "gauge_id" in wds.coords else "gauge"
        wl_ids = pd.Series(wds[wl_coord].values.astype(str))
        wl_in_analysis = ~wl_ids.map(is_paper_analysis_excluded_gauge_id).to_numpy()
        n_waterlevel_analysis = int((wl_has_data.values.astype(bool) & wl_in_analysis).sum())

    # Record-overlap macros (Sect. 2.2): both / any / none, and short records below the
    # 3-year (1095 observed-day) grading prerequisite of scripts/GradeCompound.py.
    q_flags = pd.Series(q_has_data.values.astype(bool), index=q_ids)
    wl_flags = pd.Series(wl_has_data.values.astype(bool), index=wl_ids.to_numpy())
    wl_flags = wl_flags.reindex(q_flags.index, fill_value=False)
    n_any_record = int((q_flags | wl_flags).sum())
    check_macro(macros, "nbothrecords", float((q_flags & wl_flags).sum()), "{:.0f}")
    check_macro(macros, "nanyrecord", float(n_any_record), "{:.0f}")
    check_macro(macros, "nnorecord", float(n_boundaries - n_any_record), "{:.0f}")
    check_macro(macros, "nshortrecord", float((q_obs_days[q_flags] < 365 * 3).sum()), "{:.0f}")

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
    check_macro(macros, "ngraded", float(n_graded), "{:.0f}")
    check_macro(macros, "nungraded", float(n_ungraded), "{:.0f}")
    check_macro(macros, "nqanomalygauges", float(n_q_anomaly), "{:.0f}")
    sig_anomaly_ids = set(sigs.loc[sigs["is_anomalous"].astype(bool), "gauge_id"].astype(str))
    check_macro(macros, "nqanomalyinsig", float(len(q_anomaly_ids & sig_anomaly_ids)), "{:.0f}")
    n_blank, n_blank_gauges = blank_interior_years(year_grades)
    check_macro(macros, "nblankyears", float(n_blank), "{:.0f}")
    check_macro(macros, "nblankyeargauges", float(n_blank_gauges), "{:.0f}")
    # year_grades.csv must list exactly the graded gauges of gauge_summary.csv.
    check_macro(macros, "ngraded", float(n_year_grades), "{:.0f}")

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
    # §2.3 / §5.1 attribute statistics over the Analysis set (renormalised attributes, 2026-08-23)
    analysis_attrs = attrs.loc[~attrs["gauge_id"].astype(str).map(is_paper_analysis_excluded_gauge_id)]
    check_macro(
        macros, "permafrostabsentpct", 100.0 * (analysis_attrs["prm_pc_use"] == 0).mean(), "{:.0f}"
    )
    check_macro(macros, "npermafrostninety", float((analysis_attrs["prm_pc_use"] >= 90).sum()), "{:.0f}")
    check_macro(macros, "nforesteighty", float((analysis_attrs["for_pc_use"] > 80).sum()), "{:.0f}")
    check_macro(macros, "ncroplandfifty", float((analysis_attrs["crp_pc_use"] > 50).sum()), "{:.0f}")
    check_macro(macros, "nurbanten", float((analysis_attrs["urb_pc_use"] > 10).sum()), "{:.0f}")
    check_macro(macros, "minelevation", float(attrs["ele_mt_uav"].min()), "{:.0f}")
    check_macro(macros, "maxelevation", float(attrs["ele_mt_uav"].max()), "{:.0f}")
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
    check_macro(macros, "nsignrows", float(n_sig_rows), "{:.0f}")
    check_macro(macros, "nsignanomalous", float(n_sig_anomalous), "{:.0f}")
    check_macro(macros, "nsigngauges", float(n_sig_clean), "{:.0f}")
    clean_sigs = sigs.loc[~sigs["is_anomalous"].astype(bool)]
    check_macro(macros, "nhalfflowgauges", float(clean_sigs["half_flow_date"].notna().sum()), "{:.0f}")
    check_macro(macros, "nwaterbalgauges", float(clean_sigs["runoff_ratio"].notna().sum()), "{:.0f}")

    section("GAUGE QUALITY BREAKDOWN (from year_grades.csv)")
    cols = [c for c in year_grades.columns if c.isdigit()]
    year_grades["all_A"] = year_grades[cols].apply(lambda r: all(v == "A" for v in r.dropna()), axis=1)
    strict_a = int(year_grades["all_A"].sum())
    check_macro(macros, "nhighquality", float(strict_a), "{:.0f}")
    for g in ["A", "B", "C", "D", "F"]:
        check_macro(macros, f"ngrade{g}", float((gauge_summary["overall_grade"] == g).sum()), "{:.0f}")
    n_decent = int(gauge_summary["overall_grade"].isin(["A", "B", "C"]).sum())
    check_macro(macros, "decentpct", 100.0 * n_decent / n_with_data, "{:.0f}")
    check_winter_gap_macros(macros, gauge_summary, winter_gap, winter_gap_severe)
    check_flag_frequency_table(macros, year_grades)

    section("CATCHMENT AREA STATISTICS (boundaries.gpkg area_km2)")
    areas = boundaries["area_km2"].dropna()
    kv("minarea", "0.49", f"{areas.min():.2f}", match=abs(areas.min() - 0.49) < 0.01)
    kv(
        "maxarea",
        "2,670,000",
        f"{areas.max():,.0f}",
        match=abs(areas.max() - 2_670_000) < 500,
    )
    # The Table 1 cell references \minareanum/\maxareanum, so the number lives once in
    # macros.tex; lock those macros against the recomputed areas instead of a cell literal.
    table1 = (PAPER / "overleaf" / "tables" / "camels_comparison.tex").read_text()
    check_val(
        "Table 1 CAMELS-RU area range cell",
        "\\minareanum{} to \\maxareanum",
        "\\minareanum{} to \\maxareanum" if "\\minareanum{} to \\maxareanum" in table1 else "literal",
    )
    check_macro(parse_macros(), "minareanum", float(areas.min()), "{:.2f}")
    check_macro(parse_macros(), "maxareanum", float(round(areas.max(), -4)), "{:.0f}")
    check_macro(parse_macros(), "meanarea", float(areas.mean()), "{:.0f}")
    check_macro(parse_macros(), "medianarea", float(areas.median()), "{:.0f}")
    analysis_areas = boundaries.loc[
        boundaries["gauge_id"].astype(str).str.len() != 7, "area_km2"
    ].dropna()
    small_medium_pct = 100.0 * analysis_areas.between(100, 10_000).mean()
    check_macro(parse_macros(), "smallmediumpct", small_medium_pct, "{:.0f}")

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
    check_macro(macros, "ndamfreesigngauges", float(dam_free.sum()), "{:.0f}")
    check_macro(macros, "nregulatedsigngauges", float(regulated.sum()), "{:.0f}")
    check_macro(macros, "nunknownregulation", float(unknown_regulation.sum()), "{:.0f}")
    check_macro(macros, "nwaterbaldamfree", float(water_balance_dam_free.sum()), "{:.0f}")
    check_macro(macros, "nhalfflowdamfree", float(half_flow_dam_free.sum()), "{:.0f}")
    median_columns = {
        "mediandamfreedischarge": ("q_mean", "{:.3f}"),
        "mediandamfreerunoffratio": ("runoff_ratio", "{:.3f}"),
        "mediandamfreebaseflowindex": ("baseflow_index", "{:.3f}"),
        "mediandamfreefdcslope": ("fdc_slope", "{:.3f}"),
        "mediandamfreehalfflowday": ("half_flow_date", "{:.0f}"),
        "mediandamfreesnowcover": ("snw_pc_uyr", "{:.1f}"),
        "mediandamfreepermafrost": ("prm_pc_use", "{:.2f}"),
    }
    for macro_name, (column, fmt) in median_columns.items():
        check_macro(macros, macro_name, float(dam_merged.loc[dam_free, column].dropna().median()), fmt)

    section("PAPER-ANALYSIS PRECIPITATION TABLES")
    precip_table = pd.read_csv(PAPER / "tables" / "precip_dataset_comparison.csv")
    expected_precip = {  # (n, std); the mean is locked to the \...annual macro below
        "ERA5-Land": (3201, 225, "erafiveannual"),
        "MSWEP": (3201, 217, "mswepannual"),
        "GPCP": (3201, 207, "gpcpannual"),
    }
    macros = parse_macros()
    for _, row in precip_table.iterrows():
        dataset = str(row["Dataset"])
        exp_n, exp_std, mean_macro = expected_precip[dataset]
        # The composite \...annual macro expands \...annualnum, so the number lives once;
        # parse the numeric macro (the composite has no digits of its own to extract).
        exp_mean = int(macro_num(macros[f"{mean_macro}num"]))
        table_tex = (PAPER / "overleaf" / "tables" / "forcing_products.tex").read_text()
        cell = re.search(rf"^{re.escape(dataset)}\s*&\s*(\S+)", table_tex, re.M).group(1)
        check_val(f"{dataset} forcing-table Mean P cell", f"\\{mean_macro}num", cell)
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

    agg_table = pd.read_csv(PAPER / "tables" / "aggregation_sensitivity.csv").set_index("band_km2")
    agg = agg_table.loc["150-500"]
    check_macro(macros, "aggpmedsmall", float(agg["p_median_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggpninetysmall", float(agg["p_p90_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggtmedsmall", float(agg["t_median_abs_degc"]), "{:.2f}")
    check_macro(macros, "aggtninetysmall", float(agg["t_p90_abs_degc"]), "{:.2f}")

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
    check_nested_macros(macros)
    check_precip_caption_macros(macros)
    check_coldregion_macros(macros)
    check_spike_threshold_macros(macros)
    check_stage_screen_encoding_macros(macros)
    check_water_balance_screen_macros(macros)
    check_grade_regime_macros(macros)
    check_plausibility_macros(macros)
    check_stage_discharge_macros(macros)
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
