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
from scipy.stats import mannwhitneyu, spearmanr
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
    paper_analysis_inclusion_mask,
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

    # Snow-fraction confound (Sect. 6.5): recompute from the released signatures and
    # attributes with the same Budyko (1974) curve as generate_budyko_figure.py.
    sig = pd.read_csv(RELEASE / "camels_ru_signatures.csv", dtype={"gauge_id": str})
    sig = sig[~sig["is_anomalous"].astype(bool)]
    attrs = pd.read_csv(RELEASE / "camels_ru_attributes.csv", usecols=["gauge_id", "snw_pc_uyr"])
    attrs["gauge_id"] = attrs["gauge_id"].astype(str)
    joined = sig.merge(attrs, on="gauge_id", how="left")

    def _budyko_curve(aridity: np.ndarray) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            val = aridity * np.tanh(1.0 / aridity) * (1.0 - np.exp(-aridity))
        return np.sqrt(np.clip(val, 0.0, None))

    dep_mswep = joined["evaporative_index"] - _budyko_curve(joined["aridity_index"].to_numpy())
    dep_era5 = joined["evaporative_index_era5"] - _budyko_curve(joined["aridity_index_era5"].to_numpy())
    low_snow = joined["snw_pc_uyr"] < 20
    rho_snow = float(spearmanr(joined["snw_pc_uyr"], dep_mswep, nan_policy="omit")[0])
    check_val(
        "rhosnowbudyko", macros.get("rhosnowbudyko", "").replace("\\xspace", ""), f"${rho_snow:+.2f}$"
    )
    check_macro(macros, "nlowsnowbudyko", float(low_snow.sum()), "{:.0f}")
    check_macro(macros, "budykodeplowsnowmswep", float(dep_mswep[low_snow].median()), "{:+.3f}")
    check_macro(macros, "budykodeplowsnowerafive", float(dep_era5[low_snow].median()), "{:+.3f}")


def check_coldregion_macros(macros: dict[str, str]) -> None:
    """Reconcile the Sect. 8 cold-region macros against a fresh recompute from the release."""
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
    check_macro(macros, "ncoldregionabovemean", float((cr["winter_flow_ratio"] > 1.0).sum()), "{:.0f}")
    check_macro(macros, "winterratiobaseline", float(wff_med.iloc[0]), "{:.2f}")
    check_macro(macros, "winterratiohigh", float(wff_med.iloc[-1]), "{:.2f}")
    # Sect. 8 in-text bin counts and the high-permafrost retention disclosure.
    bin_counts = cr["winter_flow_ratio"].groupby(cats, observed=True).count()
    check_macro(macros, "nwinterbinlow", float(bin_counts.iloc[0]), "{:.0f}")
    check_macro(macros, "nwinterbinhigh", float(bin_counts.iloc[-1]), "{:.0f}")
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv", dtype={"gauge_id": str})
    attrs = pd.read_csv(RELEASE / "camels_ru_attributes.csv", usecols=["gauge_id", "prm_pc_use"])
    attrs["gauge_id"] = attrs["gauge_id"].astype(str)
    high_perm = summary.merge(attrs, on="gauge_id", how="left")
    high_perm = high_perm[high_perm["prm_pc_use"] >= 80]
    check_macro(macros, "nhighpermafrostgraded", float(len(high_perm)), "{:.0f}")
    check_macro(
        macros,
        "nhighpermretained",
        float(high_perm["gauge_id"].isin(set(cr["gauge_id"])).sum()),
        "{:.0f}",
    )
    check_macro(macros, "bfipermafrostbaseline", float(bfi_med.iloc[0]), "{:.2f}")
    check_macro(macros, "bfipermafrostpeak", float(bfi_med.max()), "{:.2f}")
    check_macro(macros, "bfipermafrosthigh", float(bfi_med.iloc[-1]), "{:.2f}")
    # Identifiability disclosure (Sect. 8): temperature collinearity, coldest-quintile
    # attenuation, and the fixed-window freshet overlap (half-flow date inside Jan-Mar,
    # days 93-182 of the Oct-Sep hydrological year).
    rho_tp = float(spearmanr(cr["tmp_dc_uyr"], cr["prm_pc_use"], nan_policy="omit")[0])
    cold = cr[cr["tmp_dc_uyr"] <= cr["tmp_dc_uyr"].quantile(0.2)]
    rho_cold = float(spearmanr(cold["prm_pc_use"], cold["winter_flow_ratio"], nan_policy="omit")[0])
    in_win = (cr["half_flow_date"] >= 93) & (cr["half_flow_date"] <= 182)
    check_macro(macros, "nfreshetinwindow", float(in_win.sum()), "{:.0f}")
    check_macro(
        macros, "winterratiofreshetin", float(cr.loc[in_win, "winter_flow_ratio"].median()), "{:.2f}"
    )
    check_macro(
        macros, "winterratiofreshetout", float(cr.loc[~in_win, "winter_flow_ratio"].median()), "{:.2f}"
    )
    # Signed macros carry a LaTeX $...$ wrapper, so compare the rendered string.
    for name, value in (
        ("rhopermafrostwinter", rho_winter),
        ("rhopermafrostbfi", rho_bfi),
        ("rhobfiqcv", rho_qcv),
        ("rhotempperm", rho_tp),
        ("rhopermwintercoldq", rho_cold),
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
    # Base rate for the grade!=plausibility argument (round-7 writing M5): grade-A share
    # of the screened population vs of the whole non-anomalous signature set.
    check_macro(
        macros, "pctwaterbalscreengradea", 100.0 * (flagged["overall_grade"] == "A").mean(), "{:.0f}"
    )
    clean_grades = clean.merge(summary[["gauge_id", "overall_grade"]], on="gauge_id", how="left")
    check_macro(macros, "pctsigngradea", 100.0 * (clean_grades["overall_grade"] == "A").mean(), "{:.0f}")
    check_macro(macros, "maxrunoffratio", float(flagged["runoff_ratio"].max()), "{:.1f}")
    check_macro(macros, "nwaterbalscreenall", float(sig["water_balance_screen"].sum()), "{:.0f}")
    check_macro(macros, "nwinterflowgauges", float(clean["winter_flow_ratio"].notna().sum()), "{:.0f}")
    # Diagnosability of the runoff-ratio > 1 population (Sect. 4.1.2, domain m-6).
    boundaries = gpd.read_file(RELEASE / "camels_ru_boundaries.gpkg")
    boundaries["gauge_id"] = boundaries["gauge_id"].astype(str)
    rr1 = clean[clean["runoff_ratio"] > 1].merge(
        boundaries[["gauge_id", "area_diff_perc"]], on="gauge_id", how="left"
    )
    rest = clean[clean["runoff_ratio"] <= 1]
    check_macro(macros, "nrronewithref", float(rr1["area_diff_perc"].notna().sum()), "{:.0f}")
    check_macro(macros, "nrronebigerr", float((rr1["area_diff_perc"].abs() > 15).sum()), "{:.0f}")
    check_macro(macros, "nrroneerafive", float((rr1["runoff_ratio_era5"] > 1).sum()), "{:.0f}")
    check_macro(macros, "rronemedarea", float(rr1["area_km2"].median()), "{:.0f}")
    check_macro(macros, "nonrronemedarea", float(rest["area_km2"].median()), "{:.0f}")


def check_grdc_gates(macros: dict[str, str]) -> None:
    """Gate the Sect. 6.1 GRDC statistics and inventory against the committed CSVs."""
    section("GRDC CROSS-CHECK (paper/tables/grdc_validation.csv + grdc_inventory.csv)")
    inventory = PAPER / "tables" / "grdc_inventory.csv"
    if inventory.exists():
        inv = pd.read_csv(inventory).iloc[0]
        check_macro(macros, "ngrdcstations", float(inv["n_ru_stations"]), "{:.0f}")
        check_macro(macros, "ngrdcdaily", float(inv["n_daily_in_period"]), "{:.0f}")
        check_macro(macros, "ngrdcmatched", float(inv["n_matched"]), "{:.0f}")
        check_macro(macros, "ngrdcdischargepairs", float(inv["n_discharge_pairs"]), "{:.0f}")
        check_macro(macros, "ngrdcwlonly", float(inv["n_water_level_only"]), "{:.0f}")
    else:
        print("  SKIP inventory — run scripts/validate_grdc.py to write grdc_inventory.csv")
    table = PAPER / "tables" / "grdc_validation.csv"
    if not table.exists():
        print("  SKIP — run scripts/validate_grdc.py and copy its CSV into paper/tables/")
        return
    g = pd.read_csv(table)
    check_val("GRDC discharge pairs", "11", str(len(g)))
    check_val("median r", "1.000", f"{g['r'].median():.3f}")
    check_val("median NSE", "1.000", f"{g['nse'].median():.3f}")
    check_val("median PBIAS", "0.0%", f"{g['pbias'].median():.1f}%")
    identical = int(((g["r"].round(3) == 1.0) & (g["pbias"].round(1) == 0.0)).sum())
    check_val("pairs identical at reported precision", "10", str(identical))
    kon = g[g["grdc_station"].str.contains("KONSTANTIN", case=False, na=False)]
    check_val("Konstantinovo r", "0.996", f"{float(kon['r'].iloc[0]):.3f}")
    check_val("Konstantinovo PBIAS", "-0.6%", f"{float(kon['pbias'].iloc[0]):.1f}%")


def check_koppen_gates() -> None:
    """Gate the Sect. 2.3 Koppen shares against the committed per-gauge class CSV."""
    section("KOPPEN CLASSES (paper/tables/koppen_classes.csv)")
    table = PAPER / "tables" / "koppen_classes.csv"
    if not table.exists():
        print("  SKIP — koppen_classes.csv absent")
        return
    k = pd.read_csv(table, dtype=str)
    # The CSV covers the full release; the manuscript states shares over the Analysis set.
    k = k[paper_analysis_inclusion_mask(k["gauge_id"]).to_numpy()]
    n = len(k)
    check_val("Koppen catchments (Analysis set)", "3201", str(n))
    share = k["kg"].value_counts()
    dw = int(share[share.index.str.startswith("Dw")].sum())
    for label, expected, count in (
        ("Dfb", "37%", int(share.get("Dfb", 0))),
        ("Dfc", "32%", int(share.get("Dfc", 0))),
        ("Dw*", "21%", dw),
        ("Dfa", "5%", int(share.get("Dfa", 0))),
        ("Cfa", "2%", int(share.get("Cfa", 0))),
        ("Dsc", "2%", int(share.get("Dsc", 0))),
        ("BSk+BWk", "1%", int(share.get("BSk", 0)) + int(share.get("BWk", 0))),
    ):
        check_val(f"Koppen {label} share", expected, f"{100.0 * count / n:.0f}%")


def check_nesting_depth_macros(macros: dict[str, str], boundaries: gpd.GeoDataFrame) -> None:
    """Lock the Sect. 8.5 nesting-depth claims: containment chains over the release.

    Depth(g) = 1 + max depth over the strictly larger polygons containing g's gauge
    point (0 if none) — the same definition as scripts/detect_nesting.py, but computed
    from release artifacts alone.
    """
    section("NESTING DEPTH (boundaries.gpkg + attributes lat/lon)")
    pts_df = pd.read_csv(RELEASE / "camels_ru_attributes.csv", usecols=["gauge_id", "lat", "lon"])
    pts_df["gauge_id"] = pts_df["gauge_id"].astype(str)
    pts = gpd.GeoDataFrame(
        pts_df, geometry=gpd.points_from_xy(pts_df["lon"], pts_df["lat"]), crs=boundaries.crs
    )
    poly = boundaries[["gauge_id", "area_km2", "geometry"]].copy()
    poly["gauge_id"] = poly["gauge_id"].astype(str)
    areas = poly.set_index("gauge_id")["area_km2"]
    contain = gpd.sjoin(pts, poly.rename(columns={"gauge_id": "parent"}), predicate="within")
    contain = contain[contain["gauge_id"] != contain["parent"]]
    contain = contain[contain["area_km2"] > contain["gauge_id"].map(areas)]
    parents = contain.groupby("gauge_id")["parent"].apply(list).to_dict()

    def max_depth(members: pd.Index) -> int:
        depth = dict.fromkeys(members, 0)
        # Largest-first: every (strictly larger) parent is final before its children.
        for g in areas.loc[members].sort_values(ascending=False).index:
            ps = [p for p in parents.get(g, []) if p in depth]
            if ps:
                depth[g] = 1 + max(depth[p] for p in ps)
        return max(depth.values())

    all_ids = pd.Index(areas.index)
    analysis_ids = all_ids[paper_analysis_inclusion_mask(pd.Series(all_ids)).to_numpy()]
    check_macro(macros, "nnestmaxdepth", float(max_depth(all_ids)), "{:.0f}")
    check_macro(macros, "nnestmaxdepthanalysis", float(max_depth(analysis_ids)), "{:.0f}")


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
    # Base rate for the violation share (round-7 writing M5): grade-A share among the
    # upstream gauges of the violating pairs vs among the upstream gauges of ALL pairs.
    check_macro(
        macros, "pctnestedviolgradea", 100.0 * (df.loc[fail, "up"].map(grade) == "A").mean(), "{:.0f}"
    )
    check_macro(macros, "pctnestedupgradea", 100.0 * (df["up"].map(grade) == "A").mean(), "{:.0f}")
    check_macro(macros, "nnestedinformative", float(informative.sum()), "{:.0f}")
    check_macro(macros, "pctnestedinformativefail", float(100.0 * fail[informative].mean()), "{:.1f}")
    check_macro(macros, "pctnestedbigshare", float(100.0 * big.mean()), "{:.1f}")
    check_macro(macros, "pctnestedbigfail", float(100.0 * fail[big].mean()), "{:.1f}")
    check_macro(macros, "nnestedgauges", float(pd.concat([df["up"], df["down"]]).nunique()), "{:.0f}")
    check_macro(macros, "nestedyieldlow", float(100.0 * (yield_ratio < 0.5).mean()), "{:.1f}")
    check_macro(macros, "nestedyieldhigh", float(100.0 * (yield_ratio > 2).mean()), "{:.1f}")
    # Violations with no released screen flag on either gauge (Sect. 7.1 disclosure):
    # specific_discharge_anomaly, stage_discharge_screen == 1, is_anomalous, or
    # water_balance_screen. The worked example (2131) must remain caught.
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as dq:
        sda = pd.Series(
            dq["specific_discharge_anomaly"].values, index=[str(g) for g in dq["gauge_id"].values]
        )
    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as dw:
        sds = pd.Series(
            dw["stage_discharge_screen"].values, index=[str(g) for g in dw["gauge_id"].values]
        )
    sig = pd.read_csv(RELEASE / "camels_ru_signatures.csv", dtype={"gauge_id": str}).set_index(
        "gauge_id"
    )
    flagged_ids = set(sda.index[sda == 1]) | set(sds.index[sds == 1])
    flagged_ids |= set(sig.index[sig["is_anomalous"].astype(bool)])
    flagged_ids |= set(sig.index[sig["water_balance_screen"] == 1])
    viol = df[fail]
    unflagged = (~viol["up"].isin(flagged_ids) & ~viol["down"].isin(flagged_ids)).sum()
    check_macro(macros, "nnestedviolunflagged", float(unflagged), "{:.0f}")
    check_val(
        "worked example 2131 caught by a released screen",
        "yes",
        "yes" if "2131" in flagged_ids else "no",
    )
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
    # >= 80 as the Sect. 9 prose states it; Table 6's top band is (80, 100] but no
    # catchment sits at exactly 80, so both conventions give the same 155.
    check_macro(macros, "npermafrosteighty", float((df["prm_pc_use"] >= 80).sum()), "{:.0f}")

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
    check_macro(macros, "nstagenegative", float((river["rho_open_water"] < 0).sum()), "{:.0f}")
    check_macro(macros, "pctstageweak", 100.0 * (river["rho_open_water"] < 0.5).mean(), "{:.1f}")


def check_release_range_gates(macros: dict[str, str]) -> None:
    """Gate the Table 3 value-range macros and the release coverage statistics.

    Rounding mirrors the printed precision: volumes to the nearest 1000 (m3/s) or
    100 (mm/d stage), precipitation and temperatures to integers, the pet minimum
    to 2 d.p., the stage minimum to 1 d.p.
    """
    section("RELEASE VALUE RANGES AND COVERAGE (Table 3 + Sect. 2.3/4.2/4.4)")

    def norm(name: str) -> str:
        return macros.get(name, "").replace("\\xspace", "").replace("\\,", "").replace("$", "").strip()

    def gate_range(name: str, lo: str, hi: str) -> None:
        check_val(name, norm(name), f"{lo} to {hi}")

    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        q3 = ds["discharge_m3s"]
        qm = ds["discharge_mm"]
        gate_range("rngqvol", "0", f"{round(float(q3.max()) / 1000) * 1000:.0f}")
        # Ceil, not round: the declared maximum must not clip real data (66,732.20 -> 66,733).
        gate_range("rngqmm", "0", f"{np.ceil(float(qm.max())):.0f}")
        check_macro(macros, "nallmissingdischarge", float(q3.isnull().all("time").sum()), "{:.0f}")

    with xr.open_dataset(RELEASE / "camels_ru_forcing.nc") as fx:
        for name, var in (
            ("rngpmswep", "precip_mswep"),
            ("rngpera", "precip_era5"),
            ("rngpgpcp", "precip_gpcp"),
        ):
            gate_range(name, f"{float(fx[var].min()):.0f}", f"{float(fx[var].max()):.0f}")
        for name, var in (("rngtmean", "temp_mean"), ("rngtmin", "temp_min"), ("rngtmax", "temp_max")):
            gate_range(name, f"{float(fx[var].min()):.0f}", f"{float(fx[var].max()):.0f}")
        pet = fx["pet"]
        gate_range("rngpet", f"{float(pet.min()):.2f}", f"{float(pet.max()):.0f}")
        check_macro(macros, "petminnum", float(pet.min()), "{:.2f}")
        neg_pct = 100.0 * float((pet < 0).sum()) / int(pet.notnull().sum())
        check_macro(macros, "petnegpct", neg_pct, "{:.1f}")
        gpcp_miss = fx["precip_gpcp"].isnull()
        check_macro(macros, "ngpcpgapdays", float((gpcp_miss.sum("gauge_id") > 0).sum()), "{:.0f}")
        check_macro(macros, "ngpcpgapgauges", float(gpcp_miss.any("time").sum()), "{:.0f}")
        coverage = 100.0 * (1.0 - float(gpcp_miss.sum()) / gpcp_miss.size)
        check_macro(macros, "gpcpcoverage", coverage, "{:.1f}")
        # Climate percentiles of Sect. 2.3 over the Analysis set (in-text literals).
        ids = fx["gauge_id"].astype(str).values
        in_analysis = ~pd.Series(ids).map(is_paper_analysis_excluded_gauge_id).to_numpy()
        p_ann = (fx["precip_mswep"].sum("time", skipna=True) / 16.0).values[in_analysis]
        t_ann = fx["temp_mean"].mean("time", skipna=True).values[in_analysis]
        check_val(
            "P annual 5th pct (round 10)", "320", f"{round(np.nanpercentile(p_ann, 5) / 10) * 10:.0f}"
        )
        check_val(
            "P annual 95th pct (round 10)", "960", f"{round(np.nanpercentile(p_ann, 95) / 10) * 10:.0f}"
        )
        check_val("T annual 5th pct", "-8.7", f"{np.nanpercentile(t_ann, 5):.1f}")
        check_val("T annual 95th pct", "+9.7", f"{np.nanpercentile(t_ann, 95):+.1f}")
        attrs = pd.read_csv(RELEASE / "camels_ru_attributes.csv", usecols=["gauge_id", "snw_pc_uyr"])
        snw = attrs.set_index(attrs["gauge_id"].astype(str))["snw_pc_uyr"].reindex(
            pd.Index(ids)[in_analysis]
        )
        snw5, snw95 = np.nanpercentile(snw, 5), np.nanpercentile(snw, 95)
        check_val("snow 5th pct below 15%", "True", str(bool(snw5 < 15)))
        check_val("snow 95th pct above 60%", "True", str(bool(snw95 > 60)))

    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as wl:
        cm = wl["water_level_cm"]
        mbs = wl["water_level_mbs"]
        zero = wl["gauge_zero_m"]
        gate_range("rngwlcm", f"{float(cm.min()):.1f}", f"{round(float(cm.max()) / 100) * 100:.0f}")
        gate_range("rngwlmbs", f"{float(mbs.min()):.0f}", f"{float(mbs.max()):.0f}")
        gate_range("rngzero", f"{float(zero.min()):.0f}", f"{float(zero.max()):.0f}")

    boundaries = gpd.read_file(RELEASE / "camels_ru_boundaries.gpkg")
    err = boundaries["area_diff_perc"].dropna()
    check_macro(macros, "ntrimkept", float((err.abs() <= 100).sum()), "{:.0f}")
    check_macro(macros, "ntrimexcluded", float((err.abs() > 100).sum()), "{:.0f}")
    check_macro(macros, "nsubfivecatchments", float((boundaries["area_km2"] < 5).sum()), "{:.0f}")
    # 0.1-degree cell areas at the catchment-centroid latitudes (Sect. 4.2).
    with np.errstate(invalid="ignore"):
        lat = boundaries.geometry.centroid.y
    cell = 0.1 * 111.32 * (0.1 * 111.32 * np.cos(np.deg2rad(lat)))
    check_macro(macros, "cellareasouth", float(cell[lat.idxmin()]), "{:.0f}")
    check_macro(macros, "cellareanorth", float(cell[lat.idxmax()]), "{:.0f}")
    check_macro(macros, "cellareamedian", float(cell.median()), "{:.0f}")


_GRADE_ORDER = ["A", "B", "C", "D", "F"]


def _overall_grade(grades: list[str]) -> str:
    """Mirror quality_grader.get_gauge_summary: strict A, mode of non-F, coverage caps."""
    usable_g = [g for g in grades if g != "F"]
    if not usable_g:
        return "F"
    if all(g == "A" for g in grades):
        return "A"
    freq: dict[str, int] = {}
    for g in usable_g:
        freq[g] = freq.get(g, 0) + 1
    og = max(freq, key=lambda g: (freq[g], _GRADE_ORDER.index(g)))
    if og == "A":
        og = "B"
    usable_fraction = sum(g in ("A", "B", "C") for g in grades) / len(grades)
    if usable_fraction < 0.5:
        og = max(og, "D", key=_GRADE_ORDER.index)
    elif usable_fraction < 0.7:
        og = max(og, "C", key=_GRADE_ORDER.index)
    return og


def _nss_flag_matrix() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Mirror detect_flat_years on the released discharge: (nss, comp, ids, hy_years)."""
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        q = ds["discharge_mm"].transpose("gauge_id", "time").values
        ids = ds["gauge_id"].astype(str).values
        times = pd.DatetimeIndex(ds["time"].values)

    hy = times.year + (times.month >= 10).astype(int)
    hy_years = np.arange(hy.min(), hy.max() + 1)
    obs = ~np.isnan(q)
    n_g = q.shape[0]
    peak = np.full((n_g, len(hy_years)), np.nan)
    comp = np.zeros((n_g, len(hy_years)))
    for j, y in enumerate(hy_years):
        m = hy == y
        qy = np.where(obs[:, m], q[:, m], np.nan)
        cnt = obs[:, m].sum(axis=1)
        comp[:, j] = cnt / int(m.sum())
        with np.errstate(invalid="ignore", divide="ignore"):
            mean_y = np.nanmean(qy, axis=1)
            r = np.nanmax(qy, axis=1, initial=np.nan) / mean_y
        # detect_seasonal_signal returns NaN below 30 observed days or at mean <= 0
        r[(cnt < 30) | ~(mean_y > 0)] = np.nan
        peak[:, j] = r

    valid_ratio = ~np.isnan(peak)
    p75 = np.full(n_g, np.nan)
    mx = np.full(n_g, np.nan)
    for i in range(n_g):
        if valid_ratio[i].sum() >= 3:
            vals = peak[i, valid_ratio[i]]
            p75[i] = np.percentile(vals, 75)
            mx[i] = vals.max()
    seasonal = (p75 >= 10.0) | (mx >= 20.0)
    nss = valid_ratio & seasonal[:, None] & (peak < (0.3 * p75)[:, None])
    return nss, comp, ids, hy_years


def check_nss_completeness_macros(macros: dict[str, str]) -> None:
    """Recompute the no_seasonal_signal completeness-bar disclosure (Sect. 4.1.1).

    Mirrors src/quality/climatology.py::detect_flat_years on the released
    discharge alone (gated below: the mirror must fire on exactly the assessed
    gauge-years of the released flag census) and quantifies an 85 % completeness
    bar: F years the flag alone explains at completeness 0.5-0.85, and the
    upper bound on gauges whose overall grade would change.
    """
    section("NO_SEASONAL_SIGNAL COMPLETENESS BAR (released discharge + year grades)")
    nss, comp, ids, hy_years = _nss_flag_matrix()

    yg = pd.read_csv(RELEASE / "camels_ru_year_grades.csv", dtype={"gauge_id": str}).set_index(
        "gauge_id"
    )
    year_cols = [c for c in yg.columns if c.isdigit()]
    id_pos = {g: i for i, g in enumerate(ids)}
    ypos = {int(y): j for j, y in enumerate(hy_years)}

    sub = yg.reindex(ids)[year_cols]
    assessed = np.zeros(nss.shape, dtype=bool)
    assessed[:, [ypos[int(c)] for c in year_cols]] = (sub.notna() & (sub != "")).to_numpy()
    census = pd.read_csv(PAPER / "tables" / "flag_frequencies.csv")
    n_census = int(census.loc[census["flag"] == "no_seasonal_signal", "n_years"].iloc[0])
    check_val(
        "NSS mirror fires on assessed years (vs flag census)",
        str(int((nss & assessed).sum())),
        str(n_census),
    )

    n_f = 0
    suppressed: dict[str, list[int]] = {}
    for gid, row in yg.iterrows():
        i = id_pos.get(gid)
        if i is None:
            continue
        for c in year_cols:
            g = row[c]
            if not isinstance(g, str) or g != "F":
                continue
            n_f += 1
            j = ypos[int(c)]
            if nss[i, j] and 0.5 <= comp[i, j] < 0.85:
                suppressed.setdefault(gid, []).append(int(c))
    n_suppressed = sum(len(v) for v in suppressed.values())
    check_macro(macros, "nfyeartotal", float(n_f), "{:.0f}")
    check_macro(macros, "nnssbarsuppressed", float(n_suppressed), "{:.0f}")

    # Exact gauge-grade changes: re-run the full year rule on each suppressed year's
    # remaining flags (release evidence file), then re-aggregate. The earlier
    # become-C/D heuristic ignored the other flags of a suppressed year and missed
    # a tie-rule mode shift, undercounting by one (round-8 consistency M1).
    yfl = pd.read_csv(RELEASE / "camels_ru_year_flags.csv", dtype={"gauge_id": str})
    yfl["flag_codes"] = yfl["flag_codes"].fillna("")
    base_g: dict[str, list[str]] = {}
    var_g: dict[str, list[str]] = {}
    for r in yfl.itertuples(index=False):
        flags = [f for f in r.flag_codes.split(",") if f]
        gv = r.grade
        if r.completeness < 0.85 and "no_seasonal_signal" in flags:
            gv = _year_grade_from_evidence(
                [f for f in flags if f != "no_seasonal_signal"], r.completeness
            )
        base_g.setdefault(r.gauge_id, []).append(r.grade)
        var_g.setdefault(r.gauge_id, []).append(gv)
    n_changed = sum(1 for g in base_g if _overall_grade(base_g[g]) != _overall_grade(var_g[g]))
    check_macro(macros, "nnssbargauges", float(n_changed), "{:.0f}")


def check_year_flags_gates(year_grades: pd.DataFrame) -> None:
    """Gate camels_ru_year_flags.csv: census parity and full grade parity."""
    section("YEAR FLAGS (release camels_ru_year_flags.csv vs census + year grades)")
    path = RELEASE / "camels_ru_year_flags.csv"
    if not path.exists():
        print("  SKIP — run scripts/create_year_flags.py")
        return
    yf = pd.read_csv(path, dtype={"gauge_id": str}).fillna({"flag_codes": ""})
    census = pd.read_csv(PAPER / "tables" / "flag_frequencies.csv")
    check_val(
        "year_flags rows == assessed years", str(len(yf)), str(int(census["n_assessed_years"].iloc[0]))
    )
    counts = yf["flag_codes"].str.split(",").explode()
    counts = counts[counts != ""].value_counts()
    bad = [
        f
        for f, n in zip(census["flag"], census["n_years"], strict=True)
        if int(counts.get(f, 0)) != int(n)
    ]
    # Both directions: a flag firing in year_flags but absent from the census is drift too
    bad += sorted(set(counts.index) - set(census["flag"]))
    check_val("per-flag counts == flag census", "0 mismatches", f"{len(bad)} mismatches")
    yg = year_grades.copy()
    yg["gauge_id"] = yg["gauge_id"].astype(str)
    long = yg.melt(id_vars="gauge_id", var_name="hydro_year", value_name="released")
    long = long[long["hydro_year"].str.isdigit()].dropna(subset=["released"])
    long["hydro_year"] = long["hydro_year"].astype(int)
    merged = yf.merge(long, on=["gauge_id", "hydro_year"], how="outer", indicator=True)
    mism = (merged["_merge"] != "both") | (merged["grade"] != merged["released"])
    check_val("grade parity with year_grades.csv", "0 differences", f"{int(mism.sum())} differences")


def check_agg_missing_temperature_gate(huge: pd.Series, boundaries: gpd.GeoDataFrame) -> None:
    """Gate the Table 4 caption's causal claim (round-7 consistency m5).

    The temperature-less sampled catchment is named in the CSV and its released
    boundary lies past 170 E.
    """
    raw_missing = huge.get("t_missing_gauge_ids")
    miss = (
        []
        if pd.isna(raw_missing)
        else [s.split(".")[0] for s in str(raw_missing).split(";") if s and s != "nan"]
    )
    check_val(
        "5000+ band t_n_valid + missing ids",
        str(int(huge["n_sample"])),
        str(int(huge["t_n_valid"]) + len(miss)),
    )
    if miss:
        bnd = boundaries.loc[boundaries["gauge_id"].astype(str).isin(miss)]
        crosses = len(bnd) == len(miss) and bool((bnd.geometry.bounds["maxx"] > 170.0).all())
        check_val("missing-T catchment(s) past 170E", "True", str(crosses))


def check_water_level_reversion_gates(macros: dict[str, str]) -> None:
    """Lock the Sect. 4.1.3 reversion macros to the committed per-gauge provenance CSV."""
    section("WATER-LEVEL REVERSION (paper/tables/water_level_reversion.csv + release flags)")
    table = PAPER / "tables" / "water_level_reversion.csv"
    if not table.exists():
        print("  SKIP — run scripts/derive_water_level_reversion.py (needs the data drive)")
        return
    rev = pd.read_csv(table, dtype={"gauge_id": str})
    n_rev = int(rev["n_reverted"].sum())
    check_macro(macros, "nwlreverted", float(n_rev), "{:.0f}")
    check_macro(macros, "nwlrevertedgauges", float(len(rev)), "{:.0f}")
    check_macro(macros, "nwlnegatives", float(rev["n_negative"].sum()), "{:.0f}")
    check_val(
        "per-gauge origin split sums to n_reverted",
        "True",
        str(bool((rev["n_from_gap_fill"] + rev["n_from_zero_replacement"] == rev["n_reverted"]).all())),
    )
    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as wds:
        flag = wds["quality_flag"].values
        rel_ids = {str(g) for g in wds["gauge_id"].values}
    n_altered = n_rev + int((flag == 1).sum()) + int((flag == 2).sum())
    check_macro(macros, "nwlaltered", float(n_altered), "{:,.0f}")
    check_macro(macros, "nwlrevertedpct", 100.0 * n_rev / n_altered, "{:.1f}")
    check_val(
        "reversion gauges exist in the release", "True", str(bool(rev["gauge_id"].isin(rel_ids).all()))
    )


def check_peak_winter_ratio_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 4.1.1 annual-max / winter-mean ratio behind the 8-sigma threshold.

    Per gauge-hydro-year (2009-2023): max daily discharge over the year divided by the
    mean Jan-Mar discharge of the same year, over years with >= 70% daily coverage,
    >= 30 observed Jan-Mar days, and a positive winter mean; pooled over gauge-years.
    """
    section("PEAK/WINTER RATIO (camels_ru_discharge.nc)")
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        q = ds["discharge_m3s"].transpose("gauge_id", "time").values
        t = pd.DatetimeIndex(ds["time"].values)
    hy = (t.year + (t.month >= 10).astype(int)).to_numpy()
    winter = np.isin(t.month, (1, 2, 3))
    obs = np.isfinite(q)
    ratios = []
    for y in range(2009, 2024):
        my = hy == y
        mw = my & winter
        qy = np.where(obs[:, my], q[:, my], np.nan)
        cov = obs[:, my].sum(axis=1) / int(my.sum())
        n_w = obs[:, mw].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            amax = np.nanmax(np.where(np.isnan(qy), -np.inf, qy), axis=1)
            wmean = np.nanmean(np.where(obs[:, mw], q[:, mw], np.nan), axis=1)
            r = amax / wmean
        valid = (cov >= 0.70) & (n_w >= 30) & (wmean > 0) & np.isfinite(r)
        ratios.append(r[valid])
    pooled = np.concatenate(ratios)
    check_macro(macros, "nqpeakwinteryears", float(len(pooled)), "{:,.0f}")
    check_macro(macros, "qpeakwintermed", float(np.median(pooled)), "{:.0f}")
    check_macro(macros, "qpeakwinterqone", float(np.percentile(pooled, 25)), "{:.0f}")
    check_macro(macros, "qpeakwinterqthree", float(np.percentile(pooled, 75)), "{:.0f}")


# Mirror of src/quality severity classes for the flags that fire in the release
# (src/quality/quality_flags.py); used by check_pq_family_gates below.
_SEVERITY_MIRROR = {
    "low_clim_correlation": "minor",
    "very_low_clim_correlation": "major",
    "high_clim_nrmse": "minor",
    "low_amplitude": "minor",
    "high_amplitude": "minor",
    "no_seasonal_signal": "critical",
    "no_precip_response": "minor",
    "very_low_pq_correlation": "minor",
    "low_pq_correlation": "minor",
    "low_flashiness": "minor",
    "constant_value": "major",
    "implausible_spike": "minor",
    "low_completeness": "major",
    "very_low_completeness": "critical",
    "negative_values": "critical",
    "zero_flow_dominant": "minor",
}
_PQ_FAMILY = {"very_low_pq_correlation", "low_pq_correlation"}
# The six rows of Table 4's climatology group, incl. critical no_seasonal_signal.
_CLIM_FAMILY = {
    "low_clim_correlation",
    "very_low_clim_correlation",
    "high_clim_nrmse",
    "low_amplitude",
    "high_amplitude",
    "no_seasonal_signal",
}
_GRADE_ORDER = "ABCDF"


def _year_grade_from_evidence(flags: list[str], completeness: float) -> str:
    """Table 5 year-grade rule, applied top-down."""
    n_crit = sum(1 for f in flags if _SEVERITY_MIRROR[f] == "critical")
    n_major = sum(1 for f in flags if _SEVERITY_MIRROR[f] == "major")
    n_minor = sum(1 for f in flags if _SEVERITY_MIRROR[f] == "minor")
    if n_crit:
        return "F"
    if n_major >= 2 or completeness < 0.70:
        return "D"
    if n_major == 1 or n_minor >= 5 or completeness < 0.85:
        return "C"
    if n_minor >= 3 or completeness < 0.95:
        return "B"
    return "A"


def _overall_grade(grades: list[str]) -> str:
    """Sect. 4.1.2 gauge-aggregation rule (strict A, mode of non-F, ties worse, caps)."""
    if all(g == "A" for g in grades):
        return "A"
    if all(g == "F" for g in grades):
        return "F"
    nonf = [g for g in grades if g != "F"]
    counts = {g: nonf.count(g) for g in set(nonf)}
    top = max(counts.values())
    mode = max([g for g, n in counts.items() if n == top], key=_GRADE_ORDER.index)
    if mode == "A":
        mode = "B"
    share_abc = sum(1 for g in grades if g in "ABC") / len(grades)
    cap = "D" if share_abc < 0.5 else ("C" if share_abc < 0.7 else None)
    if cap and _GRADE_ORDER.index(mode) < _GRADE_ORDER.index(cap):
        mode = cap
    return mode


def check_fdc_sawicz_macros(macros: dict[str, str]) -> None:
    """Lock the Sect. 5.2 fdc_slope vs Sawicz (2011) comparability numbers.

    The released fdc_slope formula IS Sawicz Eq. 3 (exceedance percentiles in
    percent); the only convention difference is aggregation (mean of annual
    slopes vs one whole-record slope). Recompute the whole-record slope from
    discharge_mm for every non-anomalous gauge and gate the Spearman rank
    agreement, the median relative difference, and full sign agreement. The
    whole-record slope pools every released day (2008-2023), not only the
    complete hydro-years the annual signature uses (windowed variant: median
    -3.63 %, rho 0.9680 -- same printed values).
    """
    section("FDC SLOPE VS SAWICZ WHOLE-RECORD (release discharge + signatures)")
    sig = pd.read_csv(RELEASE / "camels_ru_signatures.csv", dtype={"gauge_id": str})
    sub = sig[(~sig["is_anomalous"]) & sig["fdc_slope"].notna()]
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        pos = {str(g): i for i, g in enumerate(ds["gauge_id"].values)}
        q = ds["discharge_mm"].values
    released, sawicz = [], []
    for g, rel_slope in zip(sub["gauge_id"], sub["fdc_slope"], strict=True):
        x = q[pos[g]]
        x = x[np.isfinite(x)]
        q1 = np.percentile(x, 67)  # exceeded 33 % of the time
        q2 = np.percentile(x, 34)  # exceeded 66 % of the time
        if q1 <= 0 or q2 <= 0:
            continue
        released.append(rel_slope)
        sawicz.append((np.log(q1) - np.log(q2)) / 33 * 100)
    rel = np.array(released)
    saw = np.array(sawicz)
    check_val("gauges compared (nonpositive percentiles skipped)", str(len(rel)), str(len(sub)))
    check_macro(macros, "nsigngauges", float(len(rel)), "{:.0f}")
    check_val("sign agreement", "100.0%", f"{(np.sign(rel) == np.sign(saw)).mean():.1%}")
    rho = float(spearmanr(rel, saw)[0])
    check_macro(macros, "fdcsawiczrho", rho, "{:.2f}")
    med = float(np.median((rel - saw) / saw))
    check_macro(macros, "fdcsawiczmeddiff", abs(med) * 100, "{:.0f}")
    direction = "below" if med < 0 else "above"
    check_val("median difference direction (Sect. 5.2 says below)", "below", direction)


def check_pq_family_gates(macros: dict[str, str]) -> None:
    """Lock the Sect. 4.1.2 flag-family counterfactual macros via a full regrade mirror.

    Recomputes every year grade from camels_ru_year_flags.csv (completeness + flag
    codes), requires exact parity with the shipped grades as a self-check, then
    recomputes the gauge-grade distribution with the two P-Q correlation flags, the
    six-flag climatology group, and implausible_spike disabled in turn.
    """
    section("FLAG-FAMILY COUNTERFACTUALS (camels_ru_year_flags.csv regrade mirror)")
    path = RELEASE / "camels_ru_year_flags.csv"
    if not path.exists():
        print("  SKIP — run scripts/create_year_flags.py")
        return
    yf = pd.read_csv(path, dtype={"gauge_id": str}).fillna({"flag_codes": ""})
    mismatch = 0
    n_pq_years = 0
    variants = {"pq": _PQ_FAMILY, "clim": _CLIM_FAMILY, "spike": {"implausible_spike"}}
    by_gauge: dict[str, dict[str, list[str]]] = {k: {} for k in ("base", *variants)}
    for row in yf.itertuples(index=False):
        flags = row.flag_codes.split(",") if row.flag_codes else []
        comp = float(row.completeness)
        if any(f in _PQ_FAMILY for f in flags):
            n_pq_years += 1
        base = _year_grade_from_evidence(flags, comp)
        if base != row.grade:
            mismatch += 1
        by_gauge["base"].setdefault(row.gauge_id, []).append(base)
        for key, fam in variants.items():
            by_gauge[key].setdefault(row.gauge_id, []).append(
                _year_grade_from_evidence([f for f in flags if f not in fam], comp)
            )
    check_val("regrade mirror parity with shipped year grades", "0 mismatches", f"{mismatch} mismatches")
    dist = {
        k: pd.Series([_overall_grade(v) for v in g.values()]).value_counts() for k, g in by_gauge.items()
    }
    check_val(
        "baseline gauge grade A",
        macros.get("ngradeA", "").replace("\\xspace", ""),
        str(int(dist["base"].get("A", 0))),
    )
    check_macro(macros, "pqfamilypct", 100.0 * n_pq_years / len(yf), "{:.1f}")
    check_macro(macros, "ngradeanopq", float(dist["pq"].get("A", 0)), "{:.0f}")
    check_macro(macros, "ngradebnopq", float(dist["pq"].get("B", 0)), "{:.0f}")
    check_macro(macros, "ngradeanoclim", float(dist["clim"].get("A", 0)), "{:.0f}")
    check_macro(macros, "ngradeanospike", float(dist["spike"].get("A", 0)), "{:.0f}")
    # The Sect. 4.1.2 sentence claims the climatology counterfactual also moves
    # grades C-F, and that its dA is "nearly three times" the P-Q pair's.
    base_a = int(dist["base"].get("A", 0))
    moved_cf = any(int(dist["clim"].get(g, 0)) != int(dist["base"].get(g, 0)) for g in "CDF")
    check_val("clim counterfactual moves grades C-F", "yes", "yes" if moved_cf else "no")
    ratio = (int(dist["clim"].get("A", 0)) - base_a) / max(1, int(dist["pq"].get("A", 0)) - base_a)
    check_val(
        "clim/pq dA ratio supports 'nearly three times'",
        "yes",
        "yes" if 2.5 <= ratio < 3.05 else "no",
    )


def check_gradea_signature_bias(macros: dict[str, str]) -> None:
    """Lock the usage-notes grade-A signature-space bias medians (Sect. 6.4).

    Joins the non-anomalous signature gauges to the released overall grades and
    recomputes the strict-grade-A vs graded-below-A medians of five signatures,
    plus the Mann-Whitney significance floor the sentence claims (p < 1e-8).
    """
    section("GRADE-A SIGNATURE-SPACE BIAS (signatures.csv + gauge_summary.csv)")
    sig = pd.read_csv(RELEASE / "camels_ru_signatures.csv", dtype={"gauge_id": str})
    gs = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv", dtype={"gauge_id": str})
    m = sig[~sig["is_anomalous"]].merge(gs[["gauge_id", "overall_grade"]], on="gauge_id")
    graded = m[m["overall_grade"].isin(list("ABCDF"))]
    a = graded[graded["overall_grade"] == "A"]
    na = graded[graded["overall_grade"] != "A"]
    check_macro(macros, "nsigngradea", float(len(a)), "{:.0f}")
    check_macro(macros, "nsigngradednona", float(len(na)), "{:.0f}")
    check_val(
        "grade split exhausts nsigngauges",
        macros.get("nsigngauges", "").replace("\\xspace", ""),
        str(len(a) + len(na)),
    )
    specs = [
        ("runoff_ratio", "sgamedrr", "sgnamedrr", "{:.2f}"),
        ("q_mean", "sgamedqmean", "sgnamedqmean", "{:.2f}"),
        ("winter_flow_ratio", "sgamedwfr", "sgnamedwfr", "{:.2f}"),
        ("half_flow_date", "sgamedhfd", "sgnamedhfd", "{:.0f}"),
        ("area_km2", "sgamedarea", "sgnamedarea", "{:.0f}"),
    ]
    worst_p = 0.0
    for col, ma, mn, fmt in specs:
        xa, xn = a[col].dropna(), na[col].dropna()
        check_macro(macros, ma, float(xa.median()), fmt)
        check_macro(macros, mn, float(xn.median()), fmt)
        worst_p = max(worst_p, float(mannwhitneyu(xa, xn).pvalue))
    check_val("all five contrasts Mann-Whitney p < 1e-8", "yes", "yes" if worst_p < 1e-8 else "no")


def check_ice_window_gates(macros: dict[str, str]) -> None:
    """Gate the ice-window sensitivity macros against the committed provenance CSV."""
    section("ICE-WINDOW SENSITIVITY (paper/tables/ice_window_sensitivity.csv)")
    table = PAPER / "tables" / "ice_window_sensitivity.csv"
    if not table.exists():
        print("  SKIP — run scripts/ice_window_sensitivity.py")
        return
    row = pd.read_csv(table).iloc[0]
    check_macro(macros, "nconstflagged", float(row["n_const_flagged_fixed"]), "{:.0f}")
    check_macro(macros, "nconstwinexempt", float(row["n_const_exempt_derived"]), "{:.0f}")
    check_macro(macros, "nconstwinnew", float(row["n_const_new_derived"]), "{:.0f}")
    check_val(
        "stage screen weak May-Oct (CSV vs nstageweak)",
        macros.get("nstageweak", "").replace("\\xspace", ""),
        str(int(row["n_stage_weak_may_oct"])),
    )
    check_macro(macros, "nstageweakjunsep", float(row["n_stage_weak_jun_sep"]), "{:.0f}")


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
    check_macro(macros, "medianerror", float(aep.median()), "{:.1f}")
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
    tiny = agg_table.loc["5-150"]
    check_macro(macros, "aggpmedtiny", float(tiny["p_median_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggpninetytiny", float(tiny["p_p90_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggtmedtiny", float(tiny["t_median_abs_degc"]), "{:.2f}")
    check_macro(macros, "aggtninetytiny", float(tiny["t_p90_abs_degc"]), "{:.2f}")
    mid = agg_table.loc["500-1000"]
    check_macro(macros, "aggpmedmid", float(mid["p_median_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggpninetymid", float(mid["p_p90_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggtmedmid", float(mid["t_median_abs_degc"]), "{:.2f}")
    check_macro(macros, "aggtninetymid", float(mid["t_p90_abs_degc"]), "{:.2f}")
    large = agg_table.loc["1000-5000"]
    check_macro(macros, "aggpmedlarge", float(large["p_median_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggpninetylarge", float(large["p_p90_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggtmedlarge", float(large["t_median_abs_degc"]), "{:.2f}")
    check_macro(macros, "aggtninetylarge", float(large["t_p90_abs_degc"]), "{:.2f}")
    huge = agg_table.loc["5000+"]
    check_macro(macros, "aggpmedhuge", float(huge["p_median_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggpninetyhuge", float(huge["p_p90_abs_rel_pct"]), "{:.1f}")
    check_macro(macros, "aggpsignedhuge", float(huge["p_median_rel_pct"]), "{:+.2f}")
    check_macro(macros, "aggtmedhuge", float(huge["t_median_abs_degc"]), "{:.2f}")
    check_macro(macros, "aggtninetyhuge", float(huge["t_p90_abs_degc"]), "{:.2f}")
    check_macro(macros, "aggtnvalidhuge", float(huge["t_n_valid"]), "{:.0f}")
    check_agg_missing_temperature_gate(huge, boundaries)

    corr_table = pd.read_csv(PAPER / "tables" / "precip_inter_dataset_corr.csv")
    expected_corr = {
        "ERA5-Land vs MSWEP": (3201, 0.915, 0.265),
        "ERA5-Land vs GPCP": (3201, 0.664, 0.126),
        "MSWEP vs GPCP": (3201, 0.725, -0.138),
    }
    # The Sect. 7.5 macros quote three decimals (2-dec roundings sat on knife-edges).
    corr_macro = {
        "ERA5-Land vs MSWEP": "eramsweprcorr",
        "ERA5-Land vs GPCP": "eragpcpcorr",
        "MSWEP vs GPCP": "mswepgpcpcorr",
    }
    for _, row in corr_table.iterrows():
        comparison = str(row["Comparison"])
        exp_n, exp_r, exp_bias = expected_corr[comparison]
        check_macro(macros, corr_macro[comparison], float(row["Mean r"]), "{:.3f}")
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
    check_nesting_depth_macros(macros, boundaries)
    check_grdc_gates(macros)
    check_koppen_gates()
    check_release_range_gates(macros)
    check_nss_completeness_macros(macros)
    check_ice_window_gates(macros)
    check_year_flags_gates(year_grades)
    check_precip_caption_macros(macros)
    check_coldregion_macros(macros)
    check_spike_threshold_macros(macros)
    check_stage_screen_encoding_macros(macros)
    check_water_balance_screen_macros(macros)
    check_grade_regime_macros(macros)
    check_plausibility_macros(macros)
    check_stage_discharge_macros(macros)
    check_discharge_fill_macros(macros)
    check_water_level_reversion_gates(macros)
    check_peak_winter_ratio_macros(macros)
    check_fdc_sawicz_macros(macros)
    check_gradea_signature_bias(macros)
    check_pq_family_gates(macros)

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
