"""Quality grading for discharge time series assessment.

This module assigns quality grades (A-F) to individual years and
generates gauge-level quality summaries.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any

import numpy as np
import pandas as pd

from .anomaly_detection import detect_anomalies_all_years
from .climatology import (
    build_daily_climatology,
    calculate_year_deviation,
    detect_climatology_anomalies,
    detect_flat_years,
    detect_seasonal_signal,
)
from .meteo_response import calculate_flashiness_index, detect_dead_years
from .quality_flags import FlagSeverity, QualityFlag, get_flag_severity

logger = logging.getLogger(__name__)


class QualityGrade(Enum):
    """Quality grades for discharge data."""

    A = "A"  # Excellent
    B = "B"  # Good
    C = "C"  # Usable
    D = "D"  # Poor
    F = "F"  # Fail


@dataclass
class YearQualityResult:
    """Quality assessment result for a single year."""

    year: int
    grade: QualityGrade
    flags: list[QualityFlag] = field(default_factory=list)
    clim_correlation: float = np.nan
    clim_nrmse: float = np.nan
    amplitude_ratio: float = np.nan
    event_response_rate: float = np.nan
    max_pq_correlation: float = np.nan
    flashiness_index: float = np.nan
    data_completeness: float = np.nan
    variance_ratio: float = np.nan
    peak_ratio: float = np.nan  # max/mean - key metric for snowmelt catchments

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DataFrame creation."""
        return {
            "year": self.year,
            "grade": self.grade.value,
            "peak_ratio": self.peak_ratio,
            "clim_correlation": self.clim_correlation,
            "clim_nrmse": self.clim_nrmse,
            "amplitude_ratio": self.amplitude_ratio,
            "event_response_rate": self.event_response_rate,
            "max_pq_correlation": self.max_pq_correlation,
            "flashiness_index": self.flashiness_index,
            "data_completeness": self.data_completeness,
            "variance_ratio": self.variance_ratio,
            "flag_codes": ",".join(f.value for f in self.flags),
            "n_flags": len(self.flags),
            "n_critical_flags": sum(
                1 for f in self.flags if get_flag_severity(f) == FlagSeverity.CRITICAL
            ),
            "n_major_flags": sum(1 for f in self.flags if get_flag_severity(f) == FlagSeverity.MAJOR),
        }


@dataclass
class GaugeQualitySummary:
    """Quality summary for an entire gauge."""

    gauge_id: str
    overall_grade: QualityGrade
    n_years_total: int
    n_years_usable: int  # Grade >= C
    n_years_excellent: int  # Grade A
    n_years_good: int  # Grade B
    n_years_poor: int  # Grade D
    n_years_fail: int  # Grade F
    excluded_years: list[int] = field(default_factory=list)
    recommendation: str = "Include"
    new_tier: str = "decent"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DataFrame creation."""
        return {
            "gauge_id": self.gauge_id,
            "overall_grade": self.overall_grade.value,
            "n_years_total": self.n_years_total,
            "n_years_usable": self.n_years_usable,
            "n_years_excellent": self.n_years_excellent,
            "n_years_good": self.n_years_good,
            "n_years_poor": self.n_years_poor,
            "n_years_fail": self.n_years_fail,
            "excluded_years": ",".join(str(y) for y in self.excluded_years),
            "usable_fraction": self.n_years_usable / self.n_years_total
            if self.n_years_total > 0
            else 0.0,
            "recommendation": self.recommendation,
            "new_tier": self.new_tier,
        }


class YearQualityGrader:
    """Assigns quality grades to individual years based on metrics and flags."""

    def __init__(
        self,
        # Grade A thresholds (Excellent)
        min_corr_a: float = 0.8,
        min_response_a: float = 0.7,
        min_completeness_a: float = 0.95,
        # Grade B thresholds (Good)
        min_corr_b: float = 0.6,
        min_response_b: float = 0.5,
        min_completeness_b: float = 0.85,
        # Grade C thresholds (Usable)
        min_corr_c: float = 0.4,
        min_completeness_c: float = 0.7,
        # Grade F threshold (Fail)
        max_corr_f: float = 0.2,
    ):
        """Initialize grader with thresholds.

        Args:
            min_corr_a: Minimum climatology correlation for grade A.
            min_response_a: Minimum event response rate for grade A.
            min_completeness_a: Minimum data completeness for grade A.
            min_corr_b: Minimum climatology correlation for grade B.
            min_response_b: Minimum event response rate for grade B.
            min_completeness_b: Minimum data completeness for grade B.
            min_corr_c: Minimum climatology correlation for grade C.
            min_completeness_c: Minimum data completeness for grade C.
            max_corr_f: Maximum climatology correlation for automatic grade F.
        """
        self.min_corr_a = min_corr_a
        self.min_response_a = min_response_a
        self.min_completeness_a = min_completeness_a
        self.min_corr_b = min_corr_b
        self.min_response_b = min_response_b
        self.min_completeness_b = min_completeness_b
        self.min_corr_c = min_corr_c
        self.min_completeness_c = min_completeness_c
        self.max_corr_f = max_corr_f

    def grade_year(
        self,
        flags: list[QualityFlag],
        clim_correlation: float,
        event_response_rate: float,
        data_completeness: float,
    ) -> QualityGrade:
        """Assign a quality grade to a year based on flags and metrics.

        Grade assignment rules (simplified, flag-focused):
        - F: Any critical flag (NO_SEASONAL_SIGNAL, VERY_LOW_COMPLETENESS, etc.)
        - D: Multiple major flags, or very low completeness
        - C: 1 major flag or 3+ minor flags
        - B: 1-2 minor flags
        - A: No flags and good completeness

        Climatology correlation is downweighted since amplitude variation
        is natural in snowmelt-dominated catchments.

        Args:
            flags: List of quality flags for the year.
            clim_correlation: Correlation with climatology (secondary metric).
            event_response_rate: P-Q event response rate (secondary metric).
            data_completeness: Fraction of valid data.

        Returns:
            Quality grade (A-F).
        """
        # Count flags by severity
        n_critical = sum(1 for f in flags if get_flag_severity(f) == FlagSeverity.CRITICAL)
        n_major = sum(1 for f in flags if get_flag_severity(f) == FlagSeverity.MAJOR)
        n_minor = sum(1 for f in flags if get_flag_severity(f) == FlagSeverity.MINOR)

        # Grade F: Any critical flag (primary disqualifier)
        if n_critical > 0:
            return QualityGrade.F

        # Grade D: Multiple major flags or very poor completeness
        if n_major >= 2:
            return QualityGrade.D
        if data_completeness < self.min_completeness_c:
            return QualityGrade.D

        # Grade C: 1 major flag or 5+ minor flags
        if n_major >= 1 or n_minor >= 5:
            return QualityGrade.C
        if data_completeness < self.min_completeness_b:
            return QualityGrade.C

        # Grade B: 3-4 minor flags
        if n_minor >= 3:
            return QualityGrade.B
        if data_completeness < self.min_completeness_a:
            return QualityGrade.B

        # Grade A: 0-2 minor flags and good completeness
        return QualityGrade.A


def assess_gauge_quality(
    discharge: pd.Series,
    precipitation: pd.Series | None = None,
    gauge_id: str = "unknown",
    hydro_year_start_month: int = 10,
    min_years: int = 3,
) -> tuple[list[YearQualityResult], GaugeQualitySummary]:
    """Perform comprehensive quality assessment for a gauge.

    Args:
        discharge: Discharge time series (mm/day) with datetime index.
        precipitation: Optional precipitation time series (mm/day).
        gauge_id: Gauge identifier for reporting.
        hydro_year_start_month: Start month of hydrological year.
        min_years: Minimum years required for assessment.

    Returns:
        Tuple of (list of YearQualityResult, GaugeQualitySummary).
    """
    if not isinstance(discharge.index, pd.DatetimeIndex):
        raise ValueError("Discharge must have datetime index")

    # Get available hydrological years
    valid_data = discharge.dropna()
    if len(valid_data) == 0:
        logger.warning(f"Gauge {gauge_id}: No valid discharge data")
        return [], GaugeQualitySummary(
            gauge_id=gauge_id,
            overall_grade=QualityGrade.F,
            n_years_total=0,
            n_years_usable=0,
            n_years_excellent=0,
            n_years_good=0,
            n_years_poor=0,
            n_years_fail=0,
            recommendation="Exclude",
            new_tier="poor",
        )

    # Determine hydrological years
    if hydro_year_start_month > 1:
        hydro_years = valid_data.index.year.copy()
        hydro_years = hydro_years.where(valid_data.index.month < hydro_year_start_month, hydro_years + 1)
        years = sorted(set(hydro_years))

        # Exclude partial edge hydro-years that cannot be complete due to the
        # data window. E.g., if data starts Jan 2008 and hydro-year starts Oct,
        # then HY 2008 (Oct 2007–Sep 2008) is missing Oct-Dec 2007 by
        # definition — not a quality issue. Similarly, the last HY may extend
        # beyond the data end date.
        data_start = valid_data.index.min()
        data_end = valid_data.index.max()
        first_complete_hy_start = pd.Timestamp(
            year=data_start.year if data_start.month < hydro_year_start_month else data_start.year + 1,
            month=hydro_year_start_month,
            day=1,
        )
        # First complete HY is the one starting at first_complete_hy_start
        first_complete_hy = first_complete_hy_start.year + 1  # HY labeled by end year
        # Last complete HY ends at month before hydro_year_start_month
        last_complete_hy_end_year = (
            data_end.year if data_end.month >= hydro_year_start_month - 1 else data_end.year - 1
        )
        last_complete_hy = last_complete_hy_end_year  # HY that ends in Sep of this year

        years = [y for y in years if first_complete_hy <= y <= last_complete_hy]
    else:
        years = sorted(set(valid_data.index.year))

    if len(years) < min_years:
        logger.warning(f"Gauge {gauge_id}: Insufficient years ({len(years)} < {min_years})")
        return [], GaugeQualitySummary(
            gauge_id=gauge_id,
            overall_grade=QualityGrade.F,
            n_years_total=len(years),
            n_years_usable=0,
            n_years_excellent=0,
            n_years_good=0,
            n_years_poor=0,
            n_years_fail=len(years),
            excluded_years=years,
            recommendation="Exclude",
            new_tier="poor",
        )

    # Build climatology
    try:
        climatology = build_daily_climatology(discharge)
    except ValueError as e:
        logger.warning(f"Gauge {gauge_id}: Cannot build climatology: {e}")
        climatology = None

    # Collect all flags
    # Primary metric: detect flat years (no seasonal signal) - most important for nival catchments
    flat_year_flags = detect_flat_years(discharge, hydro_year_start_month)

    # Secondary metrics: climatology correlation (less strict thresholds)
    clim_flags = detect_climatology_anomalies(
        discharge,
        hydro_year_start_month,
        min_correlation=0.3,  # Lowered - less important than peak detection
        critical_correlation=0.1,  # Lowered
        max_nrmse=5.0,  # Raised - amplitude variation is natural
        min_amplitude_ratio=0.1,  # Lowered - small years can be valid
        max_amplitude_ratio=5.0,  # Raised - large years can be valid
    )

    if precipitation is not None:
        meteo_flags = detect_dead_years(discharge, precipitation, hydro_year_start_month)
    else:
        meteo_flags = {}

    anomaly_flags = detect_anomalies_all_years(discharge, hydro_year_start_month)

    # Merge flags by year
    all_flags: dict[int, list[QualityFlag]] = {}
    for year in years:
        flags = []
        # Primary: flat years (no seasonal signal)
        flags.extend(flat_year_flags.get(year, []))
        # Secondary: climatology correlation
        flags.extend(clim_flags.get(year, []))
        # Tertiary: meteo response
        flags.extend(meteo_flags.get(year, []))
        # Anomaly detection
        flags.extend(anomaly_flags.get(year, []))
        # Remove duplicates while preserving order
        seen = set()
        unique_flags = []
        for f in flags:
            if f not in seen:
                seen.add(f)
                unique_flags.append(f)
        all_flags[year] = unique_flags

    # Grade each year
    grader = YearQualityGrader()
    year_results: list[YearQualityResult] = []

    for year in years:
        # Get metrics
        if climatology is not None:
            deviation = calculate_year_deviation(discharge, year, climatology, hydro_year_start_month)
            clim_corr = deviation["correlation"]
            clim_nrmse = deviation["nrmse"]
            amplitude_ratio = deviation["amplitude_ratio"]
            completeness = deviation["completeness"]
        else:
            clim_corr = np.nan
            clim_nrmse = np.nan
            amplitude_ratio = np.nan
            # Calculate completeness manually
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
            completeness = year_data.notna().sum() / expected_days

        # Calculate meteo response metrics for year
        event_response_rate = np.nan
        max_pq_corr = np.nan
        if precipitation is not None:
            from .meteo_response import calculate_event_response, calculate_pq_cross_correlation

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

            if len(year_q.dropna()) >= 30 and len(year_p.dropna()) >= 30:
                response = calculate_event_response(year_q, year_p)
                event_response_rate = response["event_response_rate"]

                pq_corr = calculate_pq_cross_correlation(year_p, year_q)
                max_pq_corr = pq_corr["max_cross_correlation"]

        # Calculate flashiness
        if hydro_year_start_month > 1:
            start_date = pd.Timestamp(year=year - 1, month=hydro_year_start_month, day=1)
            end_date = pd.Timestamp(year=year, month=hydro_year_start_month, day=1) - pd.Timedelta(
                days=1
            )
        else:
            start_date = pd.Timestamp(year=year, month=1, day=1)
            end_date = pd.Timestamp(year=year, month=12, day=31)
        year_q = discharge.loc[start_date:end_date]
        flashiness = calculate_flashiness_index(year_q)

        # Calculate variance ratio
        from .anomaly_detection import compare_annual_variance

        variance_result = compare_annual_variance(discharge, year, hydro_year_start_month)
        variance_ratio = variance_result["variance_ratio"]

        # Calculate peak ratio (key metric for snowmelt catchments)
        signal_info = detect_seasonal_signal(discharge, year, hydro_year_start_month)
        peak_ratio = signal_info["peak_ratio"]

        # Assign grade
        flags = all_flags.get(year, [])
        grade = grader.grade_year(flags, clim_corr, event_response_rate, completeness)

        result = YearQualityResult(
            year=year,
            grade=grade,
            flags=flags,
            clim_correlation=clim_corr,
            clim_nrmse=clim_nrmse,
            amplitude_ratio=amplitude_ratio,
            event_response_rate=event_response_rate,
            max_pq_correlation=max_pq_corr,
            flashiness_index=flashiness,
            data_completeness=completeness,
            variance_ratio=variance_ratio,
            peak_ratio=peak_ratio,
        )
        year_results.append(result)

    # Create gauge summary
    summary = get_gauge_summary(gauge_id, year_results)

    return year_results, summary


def get_gauge_summary(
    gauge_id: str,
    year_results: list[YearQualityResult],
) -> GaugeQualitySummary:
    """Create gauge-level summary from year results.

    Args:
        gauge_id: Gauge identifier.
        year_results: List of year quality results.

    Returns:
        Gauge quality summary.
    """
    if not year_results:
        return GaugeQualitySummary(
            gauge_id=gauge_id,
            overall_grade=QualityGrade.F,
            n_years_total=0,
            n_years_usable=0,
            n_years_excellent=0,
            n_years_good=0,
            n_years_poor=0,
            n_years_fail=0,
            recommendation="Exclude",
            new_tier="poor",
        )

    # Count grades
    grade_counts = dict.fromkeys(QualityGrade, 0)
    for result in year_results:
        grade_counts[result.grade] += 1

    n_years_total = len(year_results)
    n_excellent = grade_counts[QualityGrade.A]
    n_good = grade_counts[QualityGrade.B]
    n_usable = grade_counts[QualityGrade.C]
    n_poor = grade_counts[QualityGrade.D]
    n_fail = grade_counts[QualityGrade.F]

    # Years with grade >= C are usable
    n_years_usable = n_excellent + n_good + n_usable

    # Excluded years (grade F)
    excluded_years = [r.year for r in year_results if r.grade == QualityGrade.F]

    # Determine overall grade
    # Grade A is STRICT: every single year must be A. One bad year → gauge
    # drops. This ensures "Grade A" means "use without checking individual
    # years" — critical for modeling where a D/F year in the validation
    # window silently corrupts metrics.
    # Grades B-D use mode-based logic (existing behavior).
    all_grades = [r.grade for r in year_results]
    usable_grades = [g for g in all_grades if g != QualityGrade.F]

    if not usable_grades:
        overall_grade = QualityGrade.F
    elif all(g == QualityGrade.A for g in all_grades):
        # Strict Grade A: every year must be A (no F years either)
        overall_grade = QualityGrade.A
    else:
        # For B-D: mode of non-F grades (existing logic)
        grade_freq: dict[QualityGrade, int] = {}
        for g in usable_grades:
            grade_freq[g] = grade_freq.get(g, 0) + 1
        overall_grade = max(grade_freq.keys(), key=lambda g: grade_freq[g])
        # Cannot be A (handled above), so cap at B minimum
        if overall_grade == QualityGrade.A:
            overall_grade = QualityGrade.B

    # Cap overall grade based on record coverage
    # A gauge with few usable years shouldn't get top grades regardless
    # of how clean those few years are.
    usable_fraction = n_years_usable / n_years_total if n_years_total > 0 else 0
    fail_fraction = n_fail / n_years_total if n_years_total > 0 else 0

    if usable_fraction < 0.5:
        # Less than half usable → cap at D
        overall_grade = max(overall_grade, QualityGrade.D, key=lambda g: list(QualityGrade).index(g))
    elif usable_fraction < 0.7:
        # 50-70% usable → cap at C
        overall_grade = max(overall_grade, QualityGrade.C, key=lambda g: list(QualityGrade).index(g))
    elif fail_fraction > 0.3:
        # More than 30% F years → cap at B
        overall_grade = max(overall_grade, QualityGrade.B, key=lambda g: list(QualityGrade).index(g))

    # Determine recommendation and tier
    if overall_grade in [QualityGrade.A, QualityGrade.B] and usable_fraction >= 0.8:
        recommendation = "Include"
        new_tier = "decent"
    elif overall_grade == QualityGrade.C or usable_fraction >= 0.5:
        recommendation = "Use with caution"
        new_tier = "decent"
    else:
        recommendation = "Exclude"
        new_tier = "poor"

    return GaugeQualitySummary(
        gauge_id=gauge_id,
        overall_grade=overall_grade,
        n_years_total=n_years_total,
        n_years_usable=n_years_usable,
        n_years_excellent=n_excellent,
        n_years_good=n_good,
        n_years_poor=n_poor,
        n_years_fail=n_fail,
        excluded_years=excluded_years,
        recommendation=recommendation,
        new_tier=new_tier,
    )


def results_to_dataframe(
    gauge_id: str,
    year_results: list[YearQualityResult],
) -> pd.DataFrame:
    """Convert year results to DataFrame.

    Args:
        gauge_id: Gauge identifier.
        year_results: List of year quality results.

    Returns:
        DataFrame with one row per year.
    """
    if not year_results:
        return pd.DataFrame()

    records = []
    for result in year_results:
        record = result.to_dict()
        record["gauge_id"] = gauge_id
        records.append(record)

    df = pd.DataFrame(records)
    # Reorder columns
    cols = ["gauge_id", "year", "grade"] + [
        c for c in df.columns if c not in ["gauge_id", "year", "grade"]
    ]
    return df[cols]
