"""Clean meteorological aggregation for watershed-scale analysis.

This module provides a streamlined approach to aggregating gridded climate data
over watershed geometries with proper unit handling and spatial weighting.

Core principles:
1. Precipitation/ET are DEPTH variables (mm/day) - aggregate via MEAN
2. Temperature/pressure are INTENSIVE variables - aggregate via MEAN
3. Unit conversion is explicit and separate from aggregation
4. Small watersheds use fractional area weights; large use simple spatial mean

Author: Refactored 2025-10
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from rioxarray.exceptions import NoDataInBounds
from shapely.geometry import Polygon, box
import xarray as xr

from src.data_processing.geom_functions import create_gdf, polygon_area
from src.data_processing.nc_proc import nc_by_extent
from src.utils.logger import setup_logger

logger = setup_logger(
    "MeteoAggregation", log_file="logs/meteo_aggregation.log"
)

# Constants
SMALL_WATERSHED_THRESHOLD_KM2 = (
    150.0  # Watersheds smaller than this use weights
)

# Dataset unit specifications (source → target)
DATASET_UNITS = {
    "era5_land": {
        "source_units": "m",  # meters per day
        "target_units": "mm",  # millimeters per day
        "conversion_factor": 100.0,  # m → mm
    },
    "mswep": {
        "source_units": "mm",
        "target_units": "mm",
        "conversion_factor": 1.0,
    },
    "gpcp": {
        "source_units": "mm",
        "target_units": "mm",
        "conversion_factor": 1.0,
    },
    "gleam": {
        "source_units": "m",  # meters per day (ET)
        "target_units": "mm",
        "conversion_factor": 1000.0,
    },
}


def get_unit_conversion(dataset: str) -> float:
    """Get unit conversion factor for dataset.

    Args:
        dataset: Dataset identifier (era5_land, mswep, gpcp, gleam).

    Returns:
        Conversion factor to apply to aggregated values.

    Raises:
        ValueError: If dataset is unknown.
    """
    if dataset not in DATASET_UNITS:
        msg = f"Unknown dataset: {dataset}. Supported: {list(DATASET_UNITS.keys())}"
        raise ValueError(msg)
    return DATASET_UNITS[dataset]["conversion_factor"]


def compute_fractional_weights(
    watershed_geom: Polygon,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
    grid_res: float,
) -> xr.DataArray:
    """Compute fractional area weights for watershed-grid cell intersections.

    For each grid cell, calculates what fraction of the watershed area it contains.
    Weights are normalized to sum to 1.0.

    Args:
        watershed_geom: Watershed polygon (EPSG:4326).
        grid_lats: Latitude coordinates of grid cells (degrees).
        grid_lons: Longitude coordinates of grid cells (degrees).
        grid_res: Grid resolution (degrees).

    Returns:
        DataArray with normalized weights (sum = 1.0).

    Notes:
        - Uses spherical geometry (polygon_area) for accurate area calculation
        - Weights represent fractional coverage per cell
        - Zero weights retained for spatial alignment
    """
    ws_area_km2 = polygon_area(watershed_geom)
    half_res = grid_res / 2.0

    # Build GeoDataFrame for watershed
    ws_gdf = create_gdf(watershed_geom)

    # Compute intersections for each grid cell
    weights_data = np.zeros((len(grid_lats), len(grid_lons)), dtype=np.float64)

    for i, lat in enumerate(grid_lats):
        for j, lon in enumerate(grid_lons):
            # Create grid cell polygon
            cell_poly = box(
                lon - half_res, lat - half_res, lon + half_res, lat + half_res
            )
            cell_gdf = create_gdf(cell_poly)

            # Compute intersection
            try:
                intersection = gpd.overlay(
                    ws_gdf, cell_gdf, how="intersection"
                )
                if not intersection.empty:
                    # Get intersection area in km² (extract Polygon from GeoSeries)
                    geom = intersection.loc[0, "geometry"]
                    if isinstance(geom, Polygon):
                        intersect_area_km2 = polygon_area(geom)
                        weights_data[i, j] = intersect_area_km2 / ws_area_km2
            except (KeyError, IndexError):
                weights_data[i, j] = 0.0

    # Normalize weights to sum to 1.0 (corrects for numerical precision)
    weight_sum = weights_data.sum()
    if weight_sum > 0:
        weights_data /= weight_sum
        logger.debug(
            f"Normalized weights (sum before: {weight_sum:.6f}, after: 1.0)"
        )

    # Create DataArray
    weights = xr.DataArray(
        weights_data,
        dims=("lat", "lon"),
        coords={"lat": grid_lats, "lon": grid_lons},
        name="weights",
        attrs={
            "description": "Fractional area weights for watershed aggregation",
            "normalization": "sum_to_one",
            "units": "dimensionless",
        },
    )

    return weights


def aggregate_small_watershed(
    ds: xr.Dataset,
    weights: xr.DataArray,
    dataset: str,
) -> xr.Dataset:
    """Aggregate meteorological data for small watershed using area weights.

    Uses weighted spatial mean where weights represent fractional cell coverage.

    Args:
        ds: Input xarray Dataset with meteorological variables.
        weights: Fractional area weights (normalized to sum=1).
        dataset: Dataset identifier for unit conversion.

    Returns:
        Aggregated Dataset with time dimension only.

    Notes:
        - All variables aggregated via weighted mean
        - Unit conversion applied ONLY to precipitation/ET variables
        - Temperature variables are NOT converted (already in correct units)
    """
    conversion = get_unit_conversion(dataset)

    # Variables that need unit conversion (precipitation, ET)
    conversion_vars = {
        "prcp",
        "precip",
        "precipitation",
        "tp",
        "et",
        "evap",
        "evaporation",
    }

    aggregated_vars = {}
    for var_name in ds.data_vars:
        # Weighted mean across spatial dimensions
        weighted_obj = ds[var_name].weighted(weights)
        mean_val = weighted_obj.mean(dim=("lat", "lon"))

        # Apply unit conversion ONLY to precipitation/ET variables
        if var_name.lower() in conversion_vars:
            aggregated_vars[var_name] = mean_val * conversion
        else:
            # Temperature and other intensive variables: no conversion
            aggregated_vars[var_name] = mean_val

    return xr.Dataset(aggregated_vars)


def aggregate_large_watershed(
    ds: xr.Dataset,
    watershed_geom: Polygon,
    dataset: str,
) -> xr.Dataset:
    """Aggregate meteorological data for large watershed using spatial mean.

    Clips data to watershed boundary and computes simple spatial mean.

    Args:
        ds: Input xarray Dataset with meteorological variables.
        watershed_geom: Watershed polygon for clipping (EPSG:4326).
        dataset: Dataset identifier for unit conversion.

    Returns:
        Aggregated Dataset with time dimension only.

    Notes:
        - Clips data to watershed boundary (all_touched=True)
        - Simple spatial mean (no weighting needed for large areas)
        - Unit conversion applied after aggregation
    """
    conversion = get_unit_conversion(dataset)

    # Set spatial dimensions and CRS for rioxarray
    ds.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=True)
    ds.rio.write_crs("epsg:4326", inplace=True)

    # Clip to watershed boundary
    ws_gdf = create_gdf(watershed_geom)
    try:
        ds_clipped = ds.rio.clip(
            ws_gdf.geometry, 4326, drop=True, all_touched=True
        )
    except NoDataInBounds:
        logger.warning(
            "No data in watershed bounds; using unclipped extent for aggregation"
        )
        ds_clipped = ds

    # Variables that need unit conversion (precipitation, ET)
    conversion_vars = {
        "prcp",
        "precip",
        "precipitation",
        "tp",
        "et",
        "evap",
        "evaporation",
    }

    # Compute spatial mean for all variables
    aggregated_vars = {}
    for var_name in ds_clipped.data_vars:
        mean_val = ds_clipped[var_name].mean(dim=("lat", "lon"))

        # Apply unit conversion ONLY to precipitation/ET variables
        if str(var_name).lower() in conversion_vars:
            aggregated_vars[var_name] = mean_val * conversion
        else:
            # Temperature and other intensive variables: no conversion
            aggregated_vars[var_name] = mean_val

    return xr.Dataset(aggregated_vars)


def _get_or_compute_weights(
    cache_dir: Path | None,
    gauge_id: str,
    grid_resolution: float,
    watershed_geom: Polygon,
    ds_extent: xr.Dataset,
) -> xr.DataArray:
    """Helper to get cached weights or compute new ones."""
    if cache_dir is None:
        return compute_fractional_weights(
            watershed_geom,
            ds_extent.lat.values,
            ds_extent.lon.values,
            grid_resolution,
        )

    weight_path = (
        cache_dir / "weights" / f"{grid_resolution:.2f}" / f"{gauge_id}.nc"
    )
    weight_path.parent.mkdir(parents=True, exist_ok=True)

    if weight_path.exists():
        logger.debug(f"Loading cached weights: {weight_path}")
        return xr.open_dataarray(weight_path)

    weights = compute_fractional_weights(
        watershed_geom,
        ds_extent.lat.values,
        ds_extent.lon.values,
        grid_resolution,
    )
    weights.to_netcdf(weight_path)
    logger.debug(f"Saved weights to: {weight_path}")
    return weights


def _detect_time_coord(ds: xr.Dataset) -> str:
    """Detect time coordinate in dataset."""
    for coord in ("time", "valid_time", "date"):
        if coord in ds.coords:
            return coord
    raise ValueError("No time coordinate found in dataset")


def _postprocess_dataframe(df: pd.DataFrame, time_coord: str) -> pd.DataFrame:
    """Clean up aggregated DataFrame."""
    # Rename time coordinate to 'date'
    if time_coord != "date":
        df.rename(columns={time_coord: "date"}, inplace=True)

    df.set_index("date", inplace=True)

    # Clip precipitation/ET to non-negative (physical constraint)
    for col in df.columns:
        if col in ("prcp", "precip", "precipitation", "et", "evap"):
            df[col] = df[col].clip(lower=0.0)

    # Remove spatial_ref if present (metadata column)
    if "spatial_ref" in df.columns:
        df.drop("spatial_ref", axis=1, inplace=True)

    return df


def aggregate_watershed(
    dataset_path: Path,
    watershed_geom: Polygon,
    gauge_id: str,
    dataset_type: str,
    grid_resolution: float = 0.10,
    small_ws_threshold: float = SMALL_WATERSHED_THRESHOLD_KM2,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    """Aggregate gridded meteorological data to watershed scale.

    Main entry point for watershed aggregation. Automatically selects weighted
    aggregation (small) or simple spatial aggregation (large) based on area.

    Args:
        dataset_path: Path to input NetCDF file.
        watershed_geom: Watershed polygon geometry (EPSG:4326).
        gauge_id: Gauge identifier for logging and caching.
        dataset_type: Dataset type (era5_land, mswep, gpcp, gleam).
        grid_resolution: Grid resolution in degrees (default: 0.10).
        small_ws_threshold: Area threshold for small watershed in km² (default: 5.0).
        cache_dir: Optional directory for caching weights (NetCDF format).

    Returns:
        Aggregated DataFrame with DatetimeIndex.

    Raises:
        ValueError: If dataset_type is unknown.
        FileNotFoundError: If dataset_path does not exist.

    Notes:
        - Small watersheds (<threshold): weighted mean with fractional coverage
        - Large watersheds (≥threshold): simple spatial mean over clipped extent
        - All precipitation/ET values clipped to non-negative
        - Results include proper unit conversion (e.g., m → mm)
    """
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    # Load and clip data to watershed extent
    with xr.open_dataset(dataset_path) as ds:
        ds_extent = nc_by_extent(
            nc=ds,
            shape=watershed_geom,
            grid_res=grid_resolution,
            dataset=dataset_type,
        )

    # Calculate watershed area and detect time coordinate
    ws_area_km2 = polygon_area(watershed_geom)
    time_coord = _detect_time_coord(ds_extent)

    # Select aggregation method based on watershed size
    if ws_area_km2 < small_ws_threshold:
        weights = _get_or_compute_weights(
            cache_dir, gauge_id, grid_resolution, watershed_geom, ds_extent
        )
        ds_masked = ds_extent.where(weights > 0)
        agg_ds = aggregate_small_watershed(ds_masked, weights, dataset_type)
    else:
        agg_ds = aggregate_large_watershed(
            ds_extent, watershed_geom, dataset_type
        )

    # Convert to DataFrame and postprocess
    df = agg_ds.to_dataframe().reset_index()
    df = _postprocess_dataframe(df, time_coord)

    return df
