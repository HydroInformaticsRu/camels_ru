"""Extreme meteorological events analysis.

This module provides tools for identifying and analyzing extreme weather events
including heat waves, cold spells, and precipitation extremes.
"""

from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from ..utils.logger import setup_logger

logger = setup_logger("extreme_events", log_file="logs/meteorological.log")


class ExtremeEvents:
    """Analysis of extreme meteorological events."""

    def __init__(self, data: pd.Series | xr.DataArray, variable_type: str = "temperature") -> None:
        """Initialize extreme events analysis.

        Args:
            data: Meteorological time series data.
            variable_type: Type of variable ('temperature', 'precipitation', 'wind').

        Raises:
            ValueError: If input data is invalid.
        """
        try:
            if isinstance(data, pd.Series):
                if data.empty:
                    raise ValueError("Input data is empty")
                self.data = data
            elif isinstance(data, xr.DataArray):
                if data.size == 0:
                    raise ValueError("Input data is empty")
                self.data = data.to_series()
            else:
                raise ValueError("Data must be pandas Series or xarray DataArray")

            self.variable_type = variable_type.lower()

        except Exception as e:
            logger.error("Failed to initialize extreme events analysis: %s", e)
            raise

    def percentile_thresholds(
        self, low_percentile: float = 10, high_percentile: float = 90
    ) -> dict[str, float]:
        """Calculate percentile-based thresholds for extreme events.

        Args:
            low_percentile: Lower percentile for extreme low events.
            high_percentile: Upper percentile for extreme high events.

        Returns:
            Dictionary with low and high thresholds.
        """
        try:
            return {
                "low_threshold": float(self.data.quantile(low_percentile / 100)),
                "high_threshold": float(self.data.quantile(high_percentile / 100)),
                "low_percentile": low_percentile,
                "high_percentile": high_percentile,
            }

        except Exception as e:
            logger.error("Failed to calculate percentile thresholds: %s", e)
            raise

    def identify_extremes(
        self, low_threshold: float | None = None, high_threshold: float | None = None
    ) -> dict[str, Any]:
        """Identify extreme events based on thresholds.

        Args:
            low_threshold: Threshold for extreme low events. If None, uses 10th percentile.
            high_threshold: Threshold for extreme high events. If None, uses 90th percentile.

        Returns:
            Dictionary with extreme event identification results.
        """
        try:
            if low_threshold is None or high_threshold is None:
                thresholds = self.percentile_thresholds()
                low_threshold = low_threshold or thresholds["low_threshold"]
                high_threshold = high_threshold or thresholds["high_threshold"]

            extreme_low = self.data <= low_threshold
            extreme_high = self.data >= high_threshold

            return {
                "extreme_low_events": self._analyze_extreme_periods(extreme_low),
                "extreme_high_events": self._analyze_extreme_periods(extreme_high),
                "thresholds": {
                    "low_threshold": low_threshold,
                    "high_threshold": high_threshold,
                },
                "extreme_low_count": int(extreme_low.sum()),
                "extreme_high_count": int(extreme_high.sum()),
                "extreme_low_percentage": float(extreme_low.mean() * 100),
                "extreme_high_percentage": float(extreme_high.mean() * 100),
            }

        except Exception as e:
            logger.error("Failed to identify extreme events: %s", e)
            raise

    def _analyze_extreme_periods(self, condition: pd.Series) -> list[dict[str, Any]]:
        """Analyze periods of extreme conditions."""
        events = []
        in_event = False
        event_start = None

        for date, is_extreme in condition.items():
            if is_extreme and not in_event:
                # Start of new extreme event
                in_event = True
                event_start = date
            elif not is_extreme and in_event:
                # End of extreme event
                in_event = False
                event_end = condition.index[condition.index.get_indexer([date])[0] - 1]
                duration = (event_end - event_start).days + 1
                event_data = self.data[event_start:event_end]

                events.append(
                    {
                        "start_date": str(event_start),
                        "end_date": str(event_end),
                        "duration_days": duration,
                        "intensity_mean": float(event_data.mean()),
                        "intensity_min": float(event_data.min()),
                        "intensity_max": float(event_data.max()),
                    }
                )

        # Handle case where series ends during an extreme event
        if in_event and event_start is not None:
            event_end = condition.index[-1]
            duration = (event_end - event_start).days + 1
            event_data = self.data[event_start:event_end]

            events.append(
                {
                    "start_date": str(event_start),
                    "end_date": str(event_end),
                    "duration_days": duration,
                    "intensity_mean": float(event_data.mean()),
                    "intensity_min": float(event_data.min()),
                    "intensity_max": float(event_data.max()),
                }
            )

        return events

    def heat_waves(self, temperature_threshold: float = 30, min_duration: int = 3) -> dict[str, Any]:
        """Identify heat wave events.

        Args:
            temperature_threshold: Minimum temperature for heat wave (°C).
            min_duration: Minimum duration in days.

        Returns:
            Dictionary with heat wave analysis results.
        """
        try:
            if self.variable_type != "temperature":
                logger.warning("Heat wave analysis typically requires temperature data")

            hot_days = self.data >= temperature_threshold
            heat_waves = self._find_consecutive_events(hot_days, min_duration)

            return {
                "heat_wave_events": heat_waves,
                "total_heat_waves": len(heat_waves),
                "total_heat_wave_days": sum(hw["duration_days"] for hw in heat_waves),
                "average_duration": np.mean([hw["duration_days"] for hw in heat_waves])
                if heat_waves
                else 0,
                "maximum_duration": max((hw["duration_days"] for hw in heat_waves), default=0),
                "maximum_intensity": max((hw["intensity_max"] for hw in heat_waves), default=0),
            }

        except Exception as e:
            logger.error("Failed to analyze heat waves: %s", e)
            raise

    def cold_spells(self, temperature_threshold: float = -10, min_duration: int = 3) -> dict[str, Any]:
        """Identify cold spell events.

        Args:
            temperature_threshold: Maximum temperature for cold spell (°C).
            min_duration: Minimum duration in days.

        Returns:
            Dictionary with cold spell analysis results.
        """
        try:
            if self.variable_type != "temperature":
                logger.warning("Cold spell analysis typically requires temperature data")

            cold_days = self.data <= temperature_threshold
            cold_spells = self._find_consecutive_events(cold_days, min_duration)

            return {
                "cold_spell_events": cold_spells,
                "total_cold_spells": len(cold_spells),
                "total_cold_spell_days": sum(cs["duration_days"] for cs in cold_spells),
                "average_duration": np.mean([cs["duration_days"] for cs in cold_spells])
                if cold_spells
                else 0,
                "maximum_duration": max((cs["duration_days"] for cs in cold_spells), default=0),
                "minimum_intensity": min((cs["intensity_min"] for cs in cold_spells), default=0),
            }

        except Exception as e:
            logger.error("Failed to analyze cold spells: %s", e)
            raise

    def _find_consecutive_events(self, condition: pd.Series, min_duration: int) -> list[dict[str, Any]]:
        """Find consecutive events meeting a condition with minimum duration."""
        events = []
        current_start = None
        consecutive_days = 0

        for date, meets_condition in condition.items():
            if meets_condition:
                if current_start is None:
                    current_start = date
                consecutive_days += 1
            else:
                if current_start is not None and consecutive_days >= min_duration:
                    # End of qualifying event
                    event_end = condition.index[condition.index.get_indexer([date])[0] - 1]
                    event_data = self.data[current_start:event_end]

                    events.append(
                        {
                            "start_date": str(current_start),
                            "end_date": str(event_end),
                            "duration_days": consecutive_days,
                            "intensity_mean": float(event_data.mean()),
                            "intensity_min": float(event_data.min()),
                            "intensity_max": float(event_data.max()),
                        }
                    )

                current_start = None
                consecutive_days = 0

        # Handle event at end of series
        if current_start is not None and consecutive_days >= min_duration:
            event_end = condition.index[-1]
            event_data = self.data[current_start:event_end]

            events.append(
                {
                    "start_date": str(current_start),
                    "end_date": str(event_end),
                    "duration_days": consecutive_days,
                    "intensity_mean": float(event_data.mean()),
                    "intensity_min": float(event_data.min()),
                    "intensity_max": float(event_data.max()),
                }
            )

        return events

    def annual_extremes(self) -> pd.DataFrame:
        """Calculate annual extreme statistics.

        Returns:
            DataFrame with annual extreme statistics.
        """
        try:
            # Group by year and calculate extremes
            annual_stats = (
                self.data.groupby(self.data.index.year)
                .agg(
                    [
                        "min",
                        "max",
                        "mean",
                        "std",
                        lambda x: x.quantile(0.01),  # 1st percentile
                        lambda x: x.quantile(0.99),  # 99th percentile
                    ]
                )
                .round(3)
            )

            annual_stats.columns = ["min", "max", "mean", "std", "p01", "p99"]
            annual_stats.index.name = "year"

            return annual_stats

        except Exception as e:
            logger.error("Failed to calculate annual extremes: %s", e)
            raise


def calculate_extreme_events(
    data: pd.Series | xr.DataArray,
    variable_type: str = "temperature",
    include_heat_waves: bool = True,
    include_cold_spells: bool = True,
    heat_threshold: float = 30,
    cold_threshold: float = -10,
    min_duration: int = 3,
) -> dict[str, Any]:
    """Calculate comprehensive extreme event metrics.

    Args:
        data: Meteorological time series data.
        variable_type: Type of variable ('temperature', 'precipitation', 'wind').
        include_heat_waves: Whether to analyze heat waves.
        include_cold_spells: Whether to analyze cold spells.
        heat_threshold: Temperature threshold for heat waves (°C).
        cold_threshold: Temperature threshold for cold spells (°C).
        min_duration: Minimum duration for consecutive events.

    Returns:
        Dictionary containing all calculated extreme event metrics.
    """
    try:
        analyzer = ExtremeEvents(data, variable_type)

        results = {
            "extremes_general": analyzer.identify_extremes(),
            "annual_extremes": analyzer.annual_extremes(),
        }

        if include_heat_waves and variable_type == "temperature":
            results["heat_waves"] = analyzer.heat_waves(heat_threshold, min_duration)

        if include_cold_spells and variable_type == "temperature":
            results["cold_spells"] = analyzer.cold_spells(cold_threshold, min_duration)

        return results

    except Exception as e:
        logger.error("Failed to calculate comprehensive extreme event metrics: %s", e)
        raise
