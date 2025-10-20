"""Water balance and precipitation-discharge relationship analysis.

This module provides functions for calculating water balance metrics,
runoff coefficients, and volume-based relationships between precipitation
and discharge time series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..utils.logger import setup_logger

logger = setup_logger("water_balance", log_file="logs/water_balance.log")


def calculate_annual_totals(
    series: pd.Series,
    period_type: str = "hydrological",
    hydro_year_start_month: int = 10,
) -> pd.Series:
    """Calculate annual total values from daily time series.

    Args:
        series: Daily time series with datetime index
        period_type: 'calendar' or 'hydrological'
        hydro_year_start_month: Starting month for hydrological year (default 10 = October)

    Returns:
        Annual total series indexed by year
    """
    if series.empty:
        return pd.Series(dtype=float)

    if period_type == "calendar":
        return series.resample("YE").sum()

    # Hydrological year
    df = series.to_frame(name="value")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("Series must have DatetimeIndex for hydrological year calculation")
    df["hydro_year"] = df.index.year
    df.loc[df.index.month >= hydro_year_start_month, "hydro_year"] += 1
    return df.groupby("hydro_year")["value"].sum()


def calculate_runoff_coefficient(
    precipitation: pd.Series,
    discharge: pd.Series,
    period_type: str = "hydrological",
    hydro_year_start_month: int = 10,
) -> dict[str, float]:
    """Calculate runoff coefficient (Q/P ratio) and related metrics.

    Args:
        precipitation: Daily precipitation [mm/day]
        discharge: Daily discharge [mm/day]
        period_type: 'calendar' or 'hydrological'
        hydro_year_start_month: Starting month for hydrological year

    Returns:
        Dictionary with runoff coefficient metrics:
        - mean_runoff_coefficient: Mean annual Q/P ratio
        - std_runoff_coefficient: Standard deviation of annual Q/P
        - cv_runoff_coefficient: Coefficient of variation
        - mean_annual_prcp: Mean annual precipitation [mm/yr]
        - mean_annual_discharge: Mean annual discharge [mm/yr]
        - mean_water_deficit: Mean annual P-Q deficit [mm/yr]
    """
    # Align time series
    common_idx = precipitation.index.intersection(discharge.index)
    if len(common_idx) < 365:
        logger.warning("Insufficient overlapping data for runoff coefficient calculation")
        return {
            "mean_runoff_coefficient": np.nan,
            "std_runoff_coefficient": np.nan,
            "cv_runoff_coefficient": np.nan,
            "mean_annual_prcp": np.nan,
            "mean_annual_discharge": np.nan,
            "mean_water_deficit": np.nan,
        }

    prcp_aligned = precipitation.loc[common_idx]
    discharge_aligned = discharge.loc[common_idx]

    # Calculate annual totals
    annual_prcp = calculate_annual_totals(prcp_aligned, period_type, hydro_year_start_month)
    annual_discharge = calculate_annual_totals(discharge_aligned, period_type, hydro_year_start_month)

    # Align annual series
    common_years = annual_prcp.index.intersection(annual_discharge.index)
    if len(common_years) < 3:
        logger.warning("Insufficient annual periods for runoff coefficient")
        return {
            "mean_runoff_coefficient": np.nan,
            "std_runoff_coefficient": np.nan,
            "cv_runoff_coefficient": np.nan,
            "mean_annual_prcp": np.nan,
            "mean_annual_discharge": np.nan,
            "mean_water_deficit": np.nan,
        }

    annual_prcp_aligned = annual_prcp.loc[common_years]
    annual_discharge_aligned = annual_discharge.loc[common_years]

    # Calculate runoff coefficients
    rc = annual_discharge_aligned / annual_prcp_aligned
    rc = rc.replace([np.inf, -np.inf], np.nan).dropna()

    if len(rc) == 0:
        mean_rc = np.nan
        std_rc = np.nan
        cv_rc = np.nan
    else:
        mean_rc = float(rc.mean())
        std_rc = float(rc.std())
        cv_rc = float(std_rc / mean_rc) if mean_rc > 0 else np.nan

    # Water balance components
    mean_annual_prcp = float(annual_prcp_aligned.mean())
    mean_annual_discharge = float(annual_discharge_aligned.mean())
    mean_water_deficit = mean_annual_prcp - mean_annual_discharge

    return {
        "mean_runoff_coefficient": mean_rc,
        "std_runoff_coefficient": std_rc,
        "cv_runoff_coefficient": cv_rc,
        "mean_annual_prcp": mean_annual_prcp,
        "mean_annual_discharge": mean_annual_discharge,
        "mean_water_deficit": mean_water_deficit,
    }


def calculate_volume_relationship(
    precipitation: pd.Series,
    discharge: pd.Series,
    period_type: str = "hydrological",
    hydro_year_start_month: int = 10,
) -> dict[str, float]:
    """Calculate volume-based relationships between precipitation and discharge.

    Args:
        precipitation: Daily precipitation [mm/day]
        discharge: Daily discharge [mm/day]
        period_type: 'calendar' or 'hydrological'
        hydro_year_start_month: Starting month for hydrological year

    Returns:
        Dictionary with volume relationship metrics:
        - prcp_discharge_correlation: Correlation of annual totals
        - prcp_discharge_slope: Linear regression slope (Q vs P)
        - prcp_discharge_intercept: Linear regression intercept
        - prcp_discharge_r_squared: R² of linear relationship
    """
    from scipy import stats

    # Align time series
    common_idx = precipitation.index.intersection(discharge.index)
    if len(common_idx) < 365:
        return {
            "prcp_discharge_correlation": np.nan,
            "prcp_discharge_slope": np.nan,
            "prcp_discharge_intercept": np.nan,
            "prcp_discharge_r_squared": np.nan,
        }

    prcp_aligned = precipitation.loc[common_idx]
    discharge_aligned = discharge.loc[common_idx]

    # Calculate annual totals
    annual_prcp = calculate_annual_totals(prcp_aligned, period_type, hydro_year_start_month)
    annual_discharge = calculate_annual_totals(discharge_aligned, period_type, hydro_year_start_month)

    # Align annual series
    common_years = annual_prcp.index.intersection(annual_discharge.index)
    if len(common_years) < 3:
        return {
            "prcp_discharge_correlation": np.nan,
            "prcp_discharge_slope": np.nan,
            "prcp_discharge_intercept": np.nan,
            "prcp_discharge_r_squared": np.nan,
        }

    annual_prcp_aligned = annual_prcp.loc[common_years].values
    annual_discharge_aligned = annual_discharge.loc[common_years].values

    # Calculate correlation and regression
    try:
        pearson_res = stats.pearsonr(annual_prcp_aligned, annual_discharge_aligned)
        linreg_res = stats.linregress(annual_prcp_aligned, annual_discharge_aligned)

        # Handle both old and new scipy API
        corr = pearson_res[0] if isinstance(pearson_res, tuple) else pearson_res.statistic  # type: ignore
        slope = linreg_res[0] if isinstance(linreg_res, tuple) else linreg_res.slope  # type: ignore
        intercept = linreg_res[1] if isinstance(linreg_res, tuple) else linreg_res.intercept  # type: ignore
        r_val = linreg_res[2] if isinstance(linreg_res, tuple) else linreg_res.rvalue  # type: ignore
    except Exception as e:
        logger.error(f"Error in volume relationship calculation: {e}")
        return {
            "prcp_discharge_correlation": np.nan,
            "prcp_discharge_slope": np.nan,
            "prcp_discharge_intercept": np.nan,
            "prcp_discharge_r_squared": np.nan,
        }

    return {
        "prcp_discharge_correlation": float(corr),  # type: ignore
        "prcp_discharge_slope": float(slope),  # type: ignore
        "prcp_discharge_intercept": float(intercept),  # type: ignore
        "prcp_discharge_r_squared": float(r_val * r_val),  # type: ignore
    }


def calculate_water_balance_metrics(
    precipitation_era5: pd.Series | None,
    precipitation_mswep: pd.Series | None,
    discharge: pd.Series,
    period_type: str = "hydrological",
    hydro_year_start_month: int = 10,
) -> dict[str, float]:
    """Calculate comprehensive water balance metrics.

    Args:
        precipitation_era5: Daily ERA5-Land precipitation [mm/day]
        precipitation_mswep: Daily MSWEP precipitation [mm/day]
        discharge: Daily discharge [mm/day]
        period_type: 'calendar' or 'hydrological'
        hydro_year_start_month: Starting month for hydrological year

    Returns:
        Dictionary with all water balance metrics (prefixed by dataset)
    """
    metrics = {}

    # ERA5-Land metrics
    if precipitation_era5 is not None and not precipitation_era5.empty:
        rc_era5 = calculate_runoff_coefficient(
            precipitation_era5, discharge, period_type, hydro_year_start_month
        )
        vol_era5 = calculate_volume_relationship(
            precipitation_era5, discharge, period_type, hydro_year_start_month
        )

        metrics.update({f"era5_{k}": v for k, v in rc_era5.items()})
        metrics.update({f"era5_{k}": v for k, v in vol_era5.items()})

    # MSWEP metrics
    if precipitation_mswep is not None and not precipitation_mswep.empty:
        rc_mswep = calculate_runoff_coefficient(
            precipitation_mswep, discharge, period_type, hydro_year_start_month
        )
        vol_mswep = calculate_volume_relationship(
            precipitation_mswep, discharge, period_type, hydro_year_start_month
        )

        metrics.update({f"mswep_{k}": v for k, v in rc_mswep.items()})
        metrics.update({f"mswep_{k}": v for k, v in vol_mswep.items()})

    return metrics
