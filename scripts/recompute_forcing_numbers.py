#!/usr/bin/env python3
"""Recompute the manuscript's forcing-uncertainty (Section 5) numbers.

The ERA5-Land precipitation used in the original manuscript analysis was a
*stale* copy truncated at 2018-02; this script recomputes every Section 5
forcing number from the per-gauge daily CSVs, with a command-line switch
(``--era5 stale|full``) to select the ERA5-Land precipitation source.  Run
twice (``--era5 stale`` then ``--era5 full``) to validate the reimplementation
against the published numbers and then produce the corrected values.

It reproduces the exact definitions used by ``notebooks/03_ForcingsFinal.py``
(precip table, basin-averaged bias, per-catchment annual bias, Q/P table,
closure, seasonal Q/P) and ``scripts/hess_quality_audit.py`` (AET>PET adequacy
fraction).  MSWEP, GPCP, GLEAM and discharge are unaffected by the ERA5 swap
and should reproduce identically under both modes.

Usage:
    pixi run python scripts/recompute_forcing_numbers.py --era5 full
    pixi run python scripts/recompute_forcing_numbers.py --era5 stale
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.paper_analysis_scope import (  # noqa: E402
    is_paper_analysis_excluded_gauge_id,
    paper_analysis_inclusion_mask,
)

# ── Periods (from notebooks/03_ForcingsFinal.py) ──────────────────────────────
PERIOD_START = "2008-01-01"
PERIOD_END_ERA5 = "2023-12-31"
# GPCP v3.3 parsed data has full real coverage to 2023-12-31 (the old 2021-09-30 cap
# was a stale assumption); unify all three products to a single 2008-2023 window.
PERIOD_END_GPCP = "2023-12-31"
COMMON_END = "2023-12-31"

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA = ROOT / "data"
PARSED_METEO = DATA / "CAMELS_RU" / "parsed_meteo"
ERA5_STALE_DIR = PARSED_METEO / "era5_land"
ERA5_FULL_DIR = DATA / "Russia" / "MeteoData" / "CamelsRU" / "era5_land"
MSWEP_DIR = PARSED_METEO / "mswep"
GPCP_DIR = PARSED_METEO / "gpcp"
GLEAM_DIR = PARSED_METEO / "gleam"
GEOM_GAUGES = DATA / "CAMELS_RU" / "geometry" / "camels_gauges.gpkg"

RELEASE = ROOT / "release" / "CAMELS_RU_v1.0"
DISCHARGE_NC = RELEASE / "camels_ru_discharge.nc"
BOUNDARIES = RELEASE / "camels_ru_boundaries.gpkg"

# ── Per-product precipitation column names ────────────────────────────────────
PRECIP_COL = {"era5": "prcp", "mswep": "precipitation", "gpcp": "precip"}
PRECIP_END = {"era5": PERIOD_END_ERA5, "mswep": PERIOD_END_ERA5, "gpcp": PERIOD_END_GPCP}
GLEAM_AET_COL = "actual_evaporation"
GLEAM_PET_COL = "potential_evaporation"

MONTH_TO_SEASON = {
    12: "DJF",
    1: "DJF",
    2: "DJF",
    3: "MAM",
    4: "MAM",
    5: "MAM",
    6: "JJA",
    7: "JJA",
    8: "JJA",
    9: "SON",
    10: "SON",
    11: "SON",
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def load_csv_series(path: Path, value_col: str, date_col: str = "date") -> pd.Series | None:
    """Load a single-column daily time series from CSV, or None on failure.

    Args:
        path: CSV path indexed by ``date_col``.
        value_col: Column to extract.
        date_col: Date index column name.

    Returns:
        The value column as a ``pd.Series`` indexed by date, or ``None`` if the
        file is missing, unreadable, or lacks ``value_col``.
    """
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col=date_col, parse_dates=True)
    except Exception:  # noqa: BLE001
        return None
    if value_col not in df.columns:
        return None
    return pd.Series(df[value_col])


def annual_mean_precip(series: pd.Series, end_date: str) -> float:
    """Mean annual precipitation total (mm/yr) over the analysis period.

    Reproduces ``notebooks/03_ForcingsFinal.py``: slice to
    ``PERIOD_START:end_date``, require >= 365 daily records, resample to
    calendar-year sums, then average the annual sums.

    Args:
        series: Daily precipitation series (mm/day) indexed by date.
        end_date: Inclusive period end (string date).

    Returns:
        Mean of the annual precipitation totals (mm/yr), or NaN if too short.
    """
    sub = series.loc[PERIOD_START:end_date]
    if len(sub) < 365:
        return np.nan
    return float(sub.resample("YE").sum().mean())


def annual_mean_mm_yr(series: pd.Series) -> float:
    """Long-term annual mean (mm/yr) from daily means.

    Reproduces ``scripts/hess_quality_audit.py._annual_mean_mm_yr``:
    ``mean(daily.dropna()) * 365.25``.

    Args:
        series: Daily series (mm/day) indexed by date.

    Returns:
        Long-term annual mean (mm/yr), or NaN if the series has no finite values.
    """
    valid = series.dropna()
    if valid.empty:
        return np.nan
    return float(valid.mean()) * 365.25


def era5_dir(mode: str) -> Path:
    """Return the ERA5-Land precip directory for the chosen mode.

    Args:
        mode: ``"stale"`` (truncated 2018-02 copy) or ``"full"`` (2007-2024).

    Returns:
        Directory holding per-gauge ERA5-Land CSVs.
    """
    return ERA5_STALE_DIR if mode == "stale" else ERA5_FULL_DIR


# ── Data loading ──────────────────────────────────────────────────────────────
def load_paper_gauge_ids() -> list[str]:
    """Return the paper-analysis gauge universe from the geometry layer.

    Mirrors ``notebooks/03_ForcingsFinal.py``: read ``camels_gauges.gpkg``,
    index by ``gauge_id`` as string, then keep only paper-analysis gauges
    (gauge_id length < 7).

    Returns:
        Sorted-by-source list of paper-analysis gauge IDs (strings).
    """
    gdf = gpd.read_file(GEOM_GAUGES)
    gdf = gdf.set_index("gauge_id")
    gdf.index = gdf.index.astype(str)
    mask = paper_analysis_inclusion_mask(gdf.index)
    return gdf.index[mask.to_numpy()].tolist()


def load_precip(gauge_ids: list[str], era5_mode: str) -> dict[str, dict[str, pd.Series]]:
    """Load ERA5/MSWEP/GPCP daily precip series per gauge.

    Args:
        gauge_ids: Paper-analysis gauge IDs.
        era5_mode: ``"stale"`` or ``"full"`` ERA5-Land source.

    Returns:
        Mapping ``gauge_id -> {product: series}`` for available products.
    """
    e5_dir = era5_dir(era5_mode)
    out: dict[str, dict[str, pd.Series]] = {}
    for gid in gauge_ids:
        out[gid] = {}
        sources = {
            "era5": e5_dir / f"{gid}.csv",
            "mswep": MSWEP_DIR / f"{gid}.csv",
            "gpcp": GPCP_DIR / f"{gid}.csv",
        }
        for product, path in sources.items():
            s = load_csv_series(path, PRECIP_COL[product])
            if s is not None:
                out[gid][product] = s
    return out


def load_discharge_mm() -> tuple[dict[str, pd.Series], pd.DatetimeIndex]:
    """Load daily discharge (mm/day) per gauge from the release NetCDF.

    Returns:
        A ``(discharge, dates)`` tuple, where ``discharge`` maps ``gauge_id`` to
        the daily discharge series (mm/day) indexed by date with NaNs retained,
        and ``dates`` is the shared NetCDF date index (2008-2023).
    """
    with xr.open_dataset(DISCHARGE_NC) as ds:
        coord = "gauge_id" if "gauge_id" in ds.coords else "gauge"
        gauges = [str(g) for g in ds[coord].values]
        dates = pd.DatetimeIndex(ds["time"].values)
        q = ds["discharge_mm"].values  # shape (gauge, time)
    out: dict[str, pd.Series] = {}
    for i, gid in enumerate(gauges):
        out[gid] = pd.Series(q[i], index=dates, name="q_mm")
    return out, dates


def load_area_km2() -> dict[str, float]:
    """Load per-gauge catchment area (km2) from the release boundaries.

    Returns:
        Mapping ``gauge_id -> area_km2``.
    """
    gdf = gpd.read_file(BOUNDARIES)
    return {str(gid): float(area) for gid, area in zip(gdf["gauge_id"], gdf["area_km2"], strict=False)}


# ── Section 5.1: precipitation summary table ──────────────────────────────────
def precip_table(precip: dict[str, dict[str, pd.Series]]) -> dict[str, dict[str, float]]:
    """Spatial mean / std / CV of mean-annual precip per product.

    Per product: compute ``annual_mean_precip`` (per-gauge) over the product's
    period, then take the spatial mean, std (ddof=1), and CV(%) across gauges.

    Args:
        precip: Per-gauge product series.

    Returns:
        ``product -> {mean, std, cv_pct, n}``.
    """
    per_gauge: dict[str, list[float]] = {"era5": [], "mswep": [], "gpcp": []}
    for products in precip.values():
        for product, series in products.items():
            val = annual_mean_precip(series, PRECIP_END[product])
            if not np.isnan(val):
                per_gauge[product].append(val)

    table: dict[str, dict[str, float]] = {}
    for product, vals in per_gauge.items():
        arr = np.asarray(vals, dtype=float)
        mean = float(arr.mean())
        std = float(arr.std(ddof=1))
        table[product] = {
            "mean": mean,
            "std": std,
            "cv_pct": 100.0 * std / mean if mean else np.nan,
            "n": int(arr.size),
        }
    return table


def basin_averaged_bias(table: dict[str, dict[str, float]]) -> dict[str, float]:
    """Differences of the per-product spatial mean precip (mm/yr).

    Args:
        table: Output of :func:`precip_table`.

    Returns:
        Mapping of pair label to spatial-mean difference.
    """
    return {
        "era5_minus_mswep": table["era5"]["mean"] - table["mswep"]["mean"],
        "era5_minus_gpcp": table["era5"]["mean"] - table["gpcp"]["mean"],
        "mswep_minus_gpcp": table["mswep"]["mean"] - table["gpcp"]["mean"],
    }


def per_catchment_annual_bias(
    precip: dict[str, dict[str, pd.Series]],
) -> dict[str, dict[str, float]]:
    """Per-catchment annual precip bias over the common period (to COMMON_END).

    Per gauge with both products present, compute ``annual_mean_precip(., COMMON_END)``
    for each; take the mean of each product across the paired-gauge set, and
    report the difference.

    Args:
        precip: Per-gauge product series.

    Returns:
        ``pair -> {bias, n}``.
    """
    pairs = [
        ("era5", "mswep", "era5_minus_mswep"),
        ("era5", "gpcp", "era5_minus_gpcp"),
        ("mswep", "gpcp", "mswep_minus_gpcp"),
    ]
    out: dict[str, dict[str, float]] = {}
    for a_name, b_name, label in pairs:
        a_vals: list[float] = []
        b_vals: list[float] = []
        for products in precip.values():
            if a_name not in products or b_name not in products:
                continue
            a_val = annual_mean_precip(products[a_name], COMMON_END)
            b_val = annual_mean_precip(products[b_name], COMMON_END)
            if np.isnan(a_val) or np.isnan(b_val):
                continue
            a_vals.append(a_val)
            b_vals.append(b_val)
        n = len(a_vals)
        bias = float(np.mean(a_vals) - np.mean(b_vals)) if n else np.nan
        out[label] = {"bias": bias, "n": n}
    return out


# ── Section 5.2: Q/P runoff-ratio table + closure ─────────────────────────────
def hydro_year_sum(series: pd.Series) -> pd.Series:
    """Sum a daily series into hydrological-year totals (Oct-Sep).

    Args:
        series: Daily series indexed by date over ``PERIOD_START:PERIOD_END_ERA5``.

    Returns:
        Hydrological-year totals indexed by the year in which Sep falls.
    """
    sub = series.loc[PERIOD_START:PERIOD_END_ERA5]
    hydro_year = sub.index.year + (sub.index.month >= 10).astype(int)
    return sub.groupby(hydro_year).sum(min_count=1)


def qp_table(
    precip: dict[str, dict[str, pd.Series]],
    discharge: dict[str, pd.Series],
) -> dict[str, dict[str, float]]:
    """Per-product Q/P runoff-ratio summary.

    Per gauge with paired annual Q and P and >= 5 common hydrological years
    (Oct-Sep) over ``PERIOD_START:PERIOD_END_ERA5``: hydrological-year sums of Q
    and P, intersect years, per-year ratio q/p, per-gauge Q/P = median over
    years.  Reports the spatial median (the headline value quoted in prose), the
    raw spatial mean, a robust 5%-trimmed mean (``mean_trim5``, since a handful
    of low-P gauges inflate the raw mean), and the per-gauge Q/P > 1 count/pct.

    The published table's spatial *mean* (0.302) and Q/P>1 count (29) reflect an
    additional, undocumented outlier filter from the original notebook cell; the
    median is reproducible, the raw mean is not (see report caveat).

    Args:
        precip: Per-gauge product series.
        discharge: Per-gauge daily discharge (mm/day).

    Returns:
        ``product -> {median, mean, mean_trim5, qp_gt1_pct, qp_gt1_n, n}``.
    """
    per_gauge: dict[str, list[float]] = {"era5": [], "mswep": [], "gpcp": []}
    for gid, products in precip.items():
        q_series = discharge.get(gid)
        if q_series is None:
            continue
        q_sub = q_series.loc[PERIOD_START:PERIOD_END_ERA5].dropna()
        if q_sub.empty:
            continue
        q_ann = hydro_year_sum(q_sub)
        for product, p_series in products.items():
            if p_series.loc[PERIOD_START:PERIOD_END_ERA5].empty:
                continue
            p_ann = hydro_year_sum(p_series)
            years = p_ann.index.intersection(q_ann.index)
            if len(years) < 5:
                continue
            ratios = (q_ann.loc[years] / p_ann.loc[years]).replace([np.inf, -np.inf], np.nan)
            ratios = ratios.dropna()
            if len(ratios) < 5:
                continue
            per_gauge[product].append(float(ratios.median()))

    table: dict[str, dict[str, float]] = {}
    for product, vals in per_gauge.items():
        arr = np.asarray(vals, dtype=float)
        n = int(arr.size)
        gt1 = int((arr > 1.0).sum())
        table[product] = {
            "median": float(np.median(arr)) if n else np.nan,
            "mean": float(arr.mean()) if n else np.nan,
            "mean_trim5": _trimmed_mean(arr, 0.05) if n else np.nan,
            "qp_gt1_pct": 100.0 * gt1 / n if n else np.nan,
            "qp_gt1_n": gt1,
            "n": n,
        }
    return table


def _trimmed_mean(values: np.ndarray, proportion: float) -> float:
    """Symmetric trimmed mean dropping ``proportion`` from each tail.

    Args:
        values: 1-D array of finite values.
        proportion: Fraction to trim from each tail (0 <= proportion < 0.5).

    Returns:
        Mean of the central portion, or the raw mean if trimming empties it.
    """
    arr = np.sort(np.asarray(values, dtype=float))
    n = arr.size
    k = int(np.floor(n * proportion))
    core = arr[k : n - k] if n - 2 * k > 0 else arr
    return float(core.mean())


def seasonal_qp_era5(
    precip: dict[str, dict[str, pd.Series]],
    discharge: dict[str, pd.Series],
) -> dict[str, float]:
    """Seasonal Q/P under ERA5: median across gauges of per-season sum(Q)/sum(P).

    Per gauge over ``PERIOD_START:PERIOD_END_ERA5``, on the common daily index of
    ERA5 P and Q, sum daily Q and daily P within each meteorological season
    (DJF/MAM/JJA/SON) and take the ratio; the season value is the median of these
    per-gauge ratios.

    Args:
        precip: Per-gauge product series (ERA5 used).
        discharge: Per-gauge daily discharge (mm/day).

    Returns:
        ``season -> median Q/P`` for DJF, MAM, JJA, SON.
    """
    per_season: dict[str, list[float]] = {"DJF": [], "MAM": [], "JJA": [], "SON": []}
    for gid, products in precip.items():
        if "era5" not in products:
            continue
        q_series = discharge.get(gid)
        if q_series is None:
            continue
        p = products["era5"].loc[PERIOD_START:PERIOD_END_ERA5].dropna()
        q = q_series.loc[PERIOD_START:PERIOD_END_ERA5].dropna()
        common = p.index.intersection(q.index)
        if len(common) < 365:
            continue
        seasons = pd.Series(common.month.map(MONTH_TO_SEASON), index=common)
        p_c = p.loc[common]
        q_c = q.loc[common]
        for season in per_season:
            sel = seasons == season
            p_sum = float(p_c[sel].sum())
            q_sum = float(q_c[sel].sum())
            if p_sum > 0:
                per_season[season].append(q_sum / p_sum)
    return {season: float(np.median(vals)) if vals else np.nan for season, vals in per_season.items()}


# ── Section 5.3: AET>PET adequacy fraction ────────────────────────────────────
def _aet_gauge_inputs(
    gid: str,
    q_series: pd.Series | None,
    area: float,
    discharge_dates: pd.DatetimeIndex,
) -> tuple[float, float] | None:
    """Return ``(q_mm_yr, pet_gleam_mm_yr)`` if a gauge passes the AET filter.

    Reproduces ``scripts/hess_quality_audit.py._hydroclimate_worker``: the gauge
    must not be paper-analysis-excluded, have ``50 <= area_km2 < 50000``, have
    ``>= 5*365`` finite discharge days, and have GLEAM PET *and* AET available
    over the discharge date range.  GLEAM is reindexed to the discharge dates
    before the long-term annual means, so the means cover only 2008-2023.

    Args:
        gid: Gauge ID.
        q_series: Daily discharge (mm/day) over the discharge date index, or None.
        area: Catchment area (km2); inf if unknown.
        discharge_dates: Discharge NetCDF date index used to clip GLEAM.

    Returns:
        ``(q_mm_yr, pet_gleam_mm_yr)`` if the gauge qualifies, else ``None``.
    """
    if is_paper_analysis_excluded_gauge_id(gid) or q_series is None:
        return None
    if not (50.0 <= area < 50_000):
        return None
    q_valid = q_series.dropna()
    if len(q_valid) < 365 * 5:
        return None

    gleam_path = GLEAM_DIR / f"{gid}.csv"
    if not gleam_path.exists():
        return None
    try:
        gleam = pd.read_csv(
            gleam_path,
            index_col="date",
            parse_dates=True,
            usecols=["date", GLEAM_AET_COL, GLEAM_PET_COL],
        ).reindex(discharge_dates)
    except Exception:  # noqa: BLE001
        return None
    if gleam[GLEAM_PET_COL].dropna().empty:
        return None
    pet_gleam = annual_mean_mm_yr(gleam[GLEAM_PET_COL])
    aet_gleam = annual_mean_mm_yr(gleam[GLEAM_AET_COL])
    if not (np.isfinite(pet_gleam) and np.isfinite(aet_gleam)):
        return None
    return annual_mean_mm_yr(q_series), pet_gleam


def aet_gt_pet(
    precip: dict[str, dict[str, pd.Series]],
    discharge: dict[str, pd.Series],
    area_km2: dict[str, float],
    discharge_dates: pd.DatetimeIndex,
) -> dict[str, dict[str, float]]:
    """Fraction of gauges where water-balance AET exceeds GLEAM PET, per product.

    Reproduces ``scripts/hess_quality_audit.py`` (the ``budyko_aet_table.csv``
    ``aet_area_ge_50`` path).  Per-product precip is reindexed to the discharge
    date index, long-term annual means use ``mean(daily)*365.25``, and
    ``AET_wb = P_mm_yr - Q_mm_yr`` is compared against GLEAM PET.

    Args:
        precip: Per-gauge product series.
        discharge: Per-gauge daily discharge (mm/day) over the discharge dates.
        area_km2: Per-gauge catchment area (km2).
        discharge_dates: Discharge NetCDF date index used to clip precip/GLEAM.

    Returns:
        ``product -> {frac_pct, n_gt, n}``.
    """
    counts: dict[str, dict[str, int]] = {p: {"n_gt": 0, "n": 0} for p in ("era5", "mswep", "gpcp")}
    for gid, products in precip.items():
        inputs = _aet_gauge_inputs(gid, discharge.get(gid), area_km2.get(gid, np.inf), discharge_dates)
        if inputs is None:
            continue
        q_mm_yr, pet_gleam = inputs
        for product, p_series in products.items():
            p_mm_yr = annual_mean_mm_yr(p_series.reindex(discharge_dates))
            if not (np.isfinite(p_mm_yr) and np.isfinite(q_mm_yr)):
                continue
            counts[product]["n"] += 1
            if p_mm_yr - q_mm_yr > pet_gleam:
                counts[product]["n_gt"] += 1

    out: dict[str, dict[str, float]] = {}
    for product, c in counts.items():
        n = c["n"]
        out[product] = {
            "frac_pct": 100.0 * c["n_gt"] / n if n else np.nan,
            "n_gt": c["n_gt"],
            "n": n,
        }
    return out


# ── Report ────────────────────────────────────────────────────────────────────
def build_report(era5_mode: str) -> dict[str, object]:
    """Compute every Section 5 forcing number for the chosen ERA5 source.

    Args:
        era5_mode: ``"stale"`` or ``"full"``.

    Returns:
        Nested dict of all computed quantities.
    """
    gauge_ids = load_paper_gauge_ids()
    precip = load_precip(gauge_ids, era5_mode)
    discharge, discharge_dates = load_discharge_mm()
    area_km2 = load_area_km2()

    p_table = precip_table(precip)
    return {
        "era5_mode": era5_mode,
        "n_paper_gauges": len(gauge_ids),
        "precip_table": p_table,
        "basin_bias": basin_averaged_bias(p_table),
        "per_catchment_bias": per_catchment_annual_bias(precip),
        "qp_table": qp_table(precip, discharge),
        "seasonal_qp_era5": seasonal_qp_era5(precip, discharge),
        "aet_gt_pet": aet_gt_pet(precip, discharge, area_km2, discharge_dates),
    }


def print_report(report: dict[str, object]) -> None:
    """Print a clean structured Section 5 report.

    Args:
        report: Output of :func:`build_report`.
    """
    bar = "=" * 78
    print(bar)
    print(f"FORCING-UNCERTAINTY RECOMPUTE  --  ERA5 mode: {report['era5_mode'].upper()}")
    print(f"Paper-analysis gauge universe: {report['n_paper_gauges']}")
    print(bar)

    print("\n[5.1] PRECIPITATION SUMMARY (spatial mean / std / CV over gauges)")
    print(f"  {'product':8s} {'mean':>8s} {'std':>8s} {'CV %':>8s} {'n':>7s}")
    for product in ("era5", "mswep", "gpcp"):
        t = report["precip_table"][product]  # type: ignore[index]
        print(f"  {product.upper():8s} {t['mean']:8.1f} {t['std']:8.1f} {t['cv_pct']:8.1f} {t['n']:7d}")

    print("\n[5.1] BASIN-AVERAGED BIAS (difference of spatial means, mm/yr)")
    for label, val in report["basin_bias"].items():  # type: ignore[union-attr]
        print(f"  {label:20s} {val:8.1f}")

    print("\n[5.1] PER-CATCHMENT ANNUAL BIAS (paired gauges, to 2021-09-30)")
    for label, d in report["per_catchment_bias"].items():  # type: ignore[union-attr]
        print(f"  {label:20s} {d['bias']:8.1f}   (n={d['n']})")

    print("\n[5.2] Q/P RUNOFF-RATIO TABLE (per-gauge median ratio; >=5 hydro years)")
    print(
        f"  {'product':8s} {'median':>8s} {'mean':>8s} {'mean5%':>8s} "
        f"{'Q/P>1 %':>9s} {'n_gt1':>6s} {'n':>7s}"
    )
    for product in ("era5", "mswep", "gpcp"):
        t = report["qp_table"][product]  # type: ignore[index]
        print(
            f"  {product.upper():8s} {t['median']:8.3f} {t['mean']:8.3f} {t['mean_trim5']:8.3f} "
            f"{t['qp_gt1_pct']:9.1f} {t['qp_gt1_n']:6d} {t['n']:7d}"
        )
    print(
        "  NOTE: median reproduces the published value; the raw spatial mean is "
        "inflated by a\n        few low-P gauges (published 0.302/0.453/0.433 used "
        "an undocumented outlier\n        filter). The 5%-trimmed mean is shown as "
        "a robust proxy."
    )
    era5_qp = report["qp_table"]["era5"]  # type: ignore[index]
    closure = 100.0 - era5_qp["qp_gt1_pct"]
    print(f"\n[5.2] CLOSURE: % catchments Q/P <= 1 under ERA5 = {closure:.1f}%")

    print("\n[5.2] SEASONAL Q/P UNDER ERA5 (median across gauges)")
    for season in ("DJF", "MAM", "JJA", "SON"):
        print(f"  {season:5s} {report['seasonal_qp_era5'][season]:6.2f}")  # type: ignore[index]

    print("\n[5.3] AET(water-balance) > PET(GLEAM) ADEQUACY FRACTION")
    print(f"  {'product':8s} {'frac %':>8s} {'n_gt':>7s} {'n':>7s}")
    for product in ("era5", "mswep", "gpcp"):
        t = report["aet_gt_pet"][product]  # type: ignore[index]
        print(f"  {product.upper():8s} {t['frac_pct']:8.1f} {t['n_gt']:7d} {t['n']:7d}")
    print(bar)


def main() -> None:
    """Parse arguments and print the Section 5 forcing report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--era5",
        choices=["stale", "full"],
        default="full",
        help="ERA5-Land precip source: 'stale' (truncated 2018-02) or 'full' (2007-2024).",
    )
    args = parser.parse_args()
    report = build_report(args.era5)
    print_report(report)


if __name__ == "__main__":
    main()
