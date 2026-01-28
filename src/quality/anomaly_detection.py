"""Statistical anomaly detection for discharge quality assessment.

This module detects sensor malfunctions and suspicious patterns in
discharge time series data.
"""

import logging

import numpy as np
import pandas as pd
from scipy import stats

from .quality_flags import QualityFlag

logger = logging.getLogger(__name__)


def detect_constant_periods(
    discharge: pd.Series,
    min_days: int = 30,
    tolerance: float = 1e-6,
) -> list[tuple[pd.Timestamp, pd.Timestamp, int, float]]:
    """Find periods where discharge is constant (sensor stuck).

    Args:
        discharge: Discharge time series.
        min_days: Minimum consecutive days to flag as constant.
        tolerance: Maximum variation to consider as "constant".

    Returns:
        List of tuples (start_date, end_date, duration_days, constant_value).
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        raise ValueError("Discharge must have datetime index")

    valid_data = discharge.dropna()
    if len(valid_data) < min_days:
        return []

    constant_periods = []
    period_start = None
    period_value = None
    period_length = 0

    prev_value = None
    for date, value in valid_data.items():
        if prev_value is not None:
            is_same = abs(value - prev_value) <= tolerance
        else:
            is_same = False

        if is_same:
            if period_start is None:
                period_start = prev_date
                period_value = prev_value
                period_length = 2
            else:
                period_length += 1
        else:
            # End of constant period
            if period_start is not None and period_length >= min_days:
                constant_periods.append(
                    (period_start, prev_date, period_length, period_value)
                )
            period_start = None
            period_value = None
            period_length = 0

        prev_value = value
        prev_date = date

    # Handle period at end of series
    if period_start is not None and period_length >= min_days:
        constant_periods.append(
            (period_start, valid_data.index[-1], period_length, period_value)
        )

    return constant_periods


def detect_implausible_spikes(
    discharge: pd.Series,
    sigma_threshold: float = 8.0,  # Raised from 5.0 - flood peaks can be extreme
    window_days: int = 30,
) -> list[tuple[pd.Timestamp, float, float]]:
    """Find implausible spikes in discharge (values far from rolling median).

    Args:
        discharge: Discharge time series.
        sigma_threshold: Number of standard deviations from median to flag.
        window_days: Window size for rolling statistics.

    Returns:
        List of tuples (date, value, n_sigma) for each spike.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        raise ValueError("Discharge must have datetime index")

    valid_data = discharge.dropna()
    if len(valid_data) < window_days:
        return []

    # Calculate rolling median and MAD (median absolute deviation)
    rolling_median = valid_data.rolling(window=window_days, center=True, min_periods=10).median()
    rolling_mad = valid_data.rolling(window=window_days, center=True, min_periods=10).apply(
        lambda x: np.median(np.abs(x - np.median(x))), raw=True
    )

    # Convert MAD to standard deviation equivalent (robust)
    # MAD * 1.4826 approximates standard deviation for normal distribution
    rolling_std = rolling_mad * 1.4826

    spikes = []
    for date in valid_data.index:
        if pd.isna(rolling_median.loc[date]) or pd.isna(rolling_std.loc[date]):
            continue

        value = valid_data.loc[date]
        median = rolling_median.loc[date]
        std = rolling_std.loc[date]

        if std > 0:
            n_sigma = abs(value - median) / std
            if n_sigma > sigma_threshold:
                spikes.append((date, float(value), float(n_sigma)))

    return spikes


def compare_annual_variance(
    discharge: pd.Series,
    year: int,
    hydro_year_start_month: int = 10,
    alpha: float = 0.05,
) -> dict:
    """Compare variance of a single year against long-term variance using F-test.

    Args:
        discharge: Full discharge time series.
        year: Hydrological year to evaluate.
        hydro_year_start_month: Start month of hydrological year.
        alpha: Significance level for F-test.

    Returns:
        Dictionary with:
        - f_statistic: F-test statistic
        - p_value: P-value
        - year_variance: Variance of the year
        - longterm_variance: Long-term variance
        - significant_low: True if year variance is significantly lower
        - significant_high: True if year variance is significantly higher
        - variance_ratio: year_variance / longterm_variance
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        raise ValueError("Discharge must have datetime index")

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
    all_data = discharge.dropna()

    # Exclude current year from long-term data
    longterm_data = all_data.loc[~((all_data.index >= start_date) & (all_data.index <= end_date))]

    if len(year_data) < 30 or len(longterm_data) < 365:
        return {
            "f_statistic": np.nan,
            "p_value": np.nan,
            "year_variance": np.nan,
            "longterm_variance": np.nan,
            "significant_low": False,
            "significant_high": False,
            "variance_ratio": np.nan,
        }

    year_var = year_data.var()
    longterm_var = longterm_data.var()

    if longterm_var == 0 or year_var == 0:
        return {
            "f_statistic": np.nan,
            "p_value": np.nan,
            "year_variance": float(year_var),
            "longterm_variance": float(longterm_var),
            "significant_low": year_var == 0 and longterm_var > 0,
            "significant_high": False,
            "variance_ratio": 0.0 if longterm_var > 0 else np.nan,
        }

    # F-test: year_var / longterm_var
    f_stat = year_var / longterm_var
    df1 = len(year_data) - 1
    df2 = len(longterm_data) - 1

    # Two-tailed test
    p_value = 2 * min(
        stats.f.cdf(f_stat, df1, df2),
        1 - stats.f.cdf(f_stat, df1, df2),
    )

    # Determine if significantly different
    significant_low = f_stat < 1 and p_value < alpha
    significant_high = f_stat > 1 and p_value < alpha

    return {
        "f_statistic": float(f_stat),
        "p_value": float(p_value),
        "year_variance": float(year_var),
        "longterm_variance": float(longterm_var),
        "significant_low": significant_low,
        "significant_high": significant_high,
        "variance_ratio": float(f_stat),
    }


def detect_data_quality_issues(
    discharge: pd.Series,
    year: int,
    hydro_year_start_month: int = 10,
) -> list[QualityFlag]:
    """Detect basic data quality issues for a year.

    Args:
        discharge: Discharge time series.
        year: Hydrological year to check.
        hydro_year_start_month: Start month of hydrological year.

    Returns:
        List of quality flags for detected issues.
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

    year_data = discharge.loc[start_date:end_date]
    expected_days = (end_date - start_date).days + 1

    flags = []

    # Check completeness
    valid_count = year_data.notna().sum()
    completeness = valid_count / expected_days

    if completeness < 0.5:
        flags.append(QualityFlag.VERY_LOW_COMPLETENESS)
    elif completeness < 0.8:
        flags.append(QualityFlag.LOW_COMPLETENESS)

    # Check for negative values
    valid_data = year_data.dropna()
    if len(valid_data) > 0:
        if (valid_data < 0).any():
            flags.append(QualityFlag.NEGATIVE_VALUES)

        # Check for dominant zero flow
        zero_fraction = (valid_data == 0).sum() / len(valid_data)
        if zero_fraction > 0.5:
            flags.append(QualityFlag.ZERO_FLOW_DOMINANT)

    return flags


def detect_anomalies_all_years(
    discharge: pd.Series,
    hydro_year_start_month: int = 10,
    constant_min_days: int = 30,
    spike_sigma_threshold: float = 8.0,  # Raised - flood peaks can be extreme
    variance_alpha: float = 0.01,  # Stricter - only flag extreme variance anomalies
    check_variance: bool = False,  # Disabled by default - variance varies naturally
) -> dict[int, list[QualityFlag]]:
    """Detect statistical anomalies for all years in the time series.

    Args:
        discharge: Discharge time series.
        hydro_year_start_month: Start month of hydrological year.
        constant_min_days: Minimum days for constant value detection.
        spike_sigma_threshold: Sigma threshold for spike detection.
        variance_alpha: Alpha level for variance F-test.

    Returns:
        Dictionary mapping year to list of quality flags.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        logger.error("Discharge must have datetime index")
        return {}

    # Get hydrological years
    valid_data = discharge.dropna()
    if len(valid_data) == 0:
        return {}

    if hydro_year_start_month > 1:
        hydro_years = valid_data.index.year.copy()
        hydro_years = hydro_years.where(
            valid_data.index.month < hydro_year_start_month, hydro_years + 1
        )
        years = sorted(set(hydro_years))
    else:
        years = sorted(set(valid_data.index.year))

    # Detect constant periods (across all data)
    constant_periods = detect_constant_periods(discharge, min_days=constant_min_days)

    # Detect spikes (across all data)
    spikes = detect_implausible_spikes(discharge, sigma_threshold=spike_sigma_threshold)

    # Map constant periods and spikes to years
    flags_by_year: dict[int, list[QualityFlag]] = {year: [] for year in years}

    for start, end, duration, value in constant_periods:
        # Determine which year(s) this affects
        for year in years:
            if hydro_year_start_month > 1:
                year_start = pd.Timestamp(year=year - 1, month=hydro_year_start_month, day=1)
                year_end = pd.Timestamp(year=year, month=hydro_year_start_month, day=1) - pd.Timedelta(
                    days=1
                )
            else:
                year_start = pd.Timestamp(year=year, month=1, day=1)
                year_end = pd.Timestamp(year=year, month=12, day=31)

            # Check if constant period overlaps with year
            if start <= year_end and end >= year_start:
                if QualityFlag.CONSTANT_VALUE not in flags_by_year[year]:
                    flags_by_year[year].append(QualityFlag.CONSTANT_VALUE)

    for spike_date, value, n_sigma in spikes:
        # Determine which year this spike belongs to
        for year in years:
            if hydro_year_start_month > 1:
                year_start = pd.Timestamp(year=year - 1, month=hydro_year_start_month, day=1)
                year_end = pd.Timestamp(year=year, month=hydro_year_start_month, day=1) - pd.Timedelta(
                    days=1
                )
            else:
                year_start = pd.Timestamp(year=year, month=1, day=1)
                year_end = pd.Timestamp(year=year, month=12, day=31)

            if year_start <= spike_date <= year_end:
                if QualityFlag.IMPLAUSIBLE_SPIKE not in flags_by_year[year]:
                    flags_by_year[year].append(QualityFlag.IMPLAUSIBLE_SPIKE)
                break

    # Check variance for each year (optional - disabled by default)
    for year in years:
        if check_variance:
            variance_result = compare_annual_variance(
                discharge, year, hydro_year_start_month, alpha=variance_alpha
            )

            if variance_result["significant_low"]:
                flags_by_year[year].append(QualityFlag.ABNORMAL_LOW_VARIANCE)
            elif variance_result["significant_high"]:
                flags_by_year[year].append(QualityFlag.ABNORMAL_HIGH_VARIANCE)

        # Also check data quality issues
        data_flags = detect_data_quality_issues(discharge, year, hydro_year_start_month)
        for flag in data_flags:
            if flag not in flags_by_year[year]:
                flags_by_year[year].append(flag)

    # Remove years with no flags
    flags_by_year = {year: flags for year, flags in flags_by_year.items() if flags}

    return flags_by_year


def get_year_anomaly_metrics(
    discharge: pd.Series,
    hydro_year_start_month: int = 10,
) -> pd.DataFrame:
    """Get anomaly detection metrics for all years.

    Args:
        discharge: Discharge time series.
        hydro_year_start_month: Start month of hydrological year.

    Returns:
        DataFrame with year as index and anomaly metrics as columns.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        raise ValueError("Discharge must have datetime index")

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

    # Detect constant periods and spikes once
    constant_periods = detect_constant_periods(discharge)
    spikes = detect_implausible_spikes(discharge)

    metrics_list = []

    for year in years:
        # Year boundaries
        if hydro_year_start_month > 1:
            year_start = pd.Timestamp(year=year - 1, month=hydro_year_start_month, day=1)
            year_end = pd.Timestamp(year=year, month=hydro_year_start_month, day=1) - pd.Timedelta(
                days=1
            )
        else:
            year_start = pd.Timestamp(year=year, month=1, day=1)
            year_end = pd.Timestamp(year=year, month=12, day=31)

        year_data = discharge.loc[year_start:year_end]
        expected_days = (year_end - year_start).days + 1

        # Count constant days in this year
        constant_days = 0
        for start, end, duration, value in constant_periods:
            if start <= year_end and end >= year_start:
                overlap_start = max(start, year_start)
                overlap_end = min(end, year_end)
                constant_days += (overlap_end - overlap_start).days + 1

        # Count spikes in this year
        n_spikes = sum(1 for d, v, s in spikes if year_start <= d <= year_end)

        # Variance comparison
        variance_result = compare_annual_variance(discharge, year, hydro_year_start_month)

        # Completeness and data quality
        valid_count = year_data.notna().sum()
        completeness = valid_count / expected_days

        valid_year_data = year_data.dropna()
        n_negative = (valid_year_data < 0).sum() if len(valid_year_data) > 0 else 0
        n_zero = (valid_year_data == 0).sum() if len(valid_year_data) > 0 else 0
        zero_fraction = n_zero / len(valid_year_data) if len(valid_year_data) > 0 else np.nan

        metrics = {
            "year": year,
            "constant_days": constant_days,
            "constant_fraction": constant_days / expected_days,
            "n_spikes": n_spikes,
            "variance_ratio": variance_result["variance_ratio"],
            "variance_p_value": variance_result["p_value"],
            "variance_significant_low": variance_result["significant_low"],
            "variance_significant_high": variance_result["significant_high"],
            "completeness": completeness,
            "n_negative_values": n_negative,
            "zero_flow_fraction": zero_fraction,
        }
        metrics_list.append(metrics)

    df = pd.DataFrame(metrics_list)
    if not df.empty:
        df = df.set_index("year")

    return df
