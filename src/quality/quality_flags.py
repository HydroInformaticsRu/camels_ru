"""Quality flag definitions for discharge assessment.

This module defines quality flags used to identify issues in discharge
time series data at the year level.
"""

from enum import Enum, auto


class FlagSeverity(Enum):
    """Severity levels for quality flags."""

    MINOR = auto()  # Does not alone disqualify data
    MAJOR = auto()  # Significant concern, may reduce grade
    CRITICAL = auto()  # Disqualifies data (grade F)


class QualityFlag(Enum):
    """Quality flags for discharge time series assessment.

    Each flag indicates a specific type of data quality issue.
    Flags are used to determine per-year quality grades.
    """

    # Climatology-related flags
    LOW_CLIM_CORRELATION = "low_clim_correlation"  # correlation < 0.5
    VERY_LOW_CLIM_CORRELATION = "very_low_clim_correlation"  # correlation < 0.2
    HIGH_CLIM_NRMSE = "high_clim_nrmse"  # nrmse > 2.0
    LOW_AMPLITUDE = "low_amplitude"  # amplitude_ratio < 0.3
    HIGH_AMPLITUDE = "high_amplitude"  # amplitude_ratio > 3.0
    NO_SEASONAL_SIGNAL = "no_seasonal_signal"  # flat hydrograph, no flood peak

    # Meteorological response flags
    NO_PRECIP_RESPONSE = "no_precip_response"  # event_response_rate < 0.3
    VERY_LOW_PQ_CORRELATION = "very_low_pq_correlation"  # max_cross_corr < 0.2
    LOW_PQ_CORRELATION = "low_pq_correlation"  # max_cross_corr < 0.4
    LOW_FLASHINESS = "low_flashiness"  # flashiness_index < 0.02
    NO_EFFECTIVE_WATER_RESPONSE = "no_effective_water_response"
    VERY_LOW_EFFECTIVE_WATER_CORRELATION = "very_low_effective_water_correlation"
    LOW_EFFECTIVE_WATER_CORRELATION = "low_effective_water_correlation"

    # Statistical anomaly flags
    CONSTANT_VALUE = "constant_value"  # Sensor stuck (>30 days constant)
    IMPLAUSIBLE_SPIKE = "implausible_spike"  # Values > 8 MAD-sigma from rolling median
    ABNORMAL_LOW_VARIANCE = "abnormal_low_variance"  # F-test significant low
    ABNORMAL_HIGH_VARIANCE = "abnormal_high_variance"  # F-test significant high

    # Data completeness flags
    LOW_COMPLETENESS = "low_completeness"  # < 80% data
    VERY_LOW_COMPLETENESS = "very_low_completeness"  # < 50% data

    # Data quality flags
    NEGATIVE_VALUES = "negative_values"  # Presence of negative discharge
    ZERO_FLOW_DOMINANT = "zero_flow_dominant"  # > 50% zero values


# Severity mapping for each flag
_FLAG_SEVERITY: dict[QualityFlag, FlagSeverity] = {
    # Climatology flags
    QualityFlag.LOW_CLIM_CORRELATION: FlagSeverity.MINOR,  # Downgraded - less meaningful for nival
    QualityFlag.VERY_LOW_CLIM_CORRELATION: FlagSeverity.MAJOR,  # Downgraded from CRITICAL
    QualityFlag.HIGH_CLIM_NRMSE: FlagSeverity.MINOR,  # Downgraded - amplitude variation is natural
    QualityFlag.LOW_AMPLITUDE: FlagSeverity.MINOR,  # Downgraded - small years can be valid
    QualityFlag.HIGH_AMPLITUDE: FlagSeverity.MINOR,  # Downgraded - large years can be valid
    QualityFlag.NO_SEASONAL_SIGNAL: FlagSeverity.CRITICAL,  # Primary indicator - flat = bad
    # Meteo response flags
    # Note: P-Q correlation is less meaningful for snowmelt-dominated catchments
    QualityFlag.NO_PRECIP_RESPONSE: FlagSeverity.MINOR,  # Minor - snowmelt masks direct response
    QualityFlag.VERY_LOW_PQ_CORRELATION: FlagSeverity.MINOR,  # Minor - expected for nival catchments
    QualityFlag.LOW_PQ_CORRELATION: FlagSeverity.MINOR,  # Minor - expected in continental climates
    QualityFlag.LOW_FLASHINESS: FlagSeverity.MINOR,  # Minor - large catchments have low flashiness
    # Temperature-aware rain + snowmelt response flags. Still minor because
    # the degree-day snowpack proxy is a screening heuristic, not a calibrated
    # process model.
    QualityFlag.NO_EFFECTIVE_WATER_RESPONSE: FlagSeverity.MINOR,
    QualityFlag.VERY_LOW_EFFECTIVE_WATER_CORRELATION: FlagSeverity.MINOR,
    QualityFlag.LOW_EFFECTIVE_WATER_CORRELATION: FlagSeverity.MINOR,
    # Anomaly flags
    QualityFlag.CONSTANT_VALUE: FlagSeverity.MAJOR,  # Downgraded - short constant periods may be natural
    QualityFlag.IMPLAUSIBLE_SPIKE: FlagSeverity.MINOR,  # Downgraded - spikes may be real flood events
    QualityFlag.ABNORMAL_LOW_VARIANCE: FlagSeverity.MINOR,  # Minor - naturally low outside flood season
    QualityFlag.ABNORMAL_HIGH_VARIANCE: FlagSeverity.MINOR,  # high variance during flood is natural
    # Completeness flags
    QualityFlag.LOW_COMPLETENESS: FlagSeverity.MAJOR,
    QualityFlag.VERY_LOW_COMPLETENESS: FlagSeverity.CRITICAL,
    # Data quality flags
    QualityFlag.NEGATIVE_VALUES: FlagSeverity.CRITICAL,
    QualityFlag.ZERO_FLOW_DOMINANT: FlagSeverity.MINOR,
}


def get_flag_severity(flag: QualityFlag) -> FlagSeverity:
    """Get the severity level of a quality flag.

    Args:
        flag: The quality flag to check.

    Returns:
        The severity level of the flag.
    """
    return _FLAG_SEVERITY.get(flag, FlagSeverity.MINOR)


def count_flags_by_severity(
    flags: list[QualityFlag],
) -> dict[FlagSeverity, int]:
    """Count flags by their severity level.

    Args:
        flags: List of quality flags.

    Returns:
        Dictionary mapping severity to count.
    """
    counts = dict.fromkeys(FlagSeverity, 0)
    for flag in flags:
        severity = get_flag_severity(flag)
        counts[severity] += 1
    return counts


def has_critical_flag(flags: list[QualityFlag]) -> bool:
    """Check if any flag has critical severity.

    Args:
        flags: List of quality flags.

    Returns:
        True if any flag is critical.
    """
    return any(get_flag_severity(f) == FlagSeverity.CRITICAL for f in flags)
