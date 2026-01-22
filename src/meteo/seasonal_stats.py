"""Seasonal meteorological statistics analysis.

This module provides tools for analyzing seasonal patterns and statistics
in meteorological time series data.
"""

from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from ..utils.logger import setup_logger

logger = setup_logger("seasonal_analysis", log_file="logs/meteorological.log")


class SeasonalStats:
    """Seasonal statistics analysis for meteorological data."""

    def __init__(self, data: pd.Series | xr.DataArray, variable_name: str = "variable") -> None:
        """Initialize seasonal statistics analysis.

        Args:
            data: Meteorological time series data.
            variable_name: Name of the variable for labeling.

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

            self.variable_name = variable_name

        except Exception as e:
            logger.error("Failed to initialize seasonal statistics: %s", e)
            raise

    def seasonal_means(self) -> pd.DataFrame:
        """Calculate seasonal means for each year.

        Returns:
            DataFrame with seasonal means indexed by year.
        """
        try:
            seasons = self._get_seasons()
            seasonal_data = self.data.groupby([self.data.index.year, seasons]).mean().unstack(level=1)

            seasonal_data.columns.name = "season"
            seasonal_data.index.name = "year"

            return seasonal_data.round(2)

        except Exception as e:
            logger.error("Failed to calculate seasonal means: %s", e)
            raise

    def seasonal_totals(self) -> pd.DataFrame:
        """Calculate seasonal totals for each year (useful for precipitation).

        Returns:
            DataFrame with seasonal totals indexed by year.
        """
        try:
            seasons = self._get_seasons()
            seasonal_data = self.data.groupby([self.data.index.year, seasons]).sum().unstack(level=1)

            seasonal_data.columns.name = "season"
            seasonal_data.index.name = "year"

            return seasonal_data.round(2)

        except Exception as e:
            logger.error("Failed to calculate seasonal totals: %s", e)
            raise

    def seasonal_extremes(self) -> pd.DataFrame:
        """Calculate seasonal extreme values (min and max) for each year.

        Returns:
            DataFrame with seasonal extremes.
        """
        try:
            seasons = self._get_seasons()

            # Calculate both min and max
            seasonal_min = self.data.groupby([self.data.index.year, seasons]).min().unstack(level=1)

            seasonal_max = self.data.groupby([self.data.index.year, seasons]).max().unstack(level=1)

            # Combine into a multi-level DataFrame
            extremes = pd.concat({"min": seasonal_min, "max": seasonal_max}, axis=1)

            extremes.index.name = "year"

            return extremes.round(2)

        except Exception as e:
            logger.error("Failed to calculate seasonal extremes: %s", e)
            raise

    def monthly_climatology(self, reference_period: tuple[int, int] | None = None) -> pd.Series:
        """Calculate monthly climatological means.

        Args:
            reference_period: Reference period (start_year, end_year) for climatology.

        Returns:
            Series with monthly climatological means.
        """
        try:
            if reference_period:
                start_year, end_year = reference_period
                mask = (self.data.index.year >= start_year) & (self.data.index.year <= end_year)
                data_subset = self.data[mask]
            else:
                data_subset = self.data

            monthly_clim = data_subset.groupby(data_subset.index.month).mean()
            monthly_clim.index.name = "month"

            return monthly_clim.round(2)

        except Exception as e:
            logger.error("Failed to calculate monthly climatology: %s", e)
            raise

    def seasonal_anomalies(self, reference_period: tuple[int, int] | None = None) -> pd.DataFrame:
        """Calculate seasonal anomalies relative to climatology.

        Args:
            reference_period: Reference period for climatology calculation.

        Returns:
            DataFrame with seasonal anomalies.
        """
        try:
            # Calculate seasonal climatology
            seasons = self._get_seasons()

            if reference_period:
                start_year, end_year = reference_period
                mask = (self.data.index.year >= start_year) & (self.data.index.year <= end_year)
                ref_data = self.data[mask]
            else:
                ref_data = self.data

            # Calculate seasonal climatology from reference period
            seasonal_clim = ref_data.groupby(seasons).mean()

            # Calculate seasonal means for all years
            seasonal_means = self.data.groupby([self.data.index.year, seasons]).mean().unstack(level=1)

            # Calculate anomalies
            anomalies = seasonal_means.subtract(seasonal_clim, axis=1)
            anomalies.index.name = "year"
            anomalies.columns.name = "season"

            return anomalies.round(2)

        except Exception as e:
            logger.error("Failed to calculate seasonal anomalies: %s", e)
            raise

    def annual_cycle_statistics(self) -> dict[str, Any]:
        """Calculate statistics describing the annual cycle.

        Returns:
            Dictionary with annual cycle characteristics.
        """
        try:
            monthly_clim = self.monthly_climatology()

            stats = {
                "annual_mean": float(monthly_clim.mean()),
                "annual_range": float(monthly_clim.max() - monthly_clim.min()),
                "max_month": int(monthly_clim.idxmax()),
                "min_month": int(monthly_clim.idxmin()),
                "max_value": float(monthly_clim.max()),
                "min_value": float(monthly_clim.min()),
                "coefficient_of_variation": float(monthly_clim.std() / monthly_clim.mean() * 100)
                if monthly_clim.mean() != 0
                else 0,
            }

            # Calculate timing metrics
            if len(monthly_clim) == 12:
                stats["peak_timing"] = self._calculate_peak_timing(monthly_clim)

            return stats

        except Exception as e:
            logger.error("Failed to calculate annual cycle statistics: %s", e)
            raise

    def _calculate_peak_timing(self, monthly_data: pd.Series) -> dict[str, float]:
        """Calculate timing of annual peak using harmonic analysis."""
        try:
            # Simple harmonic analysis to find peak timing
            months = np.arange(1, 13)
            values = monthly_data.values

            # First harmonic (annual cycle)
            x = 2 * np.pi * (months - 1) / 12
            a1 = np.mean(values * np.cos(x)) * 2
            b1 = np.mean(values * np.sin(x)) * 2

            # Phase and amplitude
            phase = np.arctan2(b1, a1)
            amplitude = np.sqrt(a1**2 + b1**2)

            # Convert phase to month (peak timing)
            peak_month = (phase * 12 / (2 * np.pi)) % 12 + 1

            return {
                "peak_month_harmonic": float(peak_month),
                "annual_amplitude": float(amplitude),
                "phase_radians": float(phase),
            }

        except Exception as e:
            logger.warning("Failed to calculate harmonic peak timing: %s", e)
            return {}

    def onset_dates(self, threshold: float, season: str = "growing") -> pd.Series:
        """Calculate onset dates for growing/dry seasons.

        Args:
            threshold: Threshold value for onset detection.
            season: Season type ('growing' for above threshold, 'dry' for below).

        Returns:
            Series with annual onset dates.
        """
        try:
            onset_dates = []

            for year in self.data.index.year.unique():
                year_data = self.data[self.data.index.year == year]

                if season == "growing":
                    condition = year_data >= threshold
                else:
                    condition = year_data <= threshold

                # Find first occurrence
                onset_idx = condition.idxmax() if condition.any() else None
                onset_dates.append(onset_idx)

            onset_series = pd.Series(
                onset_dates, index=self.data.index.year.unique(), name=f"{season}_season_onset"
            )

            return onset_series

        except Exception as e:
            logger.error("Failed to calculate onset dates: %s", e)
            raise

    def _get_seasons(self) -> pd.Series:
        """Get season labels for the data index."""

        def month_to_season(month: int) -> str:
            if month in [12, 1, 2]:
                return "Winter"
            elif month in [3, 4, 5]:
                return "Spring"
            elif month in [6, 7, 8]:
                return "Summer"
            else:
                return "Autumn"

        return self.data.index.month.map(month_to_season)

    def seasonal_trends(self) -> dict[str, Any]:
        """Calculate trends for each season using linear regression.

        Returns:
            Dictionary with seasonal trend statistics.
        """
        try:
            from scipy import stats as scipy_stats

            seasons = self._get_seasons()
            trends = {}

            for season in ["Winter", "Spring", "Summer", "Autumn"]:
                # Get seasonal data
                seasonal_data = (
                    self.data.groupby([self.data.index.year, seasons]).mean().unstack(level=1)
                )

                if season in seasonal_data.columns:
                    season_series = seasonal_data[season].dropna()

                    if len(season_series) >= 3:
                        # Calculate linear trend
                        years = season_series.index.values
                        values = season_series.values

                        slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(
                            years, values
                        )

                        trends[season] = {
                            "slope": float(slope),
                            "intercept": float(intercept),
                            "r_squared": float(r_value**2),
                            "p_value": float(p_value),
                            "trend_significant": p_value < 0.05,
                            "trend_per_decade": float(slope * 10),
                        }
                    else:
                        trends[season] = {
                            "slope": np.nan,
                            "trend_significant": False,
                            "insufficient_data": True,
                        }

            return trends

        except Exception as e:
            logger.error("Failed to calculate seasonal trends: %s", e)
            raise


def calculate_seasonal_statistics(
    data: pd.Series | xr.DataArray,
    variable_name: str = "variable",
    include_trends: bool = True,
    include_anomalies: bool = True,
    reference_period: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Calculate comprehensive seasonal statistics.

    Args:
        data: Meteorological time series data.
        variable_name: Name of the variable for labeling.
        include_trends: Whether to calculate seasonal trends.
        include_anomalies: Whether to calculate seasonal anomalies.
        reference_period: Reference period for climatology.

    Returns:
        Dictionary containing all calculated seasonal statistics.
    """
    try:
        analyzer = SeasonalStats(data, variable_name)

        results = {
            "seasonal_means": analyzer.seasonal_means(),
            "seasonal_totals": analyzer.seasonal_totals(),
            "seasonal_extremes": analyzer.seasonal_extremes(),
            "monthly_climatology": analyzer.monthly_climatology(reference_period),
            "annual_cycle_stats": analyzer.annual_cycle_statistics(),
        }

        if include_anomalies:
            results["seasonal_anomalies"] = analyzer.seasonal_anomalies(reference_period)

        if include_trends:
            results["seasonal_trends"] = analyzer.seasonal_trends()

        return results

    except Exception as e:
        logger.error("Failed to calculate comprehensive seasonal statistics: %s", e)
        raise
