"""Data processing utilities for CAMELS-RU dataset.

This module provides utility functions for processing discharge time series data,
including splitting by hydrological and calendar years.
"""

import pandas as pd

from .utils.logger import setup_logger

logger = setup_logger("data_processing", log_file="logs/processing.log")


def split_by_hydro_year(discharge_obs: pd.Series) -> dict[str, pd.Series]:
    """Split discharge time series by hydrological year (Oct 1 - Sep 30).

    Args:
        discharge_obs: Pandas Series with DatetimeIndex containing discharge observations.

    Returns:
        Dictionary with year strings as keys and corresponding yearly data as values.

    Raises:
        ValueError: If the input series is empty or has no valid datetime index.
    """
    try:
        if discharge_obs.empty:
            raise ValueError("Input discharge series is empty")

        return {
            str(year): discharge_obs[f"10/01/{year}" : f"10/01/{year + 1}"]
            for year in discharge_obs.index.year.unique()
        }
    except Exception as e:
        logger.error("Failed to split discharge data by hydrological year: %s", e)
        raise


def split_by_year(discharge_obs: pd.Series) -> dict[str, pd.Series]:
    """Split discharge time series by calendar year (Jan 1 - Dec 31).

    Args:
        discharge_obs: Pandas Series with DatetimeIndex containing discharge observations.

    Returns:
        Dictionary with year strings as keys and corresponding yearly data as values.

    Raises:
        ValueError: If the input series is empty or has no valid datetime index.
    """
    try:
        if discharge_obs.empty:
            raise ValueError("Input discharge series is empty")

        return {
            str(year): discharge_obs[f"01/01/{year}" : f"12/31/{year}"]
            for year in discharge_obs.index.year.unique()
        }
    except Exception as e:
        logger.error("Failed to split discharge data by calendar year: %s", e)
        raise
