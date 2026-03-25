"""Meteorological response validation for discharge quality assessment.

This module validates that discharge time series show appropriate response
to meteorological forcing (precipitation events), identifying "dead" years
that show no response to precipitation or snowmelt.
"""

import logging

import numpy as np
import pandas as pd

from .quality_flags import QualityFlag

logger = logging.getLogger(__name__)


def detect_precipitation_events(
    precipitation: pd.Series,
    threshold_mm: float = 5.0,
    min_duration_days: int = 1,
    gap_days: int = 2,
) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    """Find precipitation events in time series.

    Events are identified as periods where precipitation exceeds threshold,
    with nearby events merged if gap is less than gap_days.

    Args:
        precipitation: Precipitation time series (mm/day) with datetime index.
        threshold_mm: Minimum daily precipitation to consider (mm).
        min_duration_days: Minimum event duration.
        gap_days: Maximum gap between events to merge.

    Returns:
        List of tuples (start_date, end_date, total_precipitation_mm).
    """
    if not isinstance(precipitation.index, pd.DatetimeIndex):
        raise ValueError("Precipitation must have datetime index")

    valid_precip = precipitation.dropna()
    if len(valid_precip) == 0:
        return []

    # Find days exceeding threshold
    above_threshold = valid_precip >= threshold_mm

    # Find event boundaries
    events = []
    in_event = False
    event_start = None
    event_total = 0.0
    last_event_end = None

    for date, is_event_day in above_threshold.items():
        if is_event_day:
            if not in_event:
                # Check if we should merge with previous event
                if last_event_end is not None and (date - last_event_end).days <= gap_days and events:
                    # Merge: remove last event and continue from its start
                    prev_start, _, prev_total = events.pop()
                    event_start = prev_start
                    event_total = prev_total + valid_precip.loc[date]
                else:
                    event_start = date
                    event_total = valid_precip.loc[date]
                in_event = True
            else:
                event_total += valid_precip.loc[date]
        else:
            if in_event:
                # End of event
                if event_start is not None:
                    events.append((event_start, date - pd.Timedelta(days=1), event_total))
                    last_event_end = date - pd.Timedelta(days=1)
                in_event = False
                event_start = None
                event_total = 0.0

    # Handle event at end of series
    if in_event and event_start is not None:
        events.append((event_start, valid_precip.index[-1], event_total))

    # Filter by minimum duration
    filtered_events = [
        (start, end, total)
        for start, end, total in events
        if (end - start).days + 1 >= min_duration_days
    ]

    return filtered_events


def calculate_event_response(
    discharge: pd.Series,
    precipitation: pd.Series,
    lag_window: int = 7,
    response_threshold: float = 0.1,
    threshold_mm: float = 5.0,
) -> dict:
    """Calculate discharge response to precipitation events.

    For each precipitation event, checks if discharge responds within
    the lag window.

    Args:
        discharge: Discharge time series (mm/day).
        precipitation: Precipitation time series (mm/day).
        lag_window: Days after event end to check for response.
        response_threshold: Minimum relative discharge increase to count as response.
        threshold_mm: Precipitation threshold for event detection.

    Returns:
        Dictionary with:
        - event_response_rate: Fraction of events with discharge response
        - n_events: Number of precipitation events detected
        - n_responsive: Number of events with response
        - mean_response_ratio: Mean delta_Q / sum(P) for responsive events
    """
    # Detect precipitation events
    events = detect_precipitation_events(precipitation, threshold_mm=threshold_mm)

    if len(events) == 0:
        return {
            "event_response_rate": np.nan,
            "n_events": 0,
            "n_responsive": 0,
            "mean_response_ratio": np.nan,
        }

    # Check discharge response for each event
    n_responsive = 0
    response_ratios = []

    for event_start, event_end, precip_total in events:
        # Get discharge before event (baseline)
        baseline_start = event_start - pd.Timedelta(days=3)
        baseline_end = event_start - pd.Timedelta(days=1)
        baseline_q = discharge.loc[baseline_start:baseline_end].mean()

        # Get discharge during/after event (response window)
        response_start = event_start
        response_end = event_end + pd.Timedelta(days=lag_window)
        response_q = discharge.loc[response_start:response_end]

        if len(response_q) == 0 or np.isnan(baseline_q):
            continue

        # Check for response: peak discharge significantly above baseline
        peak_q = response_q.max()
        if np.isnan(peak_q):
            continue

        # Calculate relative increase
        if baseline_q > 0:
            relative_increase = (peak_q - baseline_q) / baseline_q
        else:
            relative_increase = 1.0 if peak_q > 0 else 0.0

        # Event is responsive if relative increase exceeds threshold
        if relative_increase > response_threshold:
            n_responsive += 1
            # Calculate response ratio (delta_Q / P)
            delta_q = peak_q - baseline_q
            if precip_total > 0:
                response_ratios.append(delta_q / precip_total)

    event_response_rate = n_responsive / len(events) if len(events) > 0 else np.nan
    mean_response_ratio = np.mean(response_ratios) if response_ratios else np.nan

    return {
        "event_response_rate": float(event_response_rate),
        "n_events": len(events),
        "n_responsive": n_responsive,
        "mean_response_ratio": float(mean_response_ratio)
        if not np.isnan(mean_response_ratio)
        else np.nan,
    }


def calculate_pq_cross_correlation(
    precipitation: pd.Series,
    discharge: pd.Series,
    max_lag: int = 14,
    window_days: int = 365,
) -> dict:
    """Calculate cross-correlation between precipitation and discharge.

    Uses rolling windows to compute time-lagged correlation.

    Args:
        precipitation: Precipitation time series (mm/day).
        discharge: Discharge time series (mm/day).
        max_lag: Maximum lag (days) to consider.
        window_days: Window size for rolling correlation.

    Returns:
        Dictionary with:
        - max_cross_correlation: Peak P-Q correlation at any lag
        - optimal_lag_days: Lag at peak correlation
        - correlation_at_lags: Dict of lag -> correlation
    """
    # Align series
    combined = pd.DataFrame({"P": precipitation, "Q": discharge}).dropna()

    if len(combined) < window_days:
        return {
            "max_cross_correlation": np.nan,
            "optimal_lag_days": np.nan,
            "correlation_at_lags": {},
        }

    p_values = combined["P"].values
    q_values = combined["Q"].values

    # Calculate cross-correlation at different lags
    correlations = {}
    for lag in range(max_lag + 1):
        if lag > 0:
            p_lagged = p_values[:-lag]
            q_shifted = q_values[lag:]
        else:
            p_lagged = p_values
            q_shifted = q_values

        if len(p_lagged) < 30:
            continue

        # Calculate Pearson correlation
        corr = np.corrcoef(p_lagged, q_shifted)[0, 1]
        if not np.isnan(corr):
            correlations[lag] = float(corr)

    if not correlations:
        return {
            "max_cross_correlation": np.nan,
            "optimal_lag_days": np.nan,
            "correlation_at_lags": {},
        }

    # Find maximum correlation and optimal lag
    max_corr = max(correlations.values())
    optimal_lag = max(correlations.keys(), key=lambda k: correlations[k])

    return {
        "max_cross_correlation": max_corr,
        "optimal_lag_days": optimal_lag,
        "correlation_at_lags": correlations,
    }


def calculate_flashiness_index(discharge: pd.Series) -> float:
    """Calculate Richards-Baker Flashiness Index.

    FI = sum(|Q_i - Q_{i-1}|) / sum(Q_i)

    Args:
        discharge: Discharge time series.

    Returns:
        Flashiness index (dimensionless).
    """
    valid_data = discharge.dropna()
    if len(valid_data) < 2:
        return np.nan

    daily_changes = np.abs(valid_data.diff().dropna())
    total_flow = valid_data.iloc[1:].sum()

    if total_flow <= 0:
        return np.nan

    return float(daily_changes.sum() / total_flow)


def detect_dead_years(  # noqa: C901
    discharge: pd.Series,
    precipitation: pd.Series,
    hydro_year_start_month: int = 10,
    min_cross_correlation: float = 0.1,  # Lower threshold for snowmelt-dominated catchments
    min_event_response_rate: float = 0.2,  # Lower threshold - snowmelt reduces event response
    min_flashiness: float = 0.01,  # Lower threshold for large catchments
) -> dict[int, list[QualityFlag]]:
    """Detect years with no response to meteorological forcing.

    Args:
        discharge: Discharge time series (mm/day).
        precipitation: Precipitation time series (mm/day).
        hydro_year_start_month: Start month of hydrological year.
        min_cross_correlation: Threshold for VERY_LOW_PQ_CORRELATION flag.
        min_event_response_rate: Threshold for NO_PRECIP_RESPONSE flag.
        min_flashiness: Threshold for LOW_FLASHINESS flag.

    Returns:
        Dictionary mapping year to list of quality flags.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        logger.error("Discharge must have datetime index")
        return {}

    # Get hydrological years
    valid_q = discharge.dropna()
    if len(valid_q) == 0:
        return {}

    if hydro_year_start_month > 1:
        hydro_years = valid_q.index.year.copy()
        hydro_years = hydro_years.where(valid_q.index.month < hydro_year_start_month, hydro_years + 1)
        years = sorted(set(hydro_years))
    else:
        years = sorted(set(valid_q.index.year))

    flags_by_year: dict[int, list[QualityFlag]] = {}

    for year in years:
        # Extract year data
        if hydro_year_start_month > 1:
            start_date = pd.Timestamp(year=year - 1, month=hydro_year_start_month, day=1)
            end_date = pd.Timestamp(year=year, month=hydro_year_start_month, day=1) - pd.Timedelta(
                days=1
            )
        else:
            start_date = pd.Timestamp(year=year, month=1, day=1)
            end_date = pd.Timestamp(year=year, month=12, day=31)

        year_q = discharge.loc[start_date:end_date]
        year_p = precipitation.loc[start_date:end_date]

        if len(year_q.dropna()) < 30 or len(year_p.dropna()) < 30:
            continue

        flags: list[QualityFlag] = []

        # Check cross-correlation
        pq_corr = calculate_pq_cross_correlation(year_p, year_q, max_lag=14)
        max_corr = pq_corr["max_cross_correlation"]
        if not np.isnan(max_corr):
            if max_corr < min_cross_correlation:
                flags.append(QualityFlag.VERY_LOW_PQ_CORRELATION)
            elif max_corr < 0.2:  # Intermediate threshold (lowered for snowmelt catchments)
                flags.append(QualityFlag.LOW_PQ_CORRELATION)

        # Check event response
        event_response = calculate_event_response(year_q, year_p)
        response_rate = event_response["event_response_rate"]
        if not np.isnan(response_rate) and response_rate < min_event_response_rate:
            flags.append(QualityFlag.NO_PRECIP_RESPONSE)

        # Check flashiness
        flashiness = calculate_flashiness_index(year_q)
        if not np.isnan(flashiness) and flashiness < min_flashiness:
            flags.append(QualityFlag.LOW_FLASHINESS)

        if flags:
            flags_by_year[year] = flags

    return flags_by_year


def get_year_meteo_response_metrics(
    discharge: pd.Series,
    precipitation: pd.Series,
    hydro_year_start_month: int = 10,
) -> pd.DataFrame:
    """Get meteorological response metrics for all years.

    Args:
        discharge: Discharge time series (mm/day).
        precipitation: Precipitation time series (mm/day).
        hydro_year_start_month: Start month of hydrological year.

    Returns:
        DataFrame with year as index and response metrics as columns.
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        raise ValueError("Discharge must have datetime index")

    # Get hydrological years
    valid_q = discharge.dropna()
    if len(valid_q) == 0:
        return pd.DataFrame()

    if hydro_year_start_month > 1:
        hydro_years = valid_q.index.year.copy()
        hydro_years = hydro_years.where(valid_q.index.month < hydro_year_start_month, hydro_years + 1)
        years = sorted(set(hydro_years))
    else:
        years = sorted(set(valid_q.index.year))

    metrics_list = []

    for year in years:
        # Extract year data
        if hydro_year_start_month > 1:
            start_date = pd.Timestamp(year=year - 1, month=hydro_year_start_month, day=1)
            end_date = pd.Timestamp(year=year, month=hydro_year_start_month, day=1) - pd.Timedelta(
                days=1
            )
        else:
            start_date = pd.Timestamp(year=year, month=1, day=1)
            end_date = pd.Timestamp(year=year, month=12, day=31)

        year_q = discharge.loc[start_date:end_date]
        year_p = precipitation.loc[start_date:end_date]

        # Calculate metrics
        pq_corr = calculate_pq_cross_correlation(year_p, year_q, max_lag=14)
        event_response = calculate_event_response(year_q, year_p)
        flashiness = calculate_flashiness_index(year_q)

        metrics = {
            "year": year,
            "max_pq_correlation": pq_corr["max_cross_correlation"],
            "optimal_lag_days": pq_corr["optimal_lag_days"],
            "event_response_rate": event_response["event_response_rate"],
            "n_precip_events": event_response["n_events"],
            "n_responsive_events": event_response["n_responsive"],
            "mean_response_ratio": event_response["mean_response_ratio"],
            "flashiness_index": flashiness,
        }
        metrics_list.append(metrics)

    df = pd.DataFrame(metrics_list)
    if not df.empty:
        df = df.set_index("year")

    return df
