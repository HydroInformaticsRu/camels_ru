#!/usr/bin/env python3
"""Regenerate the 15 hydrological signatures declared in the manuscript (paper/overleaf, Table 3).

Inputs (release files only, so the signatures are reproducible from the archive):
- `release/CAMELS_RU_v1.0/camels_ru_discharge.nc` (discharge_mm)
- `release/CAMELS_RU_v1.0/camels_ru_forcing.nc` (precip_mswep, precip_era5, pet)
- `release/CAMELS_RU_v1.0/camels_ru_boundaries.gpkg` (area filter)

Outputs (written to `--output-dir`):
- `camels_ru_signatures.csv` — per-gauge × 15 signatures (+ `_era5` water-balance variants)
- `camels_ru_signatures_summary.csv` — summary stats (n, mean, median, min, max, std) per signature

Conventions (2026-08-23 revision, science-review Domain Expert M-1/M-5):
- Only the 15 hydrological years that lie fully inside the 2008-2023 grid are used
  (Oct 2008 to Sep 2023); the partial edge periods are dropped.
- A hydrological year is valid when at least 70 % of its days carry discharge; a gauge
  needs at least 5 valid years. Signatures are the mean over valid years.
- Water-balance ratios (runoff_ratio Q/P, aridity_index PET/P, evaporative_index (P-Q)/P)
- winter_flow_fraction: mean Jan-Mar flow / mean annual flow, on observed days. A
  Lyne-Hollick BFI with alpha in [0.9, 0.98] has a 10-50 day recession constant and so
  reads a multi-week snowmelt recession as baseflow; this measures cold-season yield
  directly and declines monotonically with permafrost extent, as the BFI does not.
  are computed per valid year over the days where discharge is observed, then averaged.
  MSWEP is the primary precipitation; `_era5` columns give the ERA5-Land variants.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from tqdm.auto import tqdm
import xarray as xr

sys.path.append(str(Path(__file__).parent.parent))
from src.hydro.flow_variability import FlowVariability  # noqa: E402
from src.hydro.period_based_metrics import (  # noqa: E402
    calculate_comprehensive_metrics,
    split_by_period,
)
from src.utils.logger import setup_logger  # noqa: E402

log = setup_logger("PaperSignatures", log_file="logs/paper_signatures.log")

SIGNATURE_ORDER = [
    "q_mean",
    "runoff_ratio",
    "q_cv",
    "fdc_slope",
    "flashiness_index",
    "q05",
    "q95",
    "high_flow_freq",
    "high_flow_dur",
    "baseflow_index",
    "low_flow_freq",
    "low_flow_dur",
    "half_flow_date",
    "winter_flow_fraction",
    "aridity_index",
    "evaporative_index",
]
ERA5_VARIANTS = ["runoff_ratio_era5", "aridity_index_era5", "evaporative_index_era5"]
HYDRO_YEAR_WINDOW = ("2008-10-01", "2023-09-30")  # complete hydrological years 2009-2023
MIN_DATA_FRACTION = 0.7
MIN_PERIODS = 5
# One winter season of observed Jan-Mar days before a winter flow fraction is reported.
MIN_WINTER_DAYS = 90


def _water_balance_ratios(
    discharge: pd.Series,
    precipitation: pd.Series,
    pet: pd.Series,
    min_data_fraction: float = MIN_DATA_FRACTION,
    min_periods: int = MIN_PERIODS,
) -> tuple[float, float, float]:
    """Mean annual Q/P, PET/P and (P-Q)/P over valid hydrological years, on paired days.

    A year is valid when at least ``min_data_fraction`` of its days carry discharge;
    within a year the sums run over the days where discharge, precipitation and PET are
    all present, so a winter gap does not bias the ratio through the precipitation of the
    missing days.
    """
    q_periods = split_by_period(discharge, "hydrological", 10)
    ratios: list[tuple[float, float, float]] = []
    for q in q_periods.values():
        if q.notna().mean() < min_data_fraction:
            continue
        p_year = precipitation.reindex(q.index)
        e_year = pet.reindex(q.index)
        paired = q.notna() & p_year.notna() & e_year.notna()
        if paired.sum() < min_data_fraction * len(q):
            continue
        p = p_year[paired]
        e = e_year[paired]
        total_p = float(np.nansum(p))
        if total_p <= 0:
            continue
        total_q = float(np.nansum(q[paired]))
        ratios.append((total_q / total_p, float(np.nansum(e)) / total_p, (total_p - total_q) / total_p))
    if len(ratios) < min_periods:
        return np.nan, np.nan, np.nan
    arr = np.asarray(ratios)
    return float(arr[:, 0].mean()), float(arr[:, 1].mean()), float(arr[:, 2].mean())


def _compute_one(
    gauge_id: str,
    discharge_values: np.ndarray,
    p_mswep: np.ndarray,
    p_era5: np.ndarray,
    pet_values: np.ndarray,
    dates: pd.DatetimeIndex,
) -> dict | None:
    """Compute all 16 signatures (plus ERA5-Land variants and winter coverage) for one gauge."""
    try:
        disch = pd.Series(np.asarray(discharge_values, dtype=np.float64), index=dates, name="discharge")
        disch = disch[HYDRO_YEAR_WINDOW[0] : HYDRO_YEAR_WINDOW[1]]

        metrics = calculate_comprehensive_metrics(
            disch,
            period_type="hydrological",
            hydro_year_start_month=10,
            min_data_fraction=MIN_DATA_FRACTION,
            min_periods=MIN_PERIODS,
            aggregation="mean",
        )
        if not np.isfinite(metrics.get("mean_discharge", np.nan)):
            return None

        pet = pd.Series(np.asarray(pet_values, dtype=np.float64), index=dates)
        mswep = pd.Series(np.asarray(p_mswep, dtype=np.float64), index=dates)
        era5 = pd.Series(np.asarray(p_era5, dtype=np.float64), index=dates)
        rr, ai, ei = _water_balance_ratios(disch, mswep, pet)
        rr_e, ai_e, ei_e = _water_balance_ratios(disch, era5, pet)

        flashiness = FlowVariability(disch).calculate_flashiness_index().get("flashiness_index", np.nan)

        # Cold-season yield, straight from the record: mean Jan-Mar flow over mean annual
        # flow, both on observed days only so a winter gap cannot depress the ratio.
        # winter_coverage reports how much of Dec-Mar was actually observed, because the
        # archive omits under-ice values at many gauges and the ratio is only as
        # trustworthy as that coverage.
        months = disch.index.month
        winter_obs = disch[months.isin([1, 2, 3])].dropna()
        annual_obs = disch.dropna()
        dec_mar = months.isin([12, 1, 2, 3])
        winter_coverage = float(disch[dec_mar].notna().sum() / max(int(dec_mar.sum()), 1))
        annual_mean = float(annual_obs.mean()) if len(annual_obs) else np.nan
        winter_fraction = (
            float(winter_obs.mean()) / annual_mean
            if len(winter_obs) >= MIN_WINTER_DAYS and np.isfinite(annual_mean) and annual_mean > 0
            else np.nan
        )

        return {
            "gauge_id": gauge_id,
            "q_mean": metrics["mean_discharge"],
            "runoff_ratio": rr,
            "q_cv": metrics["cv_discharge"],
            "fdc_slope": metrics["fdc_slope"],
            "flashiness_index": flashiness,
            "q05": metrics["q05"],
            "q95": metrics["q95"],
            "high_flow_freq": metrics["high_flow_frequency"],
            "high_flow_dur": metrics["high_flow_avg_duration"],
            "baseflow_index": metrics["baseflow_index"],
            "low_flow_freq": metrics["low_flow_frequency"],
            "low_flow_dur": metrics["low_flow_avg_duration"],
            "half_flow_date": metrics["mean_half_flow_date"],
            "winter_flow_fraction": winter_fraction,
            "winter_coverage": winter_coverage,
            "aridity_index": ai,
            "evaporative_index": ei,
            "n_valid_years": metrics.get("n_valid_periods", 0),
            "runoff_ratio_era5": rr_e,
            "aridity_index_era5": ai_e,
            "evaporative_index_era5": ei_e,
        }
    except Exception as exc:
        log.error(f"gauge {gauge_id}: {exc!r}")
        return None


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--discharge-nc",
        type=Path,
        default=Path("release/CAMELS_RU_v1.0/camels_ru_discharge.nc"),
    )
    parser.add_argument(
        "--forcing-nc",
        type=Path,
        default=Path("release/CAMELS_RU_v1.0/camels_ru_forcing.nc"),
        help="Release forcing NetCDF (precip_mswep, precip_era5, pet)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/CAMELS_RU/statistics"),
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument(
        "--boundaries",
        type=Path,
        default=Path("release/CAMELS_RU_v1.0/camels_ru_boundaries.gpkg"),
        help="GeoPackage with gauge_id and area_km2 — used for the <50,000 km² filter",
    )
    parser.add_argument(
        "--area-max-km2",
        type=float,
        default=50_000.0,
        help="Catchment area cutoff; gauges larger than this are excluded (§3.5)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"Loading discharge from {args.discharge_nc}")
    ds = xr.open_dataset(args.discharge_nc)

    dvar = None
    for candidate in ["discharge_mm", "Q_mm", "q_mm"]:
        if candidate in ds.data_vars:
            dvar = candidate
            break
    if dvar is None:
        raise ValueError(f"No discharge_mm variable in {args.discharge_nc}: {list(ds.data_vars)}")

    gauge_coord = "gauge_id" if "gauge_id" in ds.coords else "gauge"
    gauges = [str(g) for g in ds[gauge_coord].values]
    dates = pd.DatetimeIndex(ds["time"].values)
    discharge = ds[dvar].values

    log.info(f"{len(gauges)} gauges × {len(dates)} days in {dvar}")

    forcing = xr.open_dataset(args.forcing_nc).reindex(gauge_id=gauges, time=dates)
    p_mswep = forcing["precip_mswep"].values
    p_era5 = forcing["precip_era5"].values
    pet_values = forcing["pet"].values
    log.info(f"Loaded precip_mswep, precip_era5, pet from {args.forcing_nc}")

    # Apply area filter (< 50,000 km²) per paper §3.5
    import geopandas as gpd  # noqa: PLC0415

    ws = gpd.read_file(args.boundaries)[["gauge_id", "area_km2"]]
    ws["gauge_id"] = ws["gauge_id"].astype(str)
    small_gauges = set(ws.loc[ws["area_km2"] < args.area_max_km2, "gauge_id"])
    log.info(
        f"{len(small_gauges)} of {len(ws)} catchments are < {args.area_max_km2:g} km² (area filter)"
    )

    in_window = (dates >= HYDRO_YEAR_WINDOW[0]) & (dates <= HYDRO_YEAR_WINDOW[1])
    valid_indices = [
        i
        for i in range(len(gauges))
        if gauges[i] in small_gauges and np.isfinite(discharge[i][in_window]).any()
    ]
    # The >= 5 valid-year rule is applied inside calculate_comprehensive_metrics (min_periods);
    # no day-count pre-filter, so the stated rule alone defines the gauge set.
    log.info(f"{len(valid_indices)} gauges pass area < {args.area_max_km2:g} km² with discharge")

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=args.workers) as exe:
        futures = {
            exe.submit(
                _compute_one,
                gauges[i],
                discharge[i],
                p_mswep[i],
                p_era5[i],
                pet_values[i],
                dates,
            ): gauges[i]
            for i in valid_indices
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Signatures"):
            r = fut.result()
            if r is not None:
                results.append(r)

    df = pd.DataFrame(results)

    # Flag implausible small-basin outliers (paper §3.5): area < 50 km² and q_mean > 20 mm/d.
    # These pass the area+5y filter but yield specific discharges inconsistent with their
    # drainage areas (likely rating-curve extrapolation or area underestimation), so they
    # are kept in the per-gauge CSV with an explicit flag and excluded from summary stats.
    area_lookup = dict(zip(ws["gauge_id"], ws["area_km2"], strict=False))
    df["area_km2"] = df["gauge_id"].map(area_lookup)
    df["is_anomalous"] = (df["area_km2"] < 50.0) & (df["q_mean"] > 20.0)
    log.info(
        f"{int(df['is_anomalous'].sum())} of {len(df)} gauges flagged is_anomalous "
        f"(area < 50 km² AND q_mean > 20 mm/d); excluded from summary statistics"
    )

    # A multi-year runoff ratio above 1 is physically impossible without inter-basin
    # import, so it marks a delineation, rating, or precipitation error. is_anomalous
    # does not catch these -- it screens tiny basins with huge specific discharge, a
    # disjoint population -- so the screen ships as its own column.
    df["water_balance_screen"] = df["runoff_ratio"] > 1.0
    log.info(
        f"{int(df['water_balance_screen'].sum())} of {len(df)} gauges flagged "
        f"water_balance_screen (multi-year runoff ratio > 1)"
    )

    df = df[
        [
            "gauge_id",
            "area_km2",
            "is_anomalous",
            "water_balance_screen",
            *SIGNATURE_ORDER,
            "winter_coverage",
            "n_valid_years",
            *ERA5_VARIANTS,
        ]
    ]
    # Deterministic row order so the released CSV is reproducible across rebuilds
    # (parallel processing otherwise yields completion-order rows, which perturbs
    # order-sensitive downstream statistics such as bootstrap resampling).
    df = df.sort_values("gauge_id", key=lambda s: s.astype("int64"), ignore_index=True)

    out_per_gauge = args.output_dir / "camels_ru_signatures.csv"
    df.to_csv(out_per_gauge, index=False, float_format="%.6g")
    log.info(f"Wrote {len(df)} gauge rows to {out_per_gauge}")

    df_clean = df[~df["is_anomalous"]]

    sig_descriptions = {
        "q_mean": "Mean daily discharge (mm/d)",
        "runoff_ratio": "Annual runoff ratio Q/P (MSWEP P, paired days)",
        "q_cv": "CV of daily discharge",
        "fdc_slope": "FDC slope [ln(Q33)-ln(Q66)]/33*100",
        "flashiness_index": "Richards-Baker flashiness Σ|ΔQ|/ΣQ",
        "q05": "Q05 high-flow threshold (mm/d)",
        "q95": "Q95 low-flow threshold (mm/d)",
        "high_flow_freq": "% of days with Q > 2×median",
        "high_flow_dur": "Mean duration of high-flow events (d)",
        "baseflow_index": "BFI (Lyne-Hollick ensemble, 1000 runs; smoothness index, "
        "not a groundwater fraction in nival regimes -- see winter_flow_fraction)",
        "low_flow_freq": "% of days with Q < 0.2×mean",
        "low_flow_dur": "Mean duration of low-flow events (d)",
        "half_flow_date": "Day of hydro year when 50% of annual Q has passed",
        "winter_flow_fraction": "Mean Jan-Mar flow / mean annual flow (observed days)",
        "aridity_index": "Aridity index PET/P (GLEAM4 PET, MSWEP P; mean of annual ratios)",
        "evaporative_index": "Evaporative index (P-Q)/P (MSWEP P; mean of annual ratios)",
    }

    summary_rows = []
    for sig in SIGNATURE_ORDER:
        s = df_clean[sig].dropna()
        summary_rows.append(
            {
                "signature": sig,
                "description": sig_descriptions[sig],
                "n_gauges": int(len(s)),
                "mean": float(s.mean()) if len(s) else np.nan,
                "median": float(s.median()) if len(s) else np.nan,
                "min": float(s.min()) if len(s) else np.nan,
                "max": float(s.max()) if len(s) else np.nan,
                "std": float(s.std()) if len(s) else np.nan,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    out_summary = args.output_dir / "camels_ru_signatures_summary.csv"
    summary_df.to_csv(out_summary, index=False, float_format="%.6g")
    log.info(f"Wrote {len(summary_df)} signature summary rows to {out_summary}")


if __name__ == "__main__":
    main()
