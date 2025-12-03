#!/usr/bin/env python3
"""Generate CAMELS-RU hydrological signatures CSV for 2,251 catchments.

This script processes discharge time series data for catchments with >80% data
completeness (2008-2023) and generates a comprehensive signatures file with:
- 10 hydrological signatures (magnitude, variability, extremes, baseflow, timing)
- 4 trend statistics (Mann-Kendall Z, p-value, Sen's slope, trend direction)

Output: paper/analysis_results/hydrological_representation/tables/camels_ru_signatures.csv

Signature categories:
- Magnitude: Mean annual discharge (mm/day), runoff ratio
- Variability: Discharge CV, FDC slope
- Extremes: Q5 (high flow), Q95 (low flow), high-flow frequency
- Baseflow: BFI (baseflow index), recession constant
- Seasonality: Peak discharge timing (day of year)
- Trends: Mann-Kendall Z-statistic, p-value, Sen's slope (mm/day/decade),
           trend direction (increasing/decreasing/non-significant)

Usage:
    python create_signatures_csv.py [--workers N] [--min-completeness 0.8]
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

sys.path.append(str(Path(__file__).parent.parent))
from src.hydro.period_based_metrics import calculate_comprehensive_metrics, calculate_runoff_ratio
from src.timeseries_stats.trends import TrendAnalysis
from src.utils.logger import setup_logger

log = setup_logger("SignaturesCSV", log_file="../logs/signatures_creation.log")

# Constants
START_DATE = "2008-01-01"
END_DATE = "2023-12-31"
TIME_INDEX = pd.date_range(START_DATE, END_DATE, freq="D")
N_DAYS = len(TIME_INDEX)
MIN_DAYS_FOR_ANALYSIS = 300  # Minimum days per hydrological year


def load_discharge_series(gauge_id: str, base_dir: Path) -> pd.Series | None:
    """Load discharge time series for a gauge from CSV files.

    Args:
        gauge_id: Gauge identifier
        base_dir: Base directory containing Discharge/ folders

    Returns:
        Discharge series with datetime index (mm/day) or None if not found
    """
    # Search directories in order of preference
    search_dirs = [
        "Discharge/full/decent",
        "Discharge/partial/decent",
        "Discharge/full/poor",
        "Discharge/partial/poor",
    ]

    for search_dir in search_dirs:
        csv_path = base_dir / search_dir / f"{gauge_id}.csv"
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
                if "discharge_mm" in df.columns:
                    series = df["discharge_mm"]
                    # Reindex to standard time range
                    series = series.reindex(TIME_INDEX)
                    return series
                else:
                    log.warning(f"No discharge_mm column in {csv_path}")
                    return None
            except Exception as e:
                log.error(f"Error loading {csv_path}: {e}")
                return None

    return None


def load_precipitation_series(
    gauge_id: str, precip_dir: Path, dataset: str = "era5"
) -> pd.Series | None:
    """Load precipitation time series for a gauge.

    Args:
        gauge_id: Gauge identifier
        precip_dir: Directory containing precipitation CSV files
        dataset: Precipitation dataset name ('era5', 'mswep', 'gpcp')

    Returns:
        Precipitation series (mm/day) or None if not found
    """
    csv_path = precip_dir / dataset / f"{gauge_id}.csv"

    if not csv_path.exists():
        return None

    try:
        df = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
        if "precipitation" in df.columns:
            series = df["precipitation"]
            series = series.reindex(TIME_INDEX)
            return series
    except Exception as e:
        log.error(f"Error loading precipitation {csv_path}: {e}")
        return None

    return None


def calculate_recession_constant(discharge: pd.Series, min_recession_days: int = 5) -> float:
    """Calculate recession constant from discharge time series.

    Uses exponential decay fitting on recession periods (where dQ/dt < 0).

    Args:
        discharge: Discharge time series
        min_recession_days: Minimum length of recession period

    Returns:
        Recession constant (1/days) or NaN if insufficient data
    """
    try:
        # Identify recession periods
        valid_data = discharge.dropna()
        if len(valid_data) < 2 * min_recession_days:
            return np.nan

        # Calculate daily change
        dq = valid_data.diff()

        # Find recession periods (dQ/dt < 0 and Q > 0)
        is_recession = (dq < 0) & (valid_data > 0)

        # Extract recession segments
        recession_values = []
        current_segment = []

        for idx in valid_data.index:
            if is_recession.loc[idx]:
                current_segment.append(valid_data.loc[idx])
            else:
                if len(current_segment) >= min_recession_days:
                    recession_values.extend(current_segment)
                current_segment = []

        # Add final segment
        if len(current_segment) >= min_recession_days:
            recession_values.extend(current_segment)

        if len(recession_values) < 10:
            return np.nan

        # Fit exponential decay: Q(t) = Q0 * exp(-k*t)
        # Use linear regression on log-transformed data
        q_arr = np.array(recession_values[:-1])
        q_next = np.array(recession_values[1:])

        # Filter out zeros/negatives
        valid_mask = (q_arr > 0) & (q_next > 0)
        q_arr = q_arr[valid_mask]
        q_next = q_next[valid_mask]

        if len(q_arr) < 10:
            return np.nan

        # Calculate k from Q(t+1)/Q(t) = exp(-k)
        # k = -ln(Q(t+1)/Q(t))
        ratios = q_next / q_arr
        k_values = -np.log(ratios)

        # Use median to be robust to outliers
        k_median = np.median(k_values[k_values > 0])

        return float(k_median)

    except Exception as e:
        log.debug(f"Recession constant calculation failed: {e}")
        return np.nan


def calculate_trend_statistics(discharge: pd.Series, aggregation: str = "annual") -> dict[str, float]:
    """Calculate Mann-Kendall trend statistics on discharge time series.

    Args:
        discharge: Discharge time series (mm/day)
        aggregation: 'annual' for annual means, 'monthly' for monthly means

    Returns:
        Dictionary with mk_z, mk_pvalue, sen_slope (mm/day/decade), trend_direction
    """
    try:
        # Aggregate to annual means
        if aggregation == "annual":
            # Use hydrological years
            df = discharge.to_frame(name="discharge")
            df["hydro_year"] = df.index.year
            df.loc[df.index.month >= 10, "hydro_year"] += 1

            annual_means = df.groupby("hydro_year")["discharge"].mean()

            # Remove years with insufficient data
            annual_counts = df.groupby("hydro_year")["discharge"].count()
            valid_years = annual_counts[annual_counts >= 0.7 * 365].index
            annual_means = annual_means.loc[valid_years]

        else:
            annual_means = discharge.resample("YE").mean()

        # Remove NaN years
        annual_means = annual_means.dropna()

        if len(annual_means) < 5:
            return {
                "mk_z": np.nan,
                "mk_pvalue": np.nan,
                "sen_slope": np.nan,
                "sen_slope_per_decade": np.nan,
                "trend_direction": "insufficient_data",
            }

        # Run Mann-Kendall test using TrendAnalysis
        analyzer = TrendAnalysis(annual_means, variable_name="discharge")
        result = analyzer.mann_kendall_test(alpha=0.05)

        # Convert Sen's slope to per decade
        sen_slope = result.get("slope", np.nan)
        sen_slope_per_decade = sen_slope * 10 if not np.isnan(sen_slope) else np.nan

        # Determine trend direction
        trend_dir = result.get("trend", "no trend")
        if trend_dir == "no trend":
            trend_dir = "non-significant"

        return {
            "mk_z": result.get("z_statistic", np.nan),
            "mk_pvalue": result.get("p_value", np.nan),
            "sen_slope": sen_slope,
            "sen_slope_per_decade": sen_slope_per_decade,
            "trend_direction": trend_dir,
        }

    except Exception as e:
        log.error(f"Trend calculation failed: {e}")
        return {
            "mk_z": np.nan,
            "mk_pvalue": np.nan,
            "sen_slope": np.nan,
            "sen_slope_per_decade": np.nan,
            "trend_direction": "error",
        }


def process_single_gauge(
    gauge_id: str,
    base_dir: Path,
    precip_dir: Path,
    min_completeness: float = 0.8,
) -> dict | None:
    """Process a single gauge and calculate all signatures.

    Args:
        gauge_id: Gauge identifier
        base_dir: Base directory for discharge data
        precip_dir: Directory for precipitation data
        min_completeness: Minimum data completeness (0-1)

    Returns:
        Dictionary of signatures or None if insufficient data
    """
    try:
        # Load discharge
        discharge = load_discharge_series(gauge_id, base_dir)
        if discharge is None:
            return None

        # Check completeness
        completeness = discharge.notna().sum() / N_DAYS
        if completeness < min_completeness:
            log.debug(f"Gauge {gauge_id}: insufficient completeness {completeness:.2%}")
            return None

        # Calculate comprehensive metrics
        metrics = calculate_comprehensive_metrics(
            discharge,
            period_type="hydrological",
            hydro_year_start_month=10,
            min_data_fraction=0.7,
            min_periods=5,
            aggregation="mean",
        )

        # Load precipitation for runoff ratio
        precip = load_precipitation_series(gauge_id, precip_dir, dataset="era5")
        if precip is not None:
            runoff_ratio = calculate_runoff_ratio(
                discharge,
                precip,
                period_type="hydrological",
                hydro_year_start_month=10,
                min_periods=5,
            )
        else:
            runoff_ratio = np.nan

        # Calculate recession constant
        recession_const = calculate_recession_constant(discharge)

        # Calculate trend statistics
        trend_stats = calculate_trend_statistics(discharge, aggregation="annual")

        # Assemble signature dictionary
        signatures = {
            "gauge_id": gauge_id,
            # Magnitude
            "mean_annual_discharge": metrics.get("mean_discharge", np.nan),
            "runoff_ratio": runoff_ratio,
            # Variability
            "discharge_cv": metrics.get("cv_discharge", np.nan),
            "fdc_slope": metrics.get("fdc_slope", np.nan),
            # Extremes
            "q05": metrics.get("q05", np.nan),
            "q95": metrics.get("q95", np.nan),
            "high_flow_frequency": metrics.get("high_flow_frequency", np.nan),
            # Baseflow
            "baseflow_index": metrics.get("baseflow_index", np.nan),
            "recession_constant": recession_const,
            # Seasonality
            "peak_discharge_timing": metrics.get("mean_half_flow_date", np.nan),
            # Trends
            "trend_mk_z": trend_stats["mk_z"],
            "trend_pvalue": trend_stats["mk_pvalue"],
            "trend_sen_slope_per_decade": trend_stats["sen_slope_per_decade"],
            "trend_direction": trend_stats["trend_direction"],
            # Metadata
            "data_completeness": completeness,
            "n_valid_years": metrics.get("n_valid_periods", 0),
        }

        return signatures

    except Exception as e:
        log.error(f"Error processing gauge {gauge_id}: {e}")
        return None


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Generate CAMELS-RU hydrological signatures CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel workers (default: 8)",
    )
    parser.add_argument(
        "--min-completeness",
        type=float,
        default=0.8,
        help="Minimum data completeness (default: 0.8)",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("../data/HydroFiles"),
        help="Base directory containing Discharge/ folders (default: ../data/HydroFiles)",
    )
    parser.add_argument(
        "--precip-dir",
        type=Path,
        default=Path("../data/MeteoData/CamelsRU"),
        help="Precipitation data directory (default: ../data/MeteoData/CamelsRU)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path(
            "../paper/analysis_results/hydrological_representation/tables/camels_ru_signatures.csv"
        ),
        help="Output CSV file path",
    )
    parser.add_argument(
        "--gauge-list",
        type=Path,
        help="Optional: CSV file with gauge_id column to process (default: scan all)",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_file.parent.mkdir(parents=True, exist_ok=True)

    # Get gauge list
    if args.gauge_list and args.gauge_list.exists():
        log.info(f"Loading gauge list from {args.gauge_list}")
        gauge_df = pd.read_csv(args.gauge_list, dtype={"gauge_id": str})
        gauge_ids = gauge_df["gauge_id"].tolist()
    else:
        # Scan discharge directories
        log.info("Scanning for available gauges...")
        gauge_ids = set()
        for search_dir in ["Discharge/full/decent", "Discharge/partial/decent"]:
            dir_path = args.base_dir / search_dir
            if dir_path.exists():
                for csv_file in dir_path.glob("*.csv"):
                    gauge_ids.add(csv_file.stem)
        gauge_ids = sorted(list(gauge_ids))

    n_gauges = len(gauge_ids)
    log.info(f"Processing {n_gauges} gauges with {args.workers} workers...")
    log.info(f"Minimum completeness: {args.min_completeness:.0%}")

    # Process gauges in parallel
    results = []
    failed_gauges = []

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Submit tasks
        future_to_gauge = {
            executor.submit(
                process_single_gauge,
                gauge_id,
                args.base_dir,
                args.precip_dir,
                args.min_completeness,
            ): gauge_id
            for gauge_id in gauge_ids
        }

        # Collect results
        for future in tqdm(
            as_completed(future_to_gauge),
            total=n_gauges,
            desc="Processing gauges",
        ):
            gauge_id = future_to_gauge[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
                else:
                    failed_gauges.append(gauge_id)
            except Exception as e:
                log.error(f"Exception processing gauge {gauge_id}: {e}")
                failed_gauges.append(gauge_id)

    # Create DataFrame
    log.info(f"Successfully processed {len(results)} / {n_gauges} gauges")
    log.info(f"Failed or insufficient data: {len(failed_gauges)} gauges")

    if not results:
        log.error("No valid results to save!")
        return

    df = pd.DataFrame(results)

    # Sort by gauge_id
    df = df.sort_values("gauge_id").reset_index(drop=True)

    # Log statistics
    log.info("=" * 60)
    log.info("Signature Statistics:")
    log.info("-" * 60)

    signature_cols = [
        "mean_annual_discharge",
        "runoff_ratio",
        "discharge_cv",
        "fdc_slope",
        "q05",
        "q95",
        "high_flow_frequency",
        "baseflow_index",
        "recession_constant",
        "peak_discharge_timing",
    ]

    for col in signature_cols:
        if col in df.columns:
            valid_count = df[col].notna().sum()
            mean_val = df[col].mean()
            median_val = df[col].median()
            log.info(f"{col}: valid={valid_count}, mean={mean_val:.3f}, median={median_val:.3f}")

    # Log trend statistics
    trend_dir_counts = df["trend_direction"].value_counts()
    log.info("-" * 60)
    log.info("Trend Direction Counts:")
    for direction, count in trend_dir_counts.items():
        log.info(f"  {direction}: {count} ({count / len(df) * 100:.1f}%)")

    # Save to CSV
    log.info("=" * 60)
    log.info(f"Saving to {args.output_file}")
    df.to_csv(args.output_file, index=False)

    log.info(f"Output file created: {args.output_file}")
    log.info(f"Total rows: {len(df)}")
    log.info(f"Total columns: {len(df.columns)}")

    # Create summary report
    summary_path = args.output_file.parent / "signatures_summary.txt"
    with open(summary_path, "w") as f:
        f.write("CAMELS-RU Hydrological Signatures Summary\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Generated: {pd.Timestamp.now()}\n")
        f.write(f"Total gauges processed: {len(df)}\n")
        f.write(f"Period: {START_DATE} to {END_DATE}\n")
        f.write(f"Minimum completeness: {args.min_completeness:.0%}\n\n")

        f.write("Signature Statistics:\n")
        f.write("-" * 60 + "\n")
        for col in signature_cols:
            if col in df.columns:
                valid_count = df[col].notna().sum()
                mean_val = df[col].mean()
                median_val = df[col].median()
                std_val = df[col].std()
                min_val = df[col].min()
                max_val = df[col].max()
                f.write(f"\n{col}:\n")
                f.write(f"  Valid: {valid_count} / {len(df)} ({valid_count / len(df) * 100:.1f}%)\n")
                f.write(f"  Mean: {mean_val:.4f}\n")
                f.write(f"  Median: {median_val:.4f}\n")
                f.write(f"  Std: {std_val:.4f}\n")
                f.write(f"  Range: [{min_val:.4f}, {max_val:.4f}]\n")

        f.write("\n" + "-" * 60 + "\n")
        f.write("Trend Statistics:\n")
        f.write("-" * 60 + "\n")
        for direction, count in trend_dir_counts.items():
            f.write(f"  {direction}: {count} ({count / len(df) * 100:.1f}%)\n")

    log.info(f"Summary report: {summary_path}")
    log.info("Complete!")


if __name__ == "__main__":
    main()
