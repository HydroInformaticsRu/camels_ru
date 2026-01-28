"""Climatological pattern analysis for discharge quality assessment.

This module compares individual years against the long-term climatological
pattern to detect years that deviate from expected seasonal behavior.

For snowmelt-dominated (nival) catchments, the key indicator is the presence
of a clear seasonal peak rather than day-to-day correlation with climatology.
"""

import logging

import numpy as np
import pandas as pd

from .quality_flags import QualityFlag

logger = logging.getLogger(__name__)


def calculate_peak_ratio(discharge: pd.Series) -> float:
    """Calculate peak-to-mean ratio for a discharge series.

    For snowmelt-dominated catchments, a clear seasonal signal
    shows a high peak-to-mean ratio (typically >10).

    Args:
        discharge: Discharge time series.

    Returns:
        Peak-to-mean ratio (max/mean), or NaN if insufficient data.
    """
    valid_data = discharge.dropna()
    if len(valid_data) < 30:
        return np.nan

    mean_q = valid_data.mean()
    max_q = valid_data.max()

    if mean_q <= 0:
        return np.nan

    return float(max_q / mean_q)


def detect_seasonal_signal(
    discharge: pd.Series,
    year: int,
    hydro_year_start_month: int = 10,
    min_peak_ratio: float = 5.0,
) -> dict:
    """Detect presence of seasonal signal (flood peak) for a year.

    For snowmelt-dominated (nival) catchments, the primary quality
    indicator is whether there's a clear spring flood peak.

    Args:
        discharge: Full discharge time series.
        year: Hydrological year to evaluate.
        hydro_year_start_month: Start month of hydrological year.
        min_peak_ratio: Minimum peak/mean ratio to consider as "has signal".

    Returns:
        Dictionary with:
        - has_seasonal_signal: True if clear peak detected
        - peak_ratio: max/mean for the year
        - peak_value: Maximum discharge value
        - peak_date: Date of peak discharge
        - mean_value: Mean discharge for the year
    """
    # Extract year data
    if hydro_year_start_month > 1:
        start_date = pd.Timestamp(year=year - 1, month=hydro_year_start_month, day=1)
        end_date = pd.Timestamp(year=year, month=hydro_year_start_month, day=1) - pd.Timedelta(
            days=1
        )
    else:
        start_date = pd.Timestamp(year=year, month=1, day=1)
        end_date = pd.Timestamp(year=year, month=12, day=31)

    year_data = discharge.loc[start_date:end_date].dropna()

    if len(year_data) < 30:
        return {
            "has_seasonal_signal": False,
            "peak_ratio": np.nan,
            "peak_value": np.nan,
            "peak_date": None,
            "mean_value": np.nan,
        }

    mean_q = year_data.mean()
    max_q = year_data.max()
    peak_date = year_data.idxmax()

    if mean_q <= 0:
        peak_ratio = np.nan
        has_signal = False
    else:
        peak_ratio = max_q / mean_q
        has_signal = peak_ratio >= min_peak_ratio

    return {
        "has_seasonal_signal": has_signal,
        "peak_ratio": float(peak_ratio) if not np.isnan(peak_ratio) else np.nan,
        "peak_value": float(max_q),
        "peak_date": peak_date,
        "mean_value": float(mean_q),
    }


def detect_flat_years(
    discharge: pd.Series,
    hydro_year_start_month: int = 10,
    relative_threshold: float = 0.3,
    min_regime_peak_ratio: float = 10.0,
) -> dict[int, list[QualityFlag]]:
    """Detect years with flat hydrograph (no seasonal response).

    Uses a regime-aware approach:
    1. First, determine if catchment is "nival" (snowmelt-dominated) by checking
       if median peak ratio > min_regime_peak_ratio
    2. For nival catchments: flag years with peak_ratio < relative_threshold * median
    3. For stable catchments: don't flag any years (low peak ratio is normal)

    This avoids penalizing stable catchments that naturally have low variability.

    Args:
        discharge: Discharge time series with datetime index.
        hydro_year_start_month: Start month of hydrological year.
        relative_threshold: Fraction of median peak ratio below which
            a year is considered to have no seasonal signal (default 0.3 = 30%).
        min_regime_peak_ratio: Minimum median peak ratio to consider catchment
            as having seasonal regime (default 10.0). Below this, catchment is
            considered "stable" and no years are flagged.

    Returns:
        Dictionary mapping year to list of quality flags.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        logger.error("Discharge must have datetime index")
        return {}

    valid_data = discharge.dropna()
    if len(valid_data) == 0:
        return {}

    # Get hydrological years
    if hydro_year_start_month > 1:
        hydro_years = valid_data.index.year.copy()
        hydro_years = hydro_years.where(
            valid_data.index.month < hydro_year_start_month, hydro_years + 1
        )
        years = sorted(set(hydro_years))
    else:
        years = sorted(set(valid_data.index.year))

    # Calculate peak ratio for each year
    peak_ratios = {}
    for year in years:
        signal_info = detect_seasonal_signal(discharge, year, hydro_year_start_month)
        if not np.isnan(signal_info["peak_ratio"]):
            peak_ratios[year] = signal_info["peak_ratio"]

    if len(peak_ratios) < 3:
        return {}

    ratio_values = list(peak_ratios.values())

    # Use 75th percentile to detect regime - more robust when many bad years exist
    # This represents what "good" years look like for this catchment
    percentile_75 = np.percentile(ratio_values, 75)

    # Also check if ANY year has a high peak ratio (clear seasonal signal)
    max_ratio = max(ratio_values)

    # Check if catchment has seasonal regime (e.g., snowmelt-dominated)
    # Catchment is considered seasonal if:
    # - 75th percentile is high (some years show clear peaks), OR
    # - Maximum ratio is very high (at least one year with dramatic peak)
    is_seasonal = percentile_75 >= min_regime_peak_ratio or max_ratio >= min_regime_peak_ratio * 2

    if not is_seasonal:
        logger.debug(
            f"Stable catchment detected (p75={percentile_75:.1f}, max={max_ratio:.1f}). "
            "No flat year detection applied."
        )
        return {}

    # For seasonal catchments: flag years with much lower peak ratio than "good" years
    # Use 75th percentile as the baseline for what a good year looks like
    no_signal_threshold = percentile_75 * relative_threshold

    # Flag years with no seasonal signal
    flags_by_year: dict[int, list[QualityFlag]] = {}
    for year, ratio in peak_ratios.items():
        if ratio < no_signal_threshold:
            flags_by_year[year] = [QualityFlag.NO_SEASONAL_SIGNAL]

    return flags_by_year


def build_daily_climatology(discharge: pd.Series) -> pd.DataFrame:
    """Build day-of-year based climatology from discharge time series.

    Calculates mean, standard deviation, and percentiles for each day
    of the year (1-366) across all available years.

    Args:
        discharge: Discharge time series with datetime index (mm/day).

    Returns:
        DataFrame with index 1-366 (day of year) and columns:
        - mean: Mean discharge for each DOY
        - std: Standard deviation for each DOY
        - median: Median discharge for each DOY
        - q25: 25th percentile
        - q75: 75th percentile
        - q05: 5th percentile
        - q95: 95th percentile
        - count: Number of valid observations

    Raises:
        ValueError: If insufficient data for climatology.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        raise ValueError("Discharge must have datetime index")

    valid_data = discharge.dropna()
    if len(valid_data) < 365:
        raise ValueError("Insufficient data for climatology (need at least 1 year)")

    # Extract day of year
    doy = valid_data.index.dayofyear

    # Group by day of year and calculate statistics
    grouped = valid_data.groupby(doy)

    climatology = pd.DataFrame(
        {
            "mean": grouped.mean(),
            "std": grouped.std(),
            "median": grouped.median(),
            "q25": grouped.quantile(0.25),
            "q75": grouped.quantile(0.75),
            "q05": grouped.quantile(0.05),
            "q95": grouped.quantile(0.95),
            "count": grouped.count(),
        }
    )

    # Ensure all days 1-366 are present (fill missing with NaN)
    full_index = pd.RangeIndex(1, 367)
    climatology = climatology.reindex(full_index)
    climatology.index.name = "day_of_year"

    return climatology


def calculate_year_deviation(
    discharge: pd.Series,
    year: int,
    climatology: pd.DataFrame,
    hydro_year_start_month: int = 10,
) -> dict:
    """Compare a single year's hydrograph against climatology.

    Args:
        discharge: Full discharge time series with datetime index.
        year: Hydrological year to evaluate.
        climatology: Climatology DataFrame from build_daily_climatology.
        hydro_year_start_month: Start month of hydrological year (default: October).

    Returns:
        Dictionary with metrics:
        - correlation: Pearson correlation between year and climatology
        - nrmse: Normalized RMSE (RMSE / mean(climatology))
        - amplitude_ratio: max(Q_year) / max(Q_climatology)
        - bias: Mean difference (Q_year - Q_climatology)
        - completeness: Fraction of days with valid data
        - n_days: Number of valid days
    """
    # Extract hydrological year data
    if hydro_year_start_month > 1:
        start_date = pd.Timestamp(year=year - 1, month=hydro_year_start_month, day=1)
        end_date = pd.Timestamp(year=year, month=hydro_year_start_month, day=1) - pd.Timedelta(
            days=1
        )
    else:
        start_date = pd.Timestamp(year=year, month=1, day=1)
        end_date = pd.Timestamp(year=year, month=12, day=31)

    year_data = discharge.loc[start_date:end_date].dropna()

    if len(year_data) < 30:
        return {
            "correlation": np.nan,
            "nrmse": np.nan,
            "amplitude_ratio": np.nan,
            "bias": np.nan,
            "completeness": len(year_data) / 365,
            "n_days": len(year_data),
        }

    # Get day of year for each observation
    doy = year_data.index.dayofyear

    # Get corresponding climatology values
    clim_values = climatology.loc[doy, "mean"].values
    year_values = year_data.values

    # Filter out NaN climatology values
    valid_mask = ~np.isnan(clim_values)
    if valid_mask.sum() < 30:
        return {
            "correlation": np.nan,
            "nrmse": np.nan,
            "amplitude_ratio": np.nan,
            "bias": np.nan,
            "completeness": len(year_data) / 365,
            "n_days": len(year_data),
        }

    clim_valid = clim_values[valid_mask]
    year_valid = year_values[valid_mask]

    # Calculate correlation
    correlation = np.corrcoef(year_valid, clim_valid)[0, 1]

    # Calculate NRMSE
    rmse = np.sqrt(np.mean((year_valid - clim_valid) ** 2))
    clim_mean = np.mean(clim_valid)
    nrmse = rmse / clim_mean if clim_mean > 0 else np.nan

    # Calculate amplitude ratio
    year_max = np.max(year_valid)
    clim_max = climatology["mean"].max()
    amplitude_ratio = year_max / clim_max if clim_max > 0 else np.nan

    # Calculate bias
    bias = np.mean(year_valid - clim_valid)

    # Calculate completeness
    expected_days = (end_date - start_date).days + 1
    completeness = len(year_data) / expected_days

    return {
        "correlation": float(correlation) if not np.isnan(correlation) else np.nan,
        "nrmse": float(nrmse) if not np.isnan(nrmse) else np.nan,
        "amplitude_ratio": float(amplitude_ratio) if not np.isnan(amplitude_ratio) else np.nan,
        "bias": float(bias),
        "completeness": float(completeness),
        "n_days": len(year_data),
    }


def detect_climatology_anomalies(
    discharge: pd.Series,
    hydro_year_start_month: int = 10,
    min_correlation: float = 0.5,
    critical_correlation: float = 0.2,
    max_nrmse: float = 2.0,
    min_amplitude_ratio: float = 0.3,
    max_amplitude_ratio: float = 3.0,
) -> dict[int, list[QualityFlag]]:
    """Detect years with anomalous patterns compared to climatology.

    Args:
        discharge: Discharge time series with datetime index.
        hydro_year_start_month: Start month of hydrological year.
        min_correlation: Threshold for LOW_CLIM_CORRELATION flag.
        critical_correlation: Threshold for VERY_LOW_CLIM_CORRELATION flag.
        max_nrmse: Threshold for HIGH_CLIM_NRMSE flag.
        min_amplitude_ratio: Lower threshold for LOW_AMPLITUDE flag.
        max_amplitude_ratio: Upper threshold for HIGH_AMPLITUDE flag.

    Returns:
        Dictionary mapping year to list of quality flags.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        logger.error("Discharge must have datetime index")
        return {}

    # Build climatology
    try:
        climatology = build_daily_climatology(discharge)
    except ValueError as e:
        logger.warning(f"Cannot build climatology: {e}")
        return {}

    # Get available hydrological years
    valid_data = discharge.dropna()
    if len(valid_data) == 0:
        return {}

    # Determine hydrological years in the data
    if hydro_year_start_month > 1:
        hydro_years = valid_data.index.year.copy()
        hydro_years = hydro_years.where(
            valid_data.index.month < hydro_year_start_month, hydro_years + 1
        )
        years = sorted(set(hydro_years))
    else:
        years = sorted(set(valid_data.index.year))

    # Analyze each year
    flags_by_year: dict[int, list[QualityFlag]] = {}

    for year in years:
        deviation = calculate_year_deviation(
            discharge, year, climatology, hydro_year_start_month
        )

        flags: list[QualityFlag] = []

        # Check correlation
        corr = deviation["correlation"]
        if not np.isnan(corr):
            if corr < critical_correlation:
                flags.append(QualityFlag.VERY_LOW_CLIM_CORRELATION)
            elif corr < min_correlation:
                flags.append(QualityFlag.LOW_CLIM_CORRELATION)

        # Check NRMSE
        nrmse = deviation["nrmse"]
        if not np.isnan(nrmse) and nrmse > max_nrmse:
            flags.append(QualityFlag.HIGH_CLIM_NRMSE)

        # Check amplitude ratio
        amp_ratio = deviation["amplitude_ratio"]
        if not np.isnan(amp_ratio):
            if amp_ratio < min_amplitude_ratio:
                flags.append(QualityFlag.LOW_AMPLITUDE)
            elif amp_ratio > max_amplitude_ratio:
                flags.append(QualityFlag.HIGH_AMPLITUDE)

        if flags:
            flags_by_year[year] = flags

    return flags_by_year


def get_year_climatology_metrics(
    discharge: pd.Series,
    hydro_year_start_month: int = 10,
) -> pd.DataFrame:
    """Get climatology deviation metrics for all years.

    Args:
        discharge: Discharge time series with datetime index.
        hydro_year_start_month: Start month of hydrological year.

    Returns:
        DataFrame with year as index and deviation metrics as columns.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        raise ValueError("Discharge must have datetime index")

    try:
        climatology = build_daily_climatology(discharge)
    except ValueError as e:
        logger.warning(f"Cannot build climatology: {e}")
        return pd.DataFrame()

    # Get hydrological years
    valid_data = discharge.dropna()
    if len(valid_data) == 0:
        return pd.DataFrame()

    if hydro_year_start_month > 1:
        hydro_years = valid_data.index.year.copy()
        hydro_years = hydro_years.where(
            valid_data.index.month < hydro_year_start_month, hydro_years + 1
        )
        years = sorted(set(hydro_years))
    else:
        years = sorted(set(valid_data.index.year))

    # Calculate metrics for each year
    metrics_list = []
    for year in years:
        deviation = calculate_year_deviation(
            discharge, year, climatology, hydro_year_start_month
        )
        deviation["year"] = year
        metrics_list.append(deviation)

    df = pd.DataFrame(metrics_list)
    if not df.empty:
        df = df.set_index("year")

    return df
