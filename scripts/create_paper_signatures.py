#!/usr/bin/env python3
"""Regenerate the 15 hydrological signatures declared in the manuscript (paper/overleaf, Table 3).

Inputs:
- Release discharge NetCDF (`release/CAMELS_RU_v1.0/camels_ru_discharge.nc`)
- ERA5-Land per-basin precipitation CSVs (`data/CAMELS_RU/parsed_meteo/era5_land/*.csv`)
- GLEAM4 per-basin PET CSVs (`data/CAMELS_RU/parsed_meteo/gleam/*.csv`)

Outputs (written to `--output-dir`):
- `camels_ru_signatures.csv` — per-gauge × 15 signatures
- `camels_ru_signatures_summary.csv` — summary stats (n, mean, median, min, max, std) per signature

Signatures produced (matching the manuscript signature table):
q_mean, runoff_ratio, q_cv, fdc_slope, flashiness_index, q05, q95,
high_flow_freq, high_flow_dur, baseflow_index, low_flow_freq, low_flow_dur, half_flow_date,
aridity_index (PET/P, mean of per-hydro-year ratios),
evaporative_index ((P-Q)/P, mean of per-hydro-year ratios).
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
    calculate_runoff_ratio,
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
    "aridity_index",
    "evaporative_index",
]


def _budyko_indices(
    discharge: pd.Series,
    precipitation: pd.Series,
    pet: pd.Series,
    hydro_year_start_month: int = 10,
    min_periods: int = 5,
) -> tuple[float, float]:
    """Compute aridity index (PET/P) and evaporative index ((P-Q)/P).

    Both are the mean of per-hydrological-year ratios over common years,
    matching the convention used by `calculate_runoff_ratio`.
    """
    q_periods = split_by_period(discharge, "hydrological", hydro_year_start_month)
    p_periods = split_by_period(precipitation, "hydrological", hydro_year_start_month)
    pet_periods = split_by_period(pet, "hydrological", hydro_year_start_month)

    common = set(q_periods) & set(p_periods) & set(pet_periods)
    if len(common) < min_periods:
        return np.nan, np.nan

    aridity: list[float] = []
    evaporative: list[float] = []
    for year in sorted(common):
        total_q = np.nansum(q_periods[year])
        total_p = np.nansum(p_periods[year])
        total_pet = np.nansum(pet_periods[year])
        if total_p > 0:
            aridity.append(total_pet / total_p)
            evaporative.append((total_p - total_q) / total_p)

    if len(aridity) < min_periods:
        return np.nan, np.nan
    return float(np.nanmean(aridity)), float(np.nanmean(evaporative))


def _compute_one(
    gauge_id: str,
    discharge_values: np.ndarray,
    dates: pd.DatetimeIndex,
    precip_dir: Path,
    era5_col: str,
    pet_dir: Path,
    pet_col: str,
) -> dict | None:
    """Compute all 15 signatures for a single gauge."""
    try:
        disch = pd.Series(np.asarray(discharge_values, dtype=np.float64), index=dates, name="discharge")
        disch = disch.dropna()
        if len(disch) < 365 * 5:
            return None

        metrics = calculate_comprehensive_metrics(
            disch,
            period_type="hydrological",
            hydro_year_start_month=10,
            min_data_fraction=0.7,
            min_periods=5,
            aggregation="mean",
        )
        if not np.isfinite(metrics.get("mean_discharge", np.nan)):
            return None

        precip_path = precip_dir / f"{gauge_id}.csv"
        runoff_ratio = np.nan
        p_series: pd.Series | None = None
        if precip_path.exists():
            p_series = pd.read_csv(
                precip_path, index_col="date", parse_dates=True, usecols=["date", era5_col]
            )[era5_col].reindex(dates)
            runoff_ratio = calculate_runoff_ratio(
                disch,
                p_series.dropna(),
                period_type="hydrological",
                hydro_year_start_month=10,
                min_periods=5,
            )

        aridity_index = np.nan
        evaporative_index = np.nan
        pet_path = pet_dir / f"{gauge_id}.csv"
        if pet_path.exists() and p_series is not None:
            pet_series = pd.read_csv(
                pet_path, index_col="date", parse_dates=True, usecols=["date", pet_col]
            )[pet_col].reindex(dates)
            aridity_index, evaporative_index = _budyko_indices(
                disch,
                p_series.dropna(),
                pet_series.dropna(),
                hydro_year_start_month=10,
                min_periods=5,
            )

        flashiness = FlowVariability(disch).calculate_flashiness_index().get("flashiness_index", np.nan)

        return {
            "gauge_id": gauge_id,
            "q_mean": metrics["mean_discharge"],
            "runoff_ratio": runoff_ratio,
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
            "aridity_index": aridity_index,
            "evaporative_index": evaporative_index,
            "n_valid_years": metrics.get("n_valid_periods", 0),
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
        "--precip-dir",
        type=Path,
        # Corrected de-accumulated ERA5-Land precip. The era5_land copy over-accumulated
        # tp (~1.5x), inflating P and biasing runoff_ratio/aridity/evaporative; this is the fix.
        default=Path("data/Russia/MeteoData/CamelsRU/era5land_tp_new"),
    )
    parser.add_argument("--era5-col", default="prcp")
    parser.add_argument(
        "--pet-dir",
        type=Path,
        default=Path("data/CAMELS_RU/parsed_meteo/gleam"),
        help="Directory of per-gauge GLEAM4 PET CSVs",
    )
    parser.add_argument("--pet-col", default="potential_evaporation")
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

    # Apply area filter (< 50,000 km²) per paper §3.5
    import geopandas as gpd  # noqa: PLC0415

    ws = gpd.read_file(args.boundaries)[["gauge_id", "area_km2"]]
    ws["gauge_id"] = ws["gauge_id"].astype(str)
    small_gauges = set(ws.loc[ws["area_km2"] < args.area_max_km2, "gauge_id"])
    log.info(
        f"{len(small_gauges)} of {len(ws)} catchments are < {args.area_max_km2:g} km² (area filter)"
    )

    valid_indices = [
        i
        for i in range(len(gauges))
        if gauges[i] in small_gauges and np.isfinite(discharge[i]).sum() >= 365 * 5
    ]
    log.info(
        f"{len(valid_indices)} gauges pass both area < {args.area_max_km2:g} km² "
        f"and ≥ 5 years of valid data filters"
    )

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=args.workers) as exe:
        futures = {
            exe.submit(
                _compute_one,
                gauges[i],
                discharge[i],
                dates,
                args.precip_dir,
                args.era5_col,
                args.pet_dir,
                args.pet_col,
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

    df = df[["gauge_id", "area_km2", "is_anomalous", *SIGNATURE_ORDER, "n_valid_years"]]
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
        "runoff_ratio": "Annual runoff ratio Q/P (ERA5-Land P)",
        "q_cv": "CV of daily discharge",
        "fdc_slope": "FDC slope [ln(Q33)-ln(Q66)]/33*100",
        "flashiness_index": "Richards-Baker flashiness Σ|ΔQ|/ΣQ",
        "q05": "Q05 high-flow threshold (mm/d)",
        "q95": "Q95 low-flow threshold (mm/d)",
        "high_flow_freq": "% of days with Q > 2×median",
        "high_flow_dur": "Mean duration of high-flow events (d)",
        "baseflow_index": "BFI (Lyne-Hollick ensemble, 1000 runs)",
        "low_flow_freq": "% of days with Q < 0.2×mean",
        "low_flow_dur": "Mean duration of low-flow events (d)",
        "half_flow_date": "Day of hydro year when 50% of annual Q has passed",
        "aridity_index": "Aridity index PET/P (GLEAM4 PET, ERA5-Land P; mean of annual ratios)",
        "evaporative_index": "Evaporative index (P-Q)/P (ERA5-Land P; mean of annual ratios)",
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
