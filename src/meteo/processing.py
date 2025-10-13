"""Meteorological data processing utilities for watershed aggregation.

This module provides functions for aggregating gridded meteorological data
(ERA5-Land, GPCP, GLEAM, etc.) over watershed geometries. It supports both
weighted aggregation for small watersheds and simple spatial aggregation for
large watersheds.

Key concepts:
- Small watersheds (<5km²): Use fractional area weighting per grid cell
- Large watersheds (≥5km²): Use simple spatial aggregation with clipping
- Scaling coefficients convert between units (e.g., kg/m²/s to mm/day)

Scaling coefficient guidelines:
- ERA5-Land precipitation: 1e2 (converts m to mm, accounting for timestep)
- MSWEP precipitation: 1e0 (already in mm)
- GPCP precipitation: 1e1 (converts mm/hr * 24hr to mm/day)
- Area coefficient for depth conversion: 1e4 (cm²/m²) for ERA5/MSWEP, 1e3 for GPCP
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
from src.data_processing.nc_proc import (
    aggregation_definer,
    make_intersected_generator,
    nc_by_extent,
)
from src.utils.logger import setup_logger

logger = setup_logger("MeteoProcessing", log_file="logs/meteo_processing.log")

# Default thresholds and constants
DEFAULT_SMALL_WS_THRESHOLD = 5e3  # m² (5 km²)
DEFAULT_PRECIP_COL = "precip"

# Dataset-specific scaling coefficients
DATASET_SCALING = {
    "era5_land": {"precip": 1e2, "area": 1e4},
    "mswep": {"precip": 1e0, "area": 1e2},
    "gpcp": {"precip": 1e1, "area": 1e3},
    "gleam": {"precip": 1e0, "area": 1e4},
}


def get_scaling_coefficients(
    dataset: str,
) -> tuple[float, float]:
    """Retrieve scaling coefficients for a given dataset.

    Args:
        dataset: Dataset name (era5_land, mswep, gpcp, gleam).

    Returns:
        Tuple of (precipitation_coefficient, area_coefficient).

    Raises:
        ValueError: If dataset is not recognized.
    """
    if dataset not in DATASET_SCALING:
        raise ValueError(f"Unknown dataset: {dataset}. Supported: {list(DATASET_SCALING.keys())}")
    return (
        DATASET_SCALING[dataset]["precip"],
        DATASET_SCALING[dataset]["area"],
    )


def detect_time_coord(ds: xr.Dataset) -> str:
    """Detect the time coordinate in an xarray Dataset.

    Args:
        ds: Input xarray Dataset.

    Returns:
        Name of the time coordinate.

    Raises:
        ValueError: If no datetime coordinate is found.
    """
    # Prefer common names
    for cand in ("time", "valid_time", "date"):
        if cand in ds.coords and np.issubdtype(ds[cand].dtype, np.datetime64):
            return cand
    # Fallback: first datetime-like coord
    for coord_name in ds.coords:
        if np.issubdtype(ds[coord_name].dtype, np.datetime64):
            return str(coord_name)
    raise ValueError("No datetime coordinate found in dataset.")


def write_or_merge_csv(path: Path, df: pd.DataFrame) -> None:
    """Write DataFrame to CSV, merging with existing data if present.

    Args:
        path: Output CSV file path.
        df: DataFrame to write (must have 'date' index).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = pd.read_csv(path, index_col="date", parse_dates=True)
        df = df.combine_first(old).sort_index()
    df.to_csv(path)


def compute_weights(
    weight_path: Path,
    mask_nc: xr.Dataset,
    ws_geom: Polygon,
    ws_area: float,
    grid_res: float = 0.05,
) -> xr.DataArray:
    """Build or load spatial weights for watershed aggregation.

    Computes fractional area of watershed per grid cell, accounting for
    partial cell coverage at watershed boundaries.

    Args:
        weight_path: Path to save/load weights NetCDF.
        mask_nc: Clipped NetCDF dataset with lat/lon coordinates.
        ws_geom: Watershed polygon geometry (EPSG:4326).
        ws_area: Watershed area in m².
        grid_res: Grid resolution in decimal degrees (default: 0.05).

    Returns:
        DataArray with weights (fractional coverage per cell).

    Notes:
        - Cached weights are reused if file exists
        - Zero-weight cells are retained (for spatial alignment)
        - Uses spherical geometry via polygon_area for accuracy
    """
    if weight_path.is_file():
        logger.debug(f"Loading cached weights from {weight_path}")
        return xr.open_dataarray(weight_path)

    weight_path.parent.mkdir(parents=True, exist_ok=True)

    ws_gdf = create_gdf(ws_geom)
    lats = mask_nc.lat.values
    lons = mask_nc.lon.values
    n_lat, n_lon = len(lats), len(lons)

    # Build grid cell polygons (shapely.box is faster)
    half = grid_res / 2.0
    polygons_gdfs = []
    for lat in lats:
        row = []
        for lon in lons:
            cell_poly = box(lon - half, lat - half, lon + half, lat + half)
            row.append(create_gdf(cell_poly))
        polygons_gdfs.append(row)

    # Compute intersections
    intersections = []
    for row in polygons_gdfs:
        for cell in row:
            try:
                intersections.append(gpd.overlay(ws_gdf, cell, how="intersection"))
            except KeyError:
                intersections.append(gpd.GeoDataFrame())

    # Compute area fractions
    fractions = np.fromiter(
        (
            0.0 if sect.empty else float(polygon_area(sect.loc[0, "geometry"])) / ws_area
            for sect in make_intersected_generator(intersections)
        ),
        dtype=float,
        count=n_lat * n_lon,
    ).reshape((n_lat, n_lon))

    weights = xr.DataArray(
        fractions,
        dims=("lat", "lon"),
        coords={"lat": lats, "lon": lons},
        name="weights",
    )
    # Retain zero cells for spatial alignment
    weights = weights.where(weights > 0, other=0.0)

    weights.to_netcdf(weight_path)
    logger.info(f"Saved weights to {weight_path}")
    return weights


def aggregate_small_watershed(
    ds: xr.Dataset,
    weights: xr.DataArray,
    dataset: str,
    precip_coeff: float | None = None,
) -> xr.Dataset:
    """Weighted aggregation for small watershed (fractional cell coverage).

    Args:
        ds: Input xarray Dataset.
        weights: Spatial weights (fractional area per cell).
        dataset: Dataset name for aggregation method selection.
        precip_coeff: Precipitation scaling coefficient (if None, use dataset default).

    Returns:
        Aggregated xarray Dataset.

    Notes:
        - Sum variables: weighted sum * precip_coeff
        - Mean variables: weighted mean (no scaling)
    """
    if precip_coeff is None:
        precip_coeff, _ = get_scaling_coefficients(dataset)

    data_vars = {}
    for var in ds.data_vars:
        agg_type = aggregation_definer(dataset=dataset, variable=str(var))
        wobj = ds[var].weighted(weights)
        if agg_type == "sum":
            data_vars[var] = wobj.sum(dim=("lat", "lon")) * precip_coeff
        else:
            data_vars[var] = wobj.mean(dim=("lat", "lon"))
    return xr.Dataset(data_vars)


def aggregate_large_watershed(
    ds: xr.Dataset,
    ws_area: float,
    dataset: str,
    area_coeff: float | None = None,
) -> xr.Dataset:
    """Simple spatial aggregation for large watershed.

    Args:
        ds: Input xarray Dataset (already clipped to watershed).
        ws_area: Watershed area in m².
        dataset: Dataset name for aggregation method selection.
        area_coeff: Area scaling coefficient (if None, use dataset default).

    Returns:
        Aggregated xarray Dataset.

    Notes:
        - Sum variables: spatial sum * area_coeff / ws_area (converts to depth)
        - Mean variables: spatial mean (no scaling)
    """
    if area_coeff is None:
        _, area_coeff = get_scaling_coefficients(dataset)

    area_factor = area_coeff / ws_area
    data_vars = {}
    for var in ds.data_vars:
        agg_type = aggregation_definer(dataset=dataset, variable=str(var))
        if agg_type == "sum":
            data_vars[var] = ds[var].sum(dim=("lat", "lon")) * area_factor
        else:
            data_vars[var] = ds[var].mean(dim=("lat", "lon"))
    return xr.Dataset(data_vars)


def aggregate_to_watershed(
    nc: xr.Dataset,
    ws_geom: Polygon,
    gauge_id: str,
    output_path: Path,
    dataset: str = "era5_land",
    grid_res: float = 0.10,
    small_ws_threshold: float = DEFAULT_SMALL_WS_THRESHOLD,
    precip_col: str = DEFAULT_PRECIP_COL,
    precip_coeff: float | None = None,
    area_coeff: float | None = None,
) -> pd.DataFrame:
    """Aggregate gridded meteorological data over a watershed.

    Automatically selects weighted aggregation (small watersheds) or simple
    spatial aggregation (large watersheds) based on watershed area.

    Args:
        nc: Input NetCDF dataset (xarray Dataset).
        ws_geom: Watershed polygon geometry (EPSG:4326).
        gauge_id: Gauge identifier for output file naming.
        output_path: Directory path for output CSV files.
        dataset: Dataset name (era5_land, mswep, gpcp, gleam).
        grid_res: Grid resolution in decimal degrees (default: 0.10).
        small_ws_threshold: Threshold for small watershed in m² (default: 5000).
        precip_col: Name of precipitation column for clipping (default: "precip").
        precip_coeff: Override precipitation scaling coefficient (optional).
        area_coeff: Override area scaling coefficient (optional).

    Returns:
        Aggregated DataFrame with date index.

    Raises:
        ValueError: If dataset is unknown or no data in bounds.

    Notes:
        - Small watersheds use fractional area weighting
        - Large watersheds use simple spatial mean/sum
        - Precipitation values are clipped to non-negative
        - Results are saved to CSV (merged if file exists)
    """
    output_path.mkdir(exist_ok=True, parents=True)

    ws_area = polygon_area(ws_geom)
    ds = nc_by_extent(nc=nc, shape=ws_geom, grid_res=grid_res, dataset=dataset)

    if ws_area < small_ws_threshold:
        logger.info(f"Gauge {gauge_id}: Small watershed ({ws_area:.1f} m²) - using weighted aggregation")
        weights_path = output_path / "weights" / f"{grid_res}" / f"{gauge_id}.nc"
        weights = compute_weights(
            weight_path=weights_path,
            mask_nc=ds,
            ws_geom=ws_geom,
            ws_area=ws_area,
            grid_res=grid_res,
        )
        # Restrict to cells with weight > 0 for efficiency
        ds_sub = ds.where(weights > 0)
        agg_ds = aggregate_small_watershed(ds_sub, weights, dataset, precip_coeff)
        time_coord = detect_time_coord(ds)
        agg_ds = agg_ds.assign_coords({time_coord: ds[time_coord]})
    else:
        logger.info(f"Gauge {gauge_id}: Large watershed ({ws_area:.1f} m²) - using spatial aggregation")
        # Clip to watershed boundary
        ds.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=True)
        ds.rio.write_crs("epsg:4326", inplace=True)
        try:
            ds_clip = ds.rio.clip(
                create_gdf(ws_geom).geometry,
                4326,
                drop=True,
                all_touched=True,
            )
        except NoDataInBounds:
            logger.warning(f"Gauge {gauge_id}: No data in bounds, using unclipped extent")
            ds_clip = ds
        agg_ds = aggregate_large_watershed(ds_clip, ws_area, dataset, area_coeff)
        time_coord = detect_time_coord(ds_clip)
        agg_ds = agg_ds.assign_coords({time_coord: ds_clip[time_coord]})

    # Build DataFrame
    df = agg_ds.to_dataframe().reset_index()
    df.rename(columns={time_coord: "date"}, inplace=True)

    # Clip precipitation to non-negative
    if precip_col in df.columns:
        df[precip_col] = df[precip_col].clip(lower=0)

    df.set_index("date", inplace=True)
    if "spatial_ref" in df.columns:
        df.drop("spatial_ref", axis=1, inplace=True)

    out_csv = output_path / f"{gauge_id}.csv"
    write_or_merge_csv(out_csv, df)

    return df
