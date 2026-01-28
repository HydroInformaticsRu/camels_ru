"""Discharge quality assessment module for CAMELS-RU dataset.

This module provides automated quality assessment for discharge time series,
evaluating data at the year level using statistical analysis against
climatological patterns and meteorological forcing.

Main components:
- climatology: Daily pattern comparison and deviation analysis
- meteo_response: Precipitation-discharge response validation
- anomaly_detection: Statistical outlier and sensor malfunction detection
- quality_grader: Grade assignment (A-F) per year and gauge summary
- quality_flags: Flag definitions and severity levels
"""

from .quality_flags import QualityFlag, FlagSeverity, get_flag_severity
from .climatology import (
    build_daily_climatology,
    calculate_year_deviation,
    detect_climatology_anomalies,
    calculate_peak_ratio,
    detect_seasonal_signal,
    detect_flat_years,
)
from .meteo_response import (
    detect_precipitation_events,
    calculate_event_response,
    calculate_pq_cross_correlation,
    detect_dead_years,
)
from .anomaly_detection import (
    detect_constant_periods,
    detect_implausible_spikes,
    compare_annual_variance,
)
from .quality_grader import (
    QualityGrade,
    YearQualityResult,
    GaugeQualitySummary,
    YearQualityGrader,
    assess_gauge_quality,
    get_gauge_summary,
    results_to_dataframe,
)
from .data_loader import (
    GradedDischargeLoader,
    load_graded_discharge,
)

__all__ = [
    # Flags
    "QualityFlag",
    "FlagSeverity",
    "get_flag_severity",
    # Climatology
    "build_daily_climatology",
    "calculate_year_deviation",
    "detect_climatology_anomalies",
    # Meteo response
    "detect_precipitation_events",
    "calculate_event_response",
    "calculate_pq_cross_correlation",
    "detect_dead_years",
    # Anomaly detection
    "detect_constant_periods",
    "detect_implausible_spikes",
    "compare_annual_variance",
    # Quality grading
    "QualityGrade",
    "YearQualityResult",
    "GaugeQualitySummary",
    "YearQualityGrader",
    "assess_gauge_quality",
    "get_gauge_summary",
    "results_to_dataframe",
    # Data loader
    "GradedDischargeLoader",
    "load_graded_discharge",
]
