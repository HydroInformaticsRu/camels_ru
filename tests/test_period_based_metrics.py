"""Tests for period-based hydrological metrics calculation."""

import numpy as np
import pandas as pd
import pytest

from src.hydro.period_based_metrics import (
    aggregate_period_metrics,
    calculate_comprehensive_metrics,
    calculate_period_metrics,
    calculate_runoff_ratio,
    split_by_period,
)


@pytest.fixture
def sample_discharge():
    """Create sample discharge time series for testing."""
    dates = pd.date_range("2010-01-01", "2023-12-31", freq="D")
    np.random.seed(42)
    discharge = pd.Series(np.abs(np.random.normal(2.0, 0.5, len(dates))), index=dates, name="discharge")
    return discharge


@pytest.fixture
def sample_discharge_with_nans():
    """Create sample discharge with some NaN values."""
    dates = pd.date_range("2010-01-01", "2023-12-31", freq="D")
    np.random.seed(42)
    discharge = pd.Series(np.abs(np.random.normal(2.0, 0.5, len(dates))), index=dates, name="discharge")
    # Add some NaNs (10% of data)
    nan_indices = np.random.choice(len(discharge), size=int(len(discharge) * 0.1), replace=False)
    discharge.iloc[nan_indices] = np.nan
    return discharge


def test_split_by_period_hydrological(sample_discharge):
    """Test splitting by hydrological year."""
    periods = split_by_period(sample_discharge, period_type="hydrological", hydro_year_start_month=10)

    # Should have ~14 hydrological years (Oct 2010 - Sep 2023)
    assert len(periods) >= 12, f"Expected at least 12 periods, got {len(periods)}"

    # Each period should have data
    for year, data in periods.items():
        assert len(data) > 0, f"Year {year} has no data"
        assert isinstance(data, pd.Series)


def test_split_by_period_calendar(sample_discharge):
    """Test splitting by calendar year."""
    periods = split_by_period(sample_discharge, period_type="calendar")

    # Should have 14 calendar years (2010-2023)
    assert len(periods) == 14, f"Expected 14 periods, got {len(periods)}"

    # Check year range
    assert min(periods.keys()) == 2010
    assert max(periods.keys()) == 2023


def test_calculate_period_metrics(sample_discharge):
    """Test metrics calculation for single period."""
    # Get one year of data
    year_data = sample_discharge["2015-01-01":"2015-12-31"]

    metrics = calculate_period_metrics(year_data, min_data_fraction=0.7)

    # Check that key metrics are present
    assert "mean_discharge" in metrics
    assert "baseflow_index" in metrics
    assert "fdc_slope" in metrics
    assert "q05" in metrics
    assert "q95" in metrics

    # Check values are reasonable
    assert metrics["mean_discharge"] > 0
    assert 0 <= metrics["baseflow_index"] <= 1
    assert metrics["q95"] < metrics["q05"]  # Q95 should be less than Q5


def test_calculate_period_metrics_insufficient_data(sample_discharge_with_nans):
    """Test that insufficient data returns NaNs."""
    # Create a year with >30% missing data
    year_data = sample_discharge_with_nans["2015-01-01":"2015-12-31"]

    # Make >30% NaN
    year_data.iloc[: int(len(year_data) * 0.4)] = np.nan

    metrics = calculate_period_metrics(year_data, min_data_fraction=0.7)

    # Should return NaNs for all metrics
    assert np.isnan(metrics["mean_discharge"])


def test_aggregate_period_metrics(sample_discharge):
    """Test aggregation of metrics across periods."""
    # Split into periods and calculate metrics
    periods = split_by_period(sample_discharge, period_type="calendar")
    period_metrics = {}

    for year, period_data in periods.items():
        period_metrics[year] = calculate_period_metrics(period_data)

    # Aggregate
    aggregated = aggregate_period_metrics(period_metrics, aggregation="mean", min_periods=3)

    # Check that we have aggregated metrics
    assert "mean_discharge" in aggregated
    assert "mean_discharge_std" in aggregated
    assert "mean_discharge_cv" in aggregated
    assert "n_valid_periods" in aggregated

    # Check values are reasonable
    assert aggregated["mean_discharge"] > 0
    assert aggregated["mean_discharge_std"] >= 0
    assert aggregated["n_valid_periods"] == len(period_metrics)


def test_calculate_comprehensive_metrics(sample_discharge):
    """Test comprehensive metrics calculation (main entry point)."""
    metrics = calculate_comprehensive_metrics(
        sample_discharge,
        period_type="hydrological",
        hydro_year_start_month=10,
        min_data_fraction=0.7,
        min_periods=3,
        aggregation="mean",
    )

    # Check all expected metrics are present
    expected_metrics = [
        "mean_discharge",
        "median_discharge",
        "std_discharge",
        "cv_discharge",
        "baseflow_index",
        "fdc_slope",
        "q05",
        "q50",
        "q95",
        "high_flow_frequency",
        "low_flow_frequency",
        "n_valid_periods",
        "mean_discharge_std",
        "mean_discharge_cv",
    ]

    for metric in expected_metrics:
        assert metric in metrics, f"Missing metric: {metric}"

    # Check values are reasonable
    assert metrics["mean_discharge"] > 0
    assert 0 <= metrics["baseflow_index"] <= 1
    assert metrics["n_valid_periods"] >= 3


def test_calculate_comprehensive_metrics_with_nans(sample_discharge_with_nans):
    """Test that NaN handling works correctly."""
    metrics = calculate_comprehensive_metrics(
        sample_discharge_with_nans,
        period_type="calendar",
        min_data_fraction=0.6,  # More lenient for this test
        min_periods=3,
        aggregation="mean",
    )

    # Should still get valid metrics despite NaNs
    assert not np.isnan(metrics["mean_discharge"])
    assert metrics["n_valid_periods"] >= 3


def test_calculate_runoff_ratio():
    """Test runoff ratio calculation."""
    # Create sample discharge and precipitation
    dates = pd.date_range("2010-01-01", "2023-12-31", freq="D")
    np.random.seed(42)

    discharge = pd.Series(np.abs(np.random.normal(1.5, 0.3, len(dates))), index=dates)
    precipitation = pd.Series(np.abs(np.random.normal(3.0, 0.5, len(dates))), index=dates)

    rr = calculate_runoff_ratio(
        discharge,
        precipitation,
        period_type="calendar",
        hydro_year_start_month=10,
        min_periods=3,
    )

    # Runoff ratio should be between 0 and 1 (allowing some >1 for snowmelt)
    assert 0 <= rr <= 1.5, f"Implausible runoff ratio: {rr}"


def test_median_aggregation(sample_discharge):
    """Test using median aggregation instead of mean."""
    metrics_mean = calculate_comprehensive_metrics(
        sample_discharge, period_type="calendar", aggregation="mean"
    )

    metrics_median = calculate_comprehensive_metrics(
        sample_discharge, period_type="calendar", aggregation="median"
    )

    # Both should return valid results
    assert not np.isnan(metrics_mean["mean_discharge"])
    assert not np.isnan(metrics_median["mean_discharge"])

    # Median should be close to mean for normally distributed data
    assert abs(metrics_mean["mean_discharge"] - metrics_median["mean_discharge"]) < 0.5


def test_insufficient_periods(sample_discharge):
    """Test that insufficient periods returns NaNs."""
    # Use only 2 years of data but require 5 periods
    short_discharge = sample_discharge["2010-01-01":"2011-12-31"]

    metrics = calculate_comprehensive_metrics(
        short_discharge,
        period_type="calendar",
        min_periods=5,  # Too strict
    )

    # Should return NaN for metrics
    assert np.isnan(metrics["mean_discharge"])


def test_physical_constraints(sample_discharge):
    """Test that calculated metrics satisfy physical constraints."""
    metrics = calculate_comprehensive_metrics(sample_discharge, period_type="calendar")

    # BFI should be between 0 and 1
    assert 0 <= metrics["baseflow_index"] <= 1, f"BFI out of bounds: {metrics['baseflow_index']}"

    # FDC ordering
    assert metrics["q95"] < metrics["q50"] < metrics["q05"], (
        f"FDC ordering violated: Q95={metrics['q95']}, Q50={metrics['q50']}, Q05={metrics['q05']}"
    )

    # CV should be non-negative
    assert metrics["cv_discharge"] >= 0, f"Negative CV: {metrics['cv_discharge']}"

    # Discharge values should be positive
    assert metrics["mean_discharge"] > 0
    assert metrics["median_discharge"] > 0


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
