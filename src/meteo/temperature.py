"""Temperature analysis for meteorological time series.

This module provides comprehensive temperature analysis including
basic statistics, trend analysis, and extreme temperature events.
"""

from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from ..utils.logger import setup_logger

logger = setup_logger("temperature_analysis", log_file="logs/meteorological.log")


class TemperatureAnalysis:
    """Comprehensive temperature analysis for meteorological time series."""

    def __init__(self, temperature_data: pd.Series | xr.DataArray) -> None:
        """Initialize temperature analysis.

        Args:
            temperature_data: Temperature time series with datetime index.
                Units should be in Celsius or Kelvin.

        Raises:
            ValueError: If input data is empty or has no datetime index.
        """
        try:
            if isinstance(temperature_data, pd.Series):
                if temperature_data.empty:
                    raise ValueError("Temperature data is empty")
                if not isinstance(temperature_data.index, pd.DatetimeIndex):
                    raise ValueError("Temperature data must have DatetimeIndex")
                self.data = temperature_data
            elif isinstance(temperature_data, xr.DataArray):
                if temperature_data.size == 0:
                    raise ValueError("Temperature data is empty")
                self.data = temperature_data.to_series()
            else:
                raise ValueError("Temperature data must be pandas Series or xarray DataArray")

            # Check for reasonable temperature range
            temp_min, temp_max = self.data.min(), self.data.max()
            if temp_max > 100:  # Likely Kelvin
                logger.warning(
                    "Temperature values appear to be in Kelvin (max=%.1f). Consider converting to Celsius.",
                    temp_max,
                )
            elif temp_min < -100 or temp_max > 60:
                logger.warning(
                    "Temperature values outside expected range (%.1f to %.1f°C)", temp_min, temp_max
                )

        except Exception as e:
            logger.error("Failed to initialize temperature analysis: %s", e)
            raise

    def basic_statistics(self) -> dict[str, float]:
        """Calculate basic temperature statistics.

        Returns:
            Dictionary containing mean, std, min, max, median, and quantiles.
        """
        try:
            stats_dict = {
                "mean": float(self.data.mean()),
                "std": float(self.data.std()),
                "min": float(self.data.min()),
                "max": float(self.data.max()),
                "median": float(self.data.median()),
                "q25": float(self.data.quantile(0.25)),
                "q75": float(self.data.quantile(0.75)),
                "count": int(self.data.count()),
                "missing_count": int(self.data.isna().sum()),
            }
            return stats_dict

        except Exception as e:
            logger.error("Failed to calculate basic temperature statistics: %s", e)
            raise

    def annual_statistics(self) -> pd.DataFrame:
        """Calculate annual temperature statistics.

        Returns:
            DataFrame with yearly statistics including mean, min, max temperatures.
        """
        try:
            annual_stats = (
                self.data.groupby(self.data.index.year)
                .agg(
                    {
                        self.data.name or "temperature": [
                            "mean",
                            "min",
                            "max",
                            "std",
                            "count",
                            lambda x: x.quantile(0.1),  # 10th percentile
                            lambda x: x.quantile(0.9),  # 90th percentile
                        ]
                    }
                )
                .round(2)
            )

            # Flatten column names
            annual_stats.columns = ["_".join(col).strip() for col in annual_stats.columns]
            annual_stats.index.name = "year"

            return annual_stats

        except Exception as e:
            logger.error("Failed to calculate annual temperature statistics: %s", e)
            raise

    def seasonal_statistics(self) -> pd.DataFrame:
        """Calculate seasonal temperature statistics.

        Returns:
            DataFrame with seasonal statistics for each year.
        """
        try:
            # Define seasons (Northern Hemisphere)
            def get_season(month: int) -> str:
                if month in [12, 1, 2]:
                    return "Winter"
                elif month in [3, 4, 5]:
                    return "Spring"
                elif month in [6, 7, 8]:
                    return "Summer"
                else:
                    return "Autumn"

            seasonal_data = (
                self.data.groupby([self.data.index.year, self.data.index.month.map(get_season)])
                .agg(["mean", "min", "max", "std"])
                .round(2)
            )

            seasonal_data.index.names = ["year", "season"]
            return seasonal_data

        except Exception as e:
            logger.error("Failed to calculate seasonal temperature statistics: %s", e)
            raise

    def extreme_events(self, cold_threshold: float = -20, hot_threshold: float = 35) -> dict[str, Any]:
        """Identify extreme temperature events.

        Args:
            cold_threshold: Temperature threshold for cold extremes (°C).
            hot_threshold: Temperature threshold for hot extremes (°C).

        Returns:
            Dictionary with extreme event statistics and indices.
        """
        try:
            cold_days = self.data <= cold_threshold
            hot_days = self.data >= hot_threshold

            # Calculate consecutive extreme days
            cold_consecutive = self._consecutive_days(cold_days)
            hot_consecutive = self._consecutive_days(hot_days)

            extremes = {
                "cold_days_count": int(cold_days.sum()),
                "hot_days_count": int(hot_days.sum()),
                "cold_days_percentage": float(cold_days.mean() * 100),
                "hot_days_percentage": float(hot_days.mean() * 100),
                "max_consecutive_cold": int(cold_consecutive.max()) if len(cold_consecutive) > 0 else 0,
                "max_consecutive_hot": int(hot_consecutive.max()) if len(hot_consecutive) > 0 else 0,
                "coldest_day": {
                    "date": str(self.data.idxmin()),
                    "temperature": float(self.data.min()),
                },
                "hottest_day": {
                    "date": str(self.data.idxmax()),
                    "temperature": float(self.data.max()),
                },
            }

            return extremes

        except Exception as e:
            logger.error("Failed to calculate extreme temperature events: %s", e)
            raise

    def _consecutive_days(self, condition: pd.Series) -> np.ndarray:
        """Calculate consecutive days meeting a condition."""
        # Find groups of consecutive True values
        groups = condition.ne(condition.shift()).cumsum()[condition]
        if groups.empty:
            return np.array([])
        return groups.value_counts().values

    def degree_days(self, base_temp: float = 10) -> dict[str, pd.Series]:
        """Calculate growing and heating degree days.

        Args:
            base_temp: Base temperature for degree day calculations (°C).

        Returns:
            Dictionary with growing and heating degree day series.
        """
        try:
            # Growing degree days (temperature above base)
            gdd = np.maximum(self.data - base_temp, 0)

            # Heating degree days (base temperature above observed)
            hdd = np.maximum(base_temp - self.data, 0)

            return {
                "growing_degree_days": gdd,
                "heating_degree_days": hdd,
                "annual_gdd": gdd.groupby(gdd.index.year).sum(),
                "annual_hdd": hdd.groupby(hdd.index.year).sum(),
            }

        except Exception as e:
            logger.error("Failed to calculate degree days: %s", e)
            raise

    def frost_analysis(self, frost_threshold: float = 0) -> dict[str, Any]:
        """Analyze frost events and frost-free periods.

        Args:
            frost_threshold: Temperature threshold for frost (°C).

        Returns:
            Dictionary with frost analysis results.
        """
        try:
            frost_days = self.data <= frost_threshold

            # Find first and last frost dates for each year
            yearly_frost = []
            for year in self.data.index.year.unique():
                year_data = frost_days[self.data.index.year == year]
                if year_data.any():
                    first_frost = year_data.idxmax() if year_data.any() else None
                    last_frost = year_data[::-1].idxmax() if year_data.any() else None
                    yearly_frost.append(
                        {
                            "year": year,
                            "first_frost": first_frost,
                            "last_frost": last_frost,
                            "frost_days": int(year_data.sum()),
                        }
                    )

            frost_analysis = {
                "total_frost_days": int(frost_days.sum()),
                "frost_percentage": float(frost_days.mean() * 100),
                "yearly_frost": yearly_frost,
                "average_frost_days_per_year": np.mean([f["frost_days"] for f in yearly_frost])
                if yearly_frost
                else 0,
            }

            return frost_analysis

        except Exception as e:
            logger.error("Failed to perform frost analysis: %s", e)
            raise


def calculate_temperature_metrics(
    temperature_data: pd.Series | xr.DataArray,
    include_extremes: bool = True,
    include_degree_days: bool = True,
    cold_threshold: float = -20,
    hot_threshold: float = 35,
    base_temp: float = 10,
) -> dict[str, Any]:
    """Calculate comprehensive temperature metrics.

    Args:
        temperature_data: Temperature time series data.
        include_extremes: Whether to calculate extreme event metrics.
        include_degree_days: Whether to calculate degree day metrics.
        cold_threshold: Temperature threshold for cold extremes (°C).
        hot_threshold: Temperature threshold for hot extremes (°C).
        base_temp: Base temperature for degree day calculations (°C).

    Returns:
        Dictionary containing all calculated temperature metrics.

    Raises:
        ValueError: If input data is invalid.
    """
    try:
        analyzer = TemperatureAnalysis(temperature_data)

        results = {
            "basic_statistics": analyzer.basic_statistics(),
            "annual_statistics": analyzer.annual_statistics(),
            "seasonal_statistics": analyzer.seasonal_statistics(),
        }

        if include_extremes:
            results["extreme_events"] = analyzer.extreme_events(cold_threshold, hot_threshold)
            results["frost_analysis"] = analyzer.frost_analysis()

        if include_degree_days:
            results["degree_days"] = analyzer.degree_days(base_temp)

        return results

    except Exception as e:
        logger.error("Failed to calculate comprehensive temperature metrics: %s", e)
        raise
