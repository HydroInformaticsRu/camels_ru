#!/usr/bin/env python3
"""Create CAMELS-RU signatures CSV from hydrological analysis results.

This script extracts the 10 hydrological signatures + trend statistics
from the complete hydrological analysis and creates the signatures file
for the CAMELS-RU dataset paper.

Output: camels_ru_signatures.csv
- Rows: 2,251 catchments (with >80% data completeness, 2008-2023)
- Columns: 15 (gauge_id + 10 signatures + 4 trend statistics)

Signatures:
1. Mean annual discharge (mm/day) - Magnitude
2. Runoff ratio - Magnitude (calculated from precipitation data)
3. Discharge CV - Variability
4. FDC slope - Variability
5. Q5 (mm/day) - Extremes (high flow)
6. Q95 (mm/day) - Extremes (low flow)
7. High-flow frequency (%) - Extremes
8. BFI (Baseflow index) - Baseflow
9. Recession constant - Baseflow (placeholder, needs implementation)
10. Peak discharge timing (day of year) - Seasonality

Trend statistics:
1. Mann-Kendall Z-statistic
2. p-value
3. Sen's slope (mm/day/decade)
4. Trend direction (increasing/decreasing/non-significant)
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.append(str(Path(__file__).parent.parent))
from src.utils.logger import setup_logger

logger = setup_logger("create_signatures", log_file="../logs/create_signatures.log")

# Paths
BASE_DIR = Path(__file__).parent.parent
HYDRO_FILE = (
    BASE_DIR
    / "docs/analysis_results/hydrological_representation/tables/hydrological_analysis_complete.csv"
)
FORCING_FILE = (
    BASE_DIR / "paper/analysis_results/forcing_representation/tables/forcing_analysis_complete.csv"
)
OUTPUT_FILE = (
    BASE_DIR / "paper/analysis_results/hydrological_representation/tables/camels_ru_signatures.csv"
)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

logger.info("Loading hydrological analysis data...")
hydro_df = pd.read_csv(HYDRO_FILE, dtype={"gauge_id": str}, index_col=0)
logger.info(f"Loaded {len(hydro_df)} gauges from hydrological analysis")

# Filter to high-quality catchments (>80% data completeness)
if "n_valid_periods" in hydro_df.columns and "n_years" in hydro_df.columns:
    data_completeness = hydro_df["n_valid_periods"] / hydro_df["n_years"]
    high_quality_mask = data_completeness > 0.8
    hydro_df = hydro_df[high_quality_mask]
    logger.info(f"Filtered to {len(hydro_df)} catchments with >80% data completeness")

# Load forcing data for runoff ratio calculation
logger.info("Loading forcing data for runoff ratio...")
forcing_df = pd.read_csv(FORCING_FILE, dtype={"gauge_id": str}, index_col=0)
# Ensure index is string type for matching
forcing_df.index = forcing_df.index.astype(str)
hydro_df.index = hydro_df.index.astype(str)

# Create signatures dataframe with required columns
signatures = pd.DataFrame(index=hydro_df.index)
signatures.index.name = "gauge_id"

# Calculate runoff ratio: mean_discharge (mm/day) × 365 / mean_annual_precip (mm/year)
# Using ERA5 precipitation as primary source
if "era5_mean_annual" in forcing_df.columns:
    # Find common gauges
    common_gauges = signatures.index.intersection(forcing_df.index)
    signatures["runoff_ratio"] = np.nan
    signatures.loc[common_gauges, "runoff_ratio"] = (
        hydro_df.loc[common_gauges, "mean_discharge"]
        * 365.25
        / forcing_df.loc[common_gauges, "era5_mean_annual"]
    )
    logger.info(f"Calculated runoff ratio for {len(common_gauges)} catchments from ERA5 precipitation")
else:
    logger.warning("ERA5 precipitation not found, runoff ratio will be NaN")
    signatures["runoff_ratio"] = np.nan

# 1. Magnitude signatures
signatures["mean_annual_discharge_mm_day"] = hydro_df["mean_discharge"]

# 2. Variability signatures
signatures["discharge_cv"] = hydro_df["cv_discharge"]
signatures["fdc_slope"] = hydro_df["fdc_slope"]

# 3. Extremes signatures
signatures["q05_high_flow_mm_day"] = hydro_df["q05"]
signatures["q95_low_flow_mm_day"] = hydro_df["q95"]
signatures["high_flow_frequency_pct"] = hydro_df["high_flow_frequency"]

# 4. Baseflow signatures
signatures["baseflow_index"] = hydro_df["baseflow_index"]
# Recession constant - placeholder (would need daily discharge analysis)
# For now, use a proxy: mean_discharge / baseflow_discharge ratio
signatures["recession_constant_placeholder"] = np.nan  # TODO: Implement proper recession analysis
logger.warning("Recession constant not yet implemented - using placeholder NaN")

# 5. Seasonality signature
signatures["peak_discharge_timing_doy"] = hydro_df["mean_half_flow_date"]


# 6. Trend statistics
# Calculate Mann-Kendall Z-statistic from p-value
# Two-tailed test: Z = Φ^(-1)(1 - p/2) for positive trends
#                  Z = -Φ^(-1)(1 - p/2) for negative trends
def calculate_mk_z(row):
    """Calculate Mann-Kendall Z-statistic from p-value and direction."""
    p_val = row["trend_pvalue"]
    direction = row["trend_direction"]

    if pd.isna(p_val) or pd.isna(direction):
        return np.nan

    # For two-tailed test, convert p-value to Z-score
    if p_val >= 1.0:
        return 0.0

    z_abs = stats.norm.ppf(1 - p_val / 2)

    # Apply sign based on direction
    if direction == "increasing":
        return z_abs
    elif direction == "decreasing":
        return -z_abs
    else:  # "no trend"
        return 0.0


signatures["mann_kendall_z"] = hydro_df.apply(calculate_mk_z, axis=1)
signatures["mann_kendall_p_value"] = hydro_df["trend_pvalue"]
signatures["sen_slope_mm_day_decade"] = hydro_df["trend_per_decade"]
signatures["trend_direction"] = hydro_df["trend_direction"]

# Remove rows with too many missing values (keep if at least 10 of 14 metrics present)
signatures = signatures.dropna(thresh=10)

logger.info(f"Final signatures dataset: {len(signatures)} catchments")

# Export to CSV
signatures.to_csv(OUTPUT_FILE)
logger.info(f"Saved signatures to: {OUTPUT_FILE}")

# Print summary statistics
logger.info("\n" + "=" * 80)
logger.info("SUMMARY STATISTICS")
logger.info("=" * 80)

for col in signatures.columns:
    if signatures[col].dtype in ["float64", "int64"]:
        logger.info(
            f"{col:40s}: mean={signatures[col].mean():8.3f}, "
            f"median={signatures[col].median():8.3f}, "
            f"n={signatures[col].notna().sum():4d}"
        )
    else:
        logger.info(f"{col:40s}: {signatures[col].value_counts().to_dict()}")

logger.info("=" * 80)

print(f"\n✓ Successfully created {OUTPUT_FILE}")
print(f"  Catchments: {len(signatures)}")
print(f"  Signatures: {len(signatures.columns)}")
print("  Period: 2008-2023 (>80% data completeness)")
