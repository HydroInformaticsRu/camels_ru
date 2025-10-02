"""Hydrological analysis package for CAMELS-RU dataset.

This package provides comprehensive hydrological metrics and analysis tools
for discharge time series data, organized into thematic modules.
"""

from .base_flow import BaseFlowSeparation, calculate_bfi
from .flow_duration import FlowDurationCurve, calculate_fdc_metrics
from .flow_extremes import FlowExtremes, calculate_extreme_metrics
from .flow_indices import HydrologicalIndices, calculate_comprehensive_metrics
from .flow_timing import FlowTiming, calculate_timing_metrics
from .flow_variability import FlowVariability, calculate_variability_metrics

__all__ = [
    "BaseFlowSeparation",
    "calculate_bfi",
    "FlowDurationCurve",
    "calculate_fdc_metrics",
    "FlowTiming",
    "calculate_timing_metrics",
    "FlowExtremes",
    "calculate_extreme_metrics",
    "FlowVariability",
    "calculate_variability_metrics",
    "HydrologicalIndices",
    "calculate_comprehensive_metrics",
]
