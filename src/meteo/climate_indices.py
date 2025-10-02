"""Climate and drought indices for meteorological analysis.

This module provides calculation of various climate indices including
drought indices, aridity measures, and other climate indicators.
"""

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
import xarray as xr

from ..utils.logger import setup_logger

logger = setup_logger("climate_indices", log_file="logs/meteorological.log")


class DroughtIndices:
    """Calculate various drought and climate indices."""

    def __init__(
        self,
        precipitation: pd.Series | xr.DataArray,
        temperature: pd.Series | xr.DataArray | None = None,
        reference_period: tuple[int, int] | None = None,
    ) -> None:
        """Initialize drought indices calculation.

        Args:
            precipitation: Precipitation time series (mm).
            temperature: Temperature time series (°C). Required for some indices.
            reference_period: Reference period (start_year, end_year) for standardization.

        Raises:
            ValueError: If input data is invalid.
        """
        try:
            # Process precipitation data
            if isinstance(precipitation, pd.Series):
                if precipitation.empty:
                    raise ValueError("Precipitation data is empty")
                self.precipitation = precipitation
            elif isinstance(precipitation, xr.DataArray):
                if precipitation.size == 0:
                    raise ValueError("Precipitation data is empty")
                self.precipitation = precipitation.to_series()
            else:
                raise ValueError("Precipitation must be pandas Series or xarray DataArray")

            # Process temperature data if provided
            self.temperature = None
            if temperature is not None:
                if isinstance(temperature, pd.Series):
                    self.temperature = temperature
                elif isinstance(temperature, xr.DataArray):
                    self.temperature = temperature.to_series()

            self.reference_period = reference_period

        except Exception as e:
            logger.error("Failed to initialize drought indices calculation: %s", e)
            raise

    def spi(self, timescale: int = 12, distribution: str = "gamma") -> pd.Series:
        """Calculate Standardized Precipitation Index (SPI).

        Args:
            timescale: Time scale in months (1, 3, 6, 12, 24).
            distribution: Distribution to fit ('gamma' or 'pearson3').

        Returns:
            SPI time series.

        Raises:
            ValueError: If timescale is invalid or insufficient data.
        """
        try:
            if timescale not in [1, 3, 6, 12, 24, 48]:
                raise ValueError(f"Invalid timescale: {timescale}. Must be 1, 3, 6, 12, 24, or 48")

            # Resample to monthly if not already
            if hasattr(self.precipitation.index, "freq") and self.precipitation.index.freq != "MS":
                monthly_precip = self.precipitation.resample("MS").sum()
            else:
                monthly_precip = self.precipitation

            # Calculate rolling sum for the specified timescale
            if timescale > 1:
                precip_sum = monthly_precip.rolling(window=timescale, min_periods=timescale).sum()
            else:
                precip_sum = monthly_precip

            # Remove NaN values for fitting
            valid_data = precip_sum.dropna()

            if len(valid_data) < 30:
                raise ValueError(
                    f"Insufficient data for SPI calculation: {len(valid_data)} valid points"
                )

            # Fit distribution and calculate SPI
            if distribution == "gamma":
                spi_values = self._fit_gamma_spi(precip_sum, valid_data)
            elif distribution == "pearson3":
                spi_values = self._fit_pearson3_spi(precip_sum, valid_data)
            else:
                raise ValueError(f"Unsupported distribution: {distribution}")

            return pd.Series(spi_values, index=precip_sum.index, name=f"SPI_{timescale}")

        except Exception as e:
            logger.error("Failed to calculate SPI: %s", e)
            raise

    def _fit_gamma_spi(self, precip_sum: pd.Series, valid_data: pd.Series) -> np.ndarray:
        """Fit gamma distribution and calculate SPI."""
        # Fit gamma distribution to valid data
        # Add small value to handle zero precipitation
        fit_data = valid_data + 1e-6
        shape, loc, scale = stats.gamma.fit(fit_data, floc=0)

        # Calculate cumulative probabilities
        cdf_values = stats.gamma.cdf(precip_sum + 1e-6, shape, loc=loc, scale=scale)

        # Convert to standard normal (SPI)
        spi_values = stats.norm.ppf(cdf_values)

        return spi_values

    def _fit_pearson3_spi(self, precip_sum: pd.Series, valid_data: pd.Series) -> np.ndarray:
        """Fit Pearson Type III distribution and calculate SPI."""
        # Fit Pearson Type III (same as gamma with different parameterization)
        skew, loc, scale = stats.pearson3.fit(valid_data)

        # Calculate cumulative probabilities
        cdf_values = stats.pearson3.cdf(precip_sum, skew, loc=loc, scale=scale)

        # Convert to standard normal (SPI)
        spi_values = stats.norm.ppf(cdf_values)

        return spi_values

    def spei(self, timescale: int = 12, method: str = "thornthwaite") -> pd.Series:
        """Calculate Standardized Precipitation Evapotranspiration Index (SPEI).

        Args:
            timescale: Time scale in months.
            method: Method for PET calculation ('thornthwaite', 'hargreaves').

        Returns:
            SPEI time series.

        Raises:
            ValueError: If temperature data is missing or method is invalid.
        """
        try:
            if self.temperature is None:
                raise ValueError("Temperature data required for SPEI calculation")

            # Calculate potential evapotranspiration
            if method == "thornthwaite":
                pet = self._calculate_pet_thornthwaite()
            elif method == "hargreaves":
                pet = self._calculate_pet_hargreaves()
            else:
                raise ValueError(f"Unsupported PET method: {method}")

            # Calculate water balance (P - PET)
            water_balance = self.precipitation - pet

            # Resample to monthly if needed
            if hasattr(water_balance.index, "freq") and water_balance.index.freq != "MS":
                monthly_wb = water_balance.resample("MS").sum()
            else:
                monthly_wb = water_balance

            # Calculate rolling sum for the specified timescale
            if timescale > 1:
                wb_sum = monthly_wb.rolling(window=timescale, min_periods=timescale).sum()
            else:
                wb_sum = monthly_wb

            # Fit log-logistic distribution (commonly used for SPEI)
            valid_data = wb_sum.dropna()
            if len(valid_data) < 30:
                raise ValueError(
                    f"Insufficient data for SPEI calculation: {len(valid_data)} valid points"
                )

            # Standardize using empirical distribution
            spei_values = self._standardize_empirical(wb_sum, valid_data)

            return pd.Series(spei_values, index=wb_sum.index, name=f"SPEI_{timescale}")

        except Exception as e:
            logger.error("Failed to calculate SPEI: %s", e)
            raise

    def _calculate_pet_thornthwaite(self) -> pd.Series:
        """Calculate PET using Thornthwaite method (simplified)."""
        # Simplified Thornthwaite equation
        # Note: This is a basic implementation. For production use,
        # consider using specialized libraries like climdex or similar
        temp_monthly = self.temperature.resample("MS").mean()
        pet = np.maximum(16 * (10 * temp_monthly / 25) ** 1.5, 0)
        return pet

    def _calculate_pet_hargreaves(self) -> pd.Series:
        """Calculate PET using Hargreaves method (simplified)."""
        # Very simplified Hargreaves equation
        # Requires additional parameters for full implementation
        temp_monthly = self.temperature.resample("MS").mean()
        pet = 0.0023 * (temp_monthly + 17.8) * 30  # Rough approximation
        return np.maximum(pet, 0)

    def _standardize_empirical(self, data: pd.Series, valid_data: pd.Series) -> np.ndarray:
        """Standardize data using empirical distribution."""
        # Calculate empirical cumulative distribution
        sorted_data = np.sort(valid_data)
        n = len(sorted_data)

        # Calculate ranks and probabilities for each value
        standardized = np.full(len(data), np.nan)

        for i, value in enumerate(data):
            if not np.isnan(value):
                # Find rank in sorted data
                rank = np.searchsorted(sorted_data, value)
                prob = rank / n

                # Convert to standard normal
                if prob == 0:
                    prob = 1 / (2 * n)
                elif prob == 1:
                    prob = 1 - 1 / (2 * n)

                standardized[i] = stats.norm.ppf(prob)

        return standardized

    def palmer_drought_severity_index(self) -> pd.Series:
        """Calculate Palmer Drought Severity Index (PDSI).

        Note: This is a simplified implementation.
        Full PDSI requires additional meteorological parameters.

        Returns:
            Simplified PDSI time series.
        """
        try:
            if self.temperature is None:
                raise ValueError("Temperature data required for PDSI calculation")

            # Simplified PDSI calculation
            # Calculate water balance
            pet = self._calculate_pet_thornthwaite()
            water_balance = self.precipitation - pet

            # Calculate cumulative departure from normal
            monthly_wb = water_balance.resample("MS").sum()
            normal_wb = monthly_wb.groupby(monthly_wb.index.month).transform("mean")
            departure = monthly_wb - normal_wb

            # Simple cumulative approach (not full PDSI algorithm)
            pdsi = departure.cumsum() / departure.std()

            return pd.Series(pdsi, name="PDSI")

        except Exception as e:
            logger.error("Failed to calculate PDSI: %s", e)
            raise

    def aridity_index(self) -> float:
        """Calculate aridity index (P/PET ratio).

        Returns:
            Aridity index value.
        """
        try:
            if self.temperature is None:
                raise ValueError("Temperature data required for aridity index")

            pet = self._calculate_pet_thornthwaite()
            annual_precip = self.precipitation.resample("YE").sum().mean()
            annual_pet = pet.resample("YE").sum().mean()

            aridity = annual_precip / annual_pet if annual_pet > 0 else np.inf

            return float(aridity)

        except Exception as e:
            logger.error("Failed to calculate aridity index: %s", e)
            raise

    def consecutive_dry_days(self, threshold: float = 1.0) -> dict[str, Any]:
        """Calculate consecutive dry days statistics.

        Args:
            threshold: Precipitation threshold for dry day (mm).

        Returns:
            Dictionary with CDD statistics.
        """
        try:
            dry_days = self.precipitation < threshold

            # Find consecutive dry periods
            consecutive_periods = []
            current_period = 0

            for is_dry in dry_days:
                if is_dry:
                    current_period += 1
                else:
                    if current_period > 0:
                        consecutive_periods.append(current_period)
                    current_period = 0

            # Add final period if series ends with dry days
            if current_period > 0:
                consecutive_periods.append(current_period)

            if not consecutive_periods:
                consecutive_periods = [0]

            return {
                "max_consecutive_dry_days": max(consecutive_periods),
                "mean_consecutive_dry_days": np.mean(consecutive_periods),
                "total_dry_periods": len(consecutive_periods),
                "total_dry_days": int(dry_days.sum()),
                "dry_day_percentage": float(dry_days.mean() * 100),
            }

        except Exception as e:
            logger.error("Failed to calculate consecutive dry days: %s", e)
            raise


def calculate_drought_indices(
    precipitation: pd.Series | xr.DataArray,
    temperature: pd.Series | xr.DataArray | None = None,
    include_spi: bool = True,
    include_spei: bool = True,
    include_pdsi: bool = False,
    spi_timescales: list[int] | None = None,
    spei_timescales: list[int] | None = None,
) -> dict[str, Any]:
    """Calculate comprehensive drought indices.

    Args:
        precipitation: Precipitation time series.
        temperature: Temperature time series (required for SPEI and PDSI).
        include_spi: Whether to calculate SPI.
        include_spei: Whether to calculate SPEI.
        include_pdsi: Whether to calculate PDSI.
        spi_timescales: List of SPI timescales to calculate.
        spei_timescales: List of SPEI timescales to calculate.

    Returns:
        Dictionary containing all calculated drought indices.
    """
    try:
        analyzer = DroughtIndices(precipitation, temperature)

        if spi_timescales is None:
            spi_timescales = [3, 6, 12]
        if spei_timescales is None:
            spei_timescales = [3, 6, 12]

        results = {
            "consecutive_dry_days": analyzer.consecutive_dry_days(),
        }

        if include_spi:
            results["spi"] = {}
            for timescale in spi_timescales:
                try:
                    results["spi"][f"spi_{timescale}"] = analyzer.spi(timescale)
                except Exception as e:
                    logger.warning("Failed to calculate SPI-%d: %s", timescale, e)

        if include_spei and temperature is not None:
            results["spei"] = {}
            for timescale in spei_timescales:
                try:
                    results["spei"][f"spei_{timescale}"] = analyzer.spei(timescale)
                except Exception as e:
                    logger.warning("Failed to calculate SPEI-%d: %s", timescale, e)

            try:
                results["aridity_index"] = analyzer.aridity_index()
            except Exception as e:
                logger.warning("Failed to calculate aridity index: %s", e)

        if include_pdsi and temperature is not None:
            try:
                results["pdsi"] = analyzer.palmer_drought_severity_index()
            except Exception as e:
                logger.warning("Failed to calculate PDSI: %s", e)

        return results

    except Exception as e:
        logger.error("Failed to calculate comprehensive drought indices: %s", e)
        raise
