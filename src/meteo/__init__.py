"""Meteorological analysis package for CAMELS-RU dataset.

This package provides comprehensive meteorological analysis tools including:
- Climate indices and extreme events
- Temperature and precipitation analysis
- Evapotranspiration calculations
- Drought indices
- Seasonal and annual statistics
"""

# Import only the main functions to avoid circular imports
try:
    from .temperature import calculate_temperature_metrics
except ImportError:
    calculate_temperature_metrics = None

try:
    from .climate_indices import calculate_drought_indices
except ImportError:
    calculate_drought_indices = None

try:
    from .extremes import calculate_extreme_events
except ImportError:
    calculate_extreme_events = None

try:
    from .seasonal_stats import calculate_seasonal_statistics
except ImportError:
    calculate_seasonal_statistics = None

__all__ = [
    "calculate_temperature_metrics",
    "calculate_drought_indices",
    "calculate_extreme_events",
    "calculate_seasonal_statistics",
]
