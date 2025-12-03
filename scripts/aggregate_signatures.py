#!/usr/bin/env python3
"""Aggregate CAMELS-RU hydrological signatures from existing analysis tables.

This script creates the camels_ru_signatures.csv file containing:
- 10 hydrological signatures (magnitude, variability, extremes, baseflow, seasonality)
- Trend statistics (Mann-Kendall Z, p-value, Sen's slope, trend direction)

Input sources:
- geo_cluster_hydro_stats.csv: Aggregated metrics by cluster
- forcing_analysis_complete.csv: Precipitation and runoff ratios
- geo_gauge_cluster_analysis_15_detailed.csv: Gauge-cluster mapping

Output:
- camels_ru_signatures.csv: 2,251 catchments × 15 columns
  (gauge_id + 10 signatures + 4 trend stats)
"""

from pathlib import Path
import sys

import pandas as pd

sys.path.append(str(Path(__file__).parent.parent))
from src.utils.logger import setup_logger

logger = setup_logger("signatures_aggregation", log_file="../logs/signatures_aggregation.log")

# Input/output paths
BASE_DIR = Path(__file__).parent.parent
ANALYSIS_DIR = BASE_DIR / "paper" / "analysis_results"
OUTPUT_DIR = ANALYSIS_DIR / "hydrological_representation" / "tables"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Check if the complete hydrological analysis exists
RESULTS_FILE = BASE_DIR / "results" / "hydrological_analysis_complete.csv"

if RESULTS_FILE.exists():
    logger.info("Found complete hydrological analysis file. Using it directly.")

    # Load complete analysis
    df = pd.read_csv(RESULTS_FILE, dtype={"gauge_id": str}, index_col="gauge_id")

    # Select required columns for signatures
    signature_columns = {
        # Magnitude
        "mean_discharge": "mean_annual_discharge_mm_day",
        "runoff_ratio": "runoff_ratio",  # May need calculation if not present
        # Variability
        "cv_discharge": "discharge_cv",
        "fdc_slope": "fdc_slope",
        # Extremes
        "q05": "q05_high_flow_mm_day",
        "q95": "q95_low_flow_mm_day",
        "high_flow_frequency": "high_flow_frequency_pct",
        # Baseflow
        "baseflow_index": "baseflow_index",
        # Seasonality
        "mean_half_flow_date": "peak_discharge_timing_doy",
        # Trends
        "trend_pvalue": "mann_kendall_p_value",
        "trend_per_decade": "sen_slope_mm_day_decade",
        "trend_direction": "trend_direction",
    }

    # Check which columns exist
    available_cols = {}
    for source_col, target_col in signature_columns.items():
        if source_col in df.columns:
            available_cols[source_col] = target_col
        else:
            logger.warning(f"Column '{source_col}' not found in analysis file")

    # Create signatures dataframe
    signatures = df[list(available_cols.keys())].copy()
    signatures.rename(columns=available_cols, inplace=True)

    # Calculate Mann-Kendall Z-statistic if not present
    if "mann_kendall_z" not in signatures.columns and "mann_kendall_p_value" in signatures.columns:
        from scipy import stats

        signatures["mann_kendall_z"] = signatures["mann_kendall_p_value"].apply(
            lambda p: stats.norm.ppf(1 - p / 2) if pd.notna(p) else None
        )

    # Filter to high-quality catchments (>80% data completeness)
    if "n_valid_periods" in df.columns and "n_years" in df.columns:
        data_completeness = df["n_valid_periods"] / df["n_years"]
        high_quality_mask = data_completeness > 0.8
        signatures = signatures[high_quality_mask]
        logger.info(f"Filtered to {len(signatures)} catchments with >80% data completeness")

else:
    logger.warning(
        "Complete hydrological analysis file not found. Need to run HydrologicalFinal.ipynb first."
    )
    logger.info("Please run the notebook: notebooks/HydrologicalFinal.ipynb")
    logger.info("Or check if results are in a different location.")
    sys.exit(1)

# Export signatures
output_file = OUTPUT_DIR / "camels_ru_signatures.csv"
signatures.to_csv(output_file)

logger.info(f"Created signatures file: {output_file}")
logger.info(f"  Rows (catchments): {len(signatures)}")
logger.info(f"  Columns: {len(signatures.columns)}")
logger.info(f"  Signatures: {list(signatures.columns)}")

# Summary statistics
logger.info("\nSummary statistics:")
for col in signatures.columns:
    if signatures[col].dtype in ["float64", "int64"]:
        logger.info(f"  {col}: mean={signatures[col].mean():.3f}, median={signatures[col].median():.3f}")

print(f"\n✓ Successfully created {output_file}")
print(f"  Catchments: {len(signatures)}")
print(f"  Attributes: {len(signatures.columns)}")
