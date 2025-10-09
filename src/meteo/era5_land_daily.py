from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from rioxarray.exceptions import NoDataInBounds
from shapely.geometry import Polygon, box
import xarray as xr

from src.data_processing.geom_functions import create_gdf, polygon_area
from src.data_processing.nc_proc import aggregation_definer, make_intersected_generator, nc_by_extent
from src.utils.logger import setup_logger

logger = setup_logger("Era5LandGauge", log_file="logs/era5_land_gauge.log")

SMALL_WS_THRESHOLD = 5e2  # m²
PRECIP_COL = "prcp"


def _write_or_merge_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = pd.read_csv(path, index_col="date", parse_dates=True)
        df = df.combine_first(old).sort_index()
    df.to_csv(path)


def _detect_time_coord(ds: xr.Dataset) -> str:
    # Prefer common names
    for cand in ("time", "valid_time", "date"):
        if cand in ds.coords and np.issubdtype(ds[cand].dtype, np.datetime64):
            return cand
    # Fallback: first datetime-like coord
    for c in ds.coords:
        if np.issubdtype(ds[c].dtype, np.datetime64):
            return c
    raise ValueError("No datetime coordinate found.")


def get_weights(
    weight_path: Path,
    mask_nc: xr.Dataset,
    ws_geom: Polygon,
    ws_area: float,
    grid_res: float = 0.05,
) -> xr.DataArray:
    """Build or load spatial weights (fractional area of watershed per grid cell)."""
    if weight_path.is_file():
        return xr.open_dataarray(weight_path)

    weight_path.parent.mkdir(parents=True, exist_ok=True)

    ws_gdf = create_gdf(ws_geom)
    lats = mask_nc.lat.values
    lons = mask_nc.lon.values
    n_lat, n_lon = len(lats), len(lons)

    # Build grid cell polygons (shapely.box is faster than custom vertex builder)
    half = grid_res / 2.0
    polygons_gdfs = []
    for lat in lats:
        row = []
        for lon in lons:
            cell_poly = box(lon - half, lat - half, lon + half, lat + half)
            row.append(create_gdf(cell_poly))
        polygons_gdfs.append(row)

    # Intersections
    intersections = []
    for row in polygons_gdfs:
        for cell in row:
            try:
                intersections.append(gpd.overlay(ws_gdf, cell, how="intersection"))
            except KeyError:
                intersections.append(gpd.GeoDataFrame())

    # Area fractions
    fractions = np.fromiter(
        (
            0.0 if sect.empty else polygon_area(sect.loc[0, "geometry"]) / ws_area
            for sect in make_intersected_generator(intersections)
        ),
        dtype=float,
        count=n_lat * n_lon,
    ).reshape((n_lat, n_lon))

    weights = xr.DataArray(
        fractions, dims=("lat", "lon"), coords={"lat": lats, "lon": lons}, name="weights"
    )
    # Drop zero cells (optional) then fill (retain full grid shape if desired)
    weights = weights.where(weights > 0, other=0.0)

    weights.to_netcdf(weight_path)
    return weights


def _aggregate_small_ws(ds: xr.Dataset, weights: xr.DataArray) -> xr.Dataset:
    """Weighted aggregation for small watershed (fractional cell coverage).

    Sum variables scaled by 1e2 (original logic) else weighted mean.
    """
    data_vars = {}
    for var in ds.data_vars:
        agg_type = aggregation_definer(dataset="era5_land", variable=var)
        wobj = ds[var].weighted(weights)
        if agg_type == "sum":
            data_vars[var] = wobj.sum(dim=("lat", "lon")) * 1e2
        else:
            data_vars[var] = wobj.mean(dim=("lat", "lon"))
    return xr.Dataset(data_vars)


def _aggregate_large_ws(ds: xr.Dataset, ws_area: float) -> xr.Dataset:
    """Simple spatial aggregation for large watershed.

    Sum variables converted to depth over watershed ( *1e4 / area ), else mean.
    """
    area_factor = 1e4 / ws_area  # maintain prior scaling
    data_vars = {}
    for var in ds.data_vars:
        agg_type = aggregation_definer(dataset="era5_land", variable=var)
        if agg_type == "sum":
            data_vars[var] = ds[var].sum(dim=("lat", "lon")) * area_factor
        else:
            data_vars[var] = ds[var].mean(dim=("lat", "lon"))
    return xr.Dataset(data_vars)


def era5_ws(
    initial_nc: xr.Dataset,
    ws_geom: Polygon,
    gauge_id: str,
    path_to_results: Path,
    grid_res: float = 0.10,
) -> pd.DataFrame:
    """Aggregate ERA5-Land variables over a watershed (weighted for small basins)."""
    path_to_results.mkdir(exist_ok=True, parents=True)

    ws_area = polygon_area(ws_geom)
    ds = nc_by_extent(nc=initial_nc, shape=ws_geom, grid_res=grid_res, dataset="era5_land")

    if ws_area < SMALL_WS_THRESHOLD:
        weights_path = path_to_results / "weights" / f"{grid_res}" / f"{gauge_id}.nc"
        weights = get_weights(
            weight_path=weights_path,
            mask_nc=ds,
            ws_geom=ws_geom,
            ws_area=ws_area,
            grid_res=grid_res,
        )
        # restrict dataset to cells with weight > 0 to speed up weighted ops
        ds_sub = ds.where(weights > 0)
        agg_ds = _aggregate_small_ws(ds_sub, weights)
        time_coord = _detect_time_coord(ds)
        agg_ds = agg_ds.assign_coords({time_coord: ds[time_coord]})
    else:
        # Clip
        ds.rio.set_spatial_dims(x_dim="lon", y_dim="lat", inplace=True)
        ds.rio.write_crs("epsg:4326", inplace=True)
        try:
            ds_clip = ds.rio.clip(create_gdf(ws_geom).geometry, 4326, drop=True, all_touched=True)
        except NoDataInBounds:
            ds_clip = ds
        agg_ds = _aggregate_large_ws(ds_clip, ws_area)
        time_coord = _detect_time_coord(ds_clip)
        agg_ds = agg_ds.assign_coords({time_coord: ds_clip[time_coord]})

    # Build DataFrame
    df = agg_ds.to_dataframe().reset_index()
    df.rename(columns={time_coord: "date"}, inplace=True)

    if PRECIP_COL in df.columns:
        df[PRECIP_COL] = df[PRECIP_COL].clip(lower=0)

    df.set_index("date", inplace=True)
    if "spatial_ref" in df.columns:
        df.drop("spatial_ref", axis=1, inplace=True)
    out_csv = path_to_results / f"{gauge_id}.csv"
    _write_or_merge_csv(out_csv, df)

    return df
