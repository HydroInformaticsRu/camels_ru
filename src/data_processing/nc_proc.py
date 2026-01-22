from collections.abc import Generator
from pathlib import Path
import sys

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon
import xarray as xr

sys.path.append(str(Path(__file__).parent.parent))

from src.data_processing.geom_functions import (
    create_gdf,
    find_extent,
    poly_from_multipoly,
)


def nc_by_extent(nc: xr.Dataset, shape: Polygon, grid_res: float, dataset: str = "") -> xr.Dataset:
    """Select net_cdf by extent of given shape. Return masked net_cdf.

    Args:
        nc (xr.Dataset): net_cdf dataset
        shape (Polygon): shape of the area of interest
        grid_res (float): grid resolution in decimal degrees
        dataset (str, optional): dataset name. Defaults to "".

    Returns:
        xr.Dataset: masked net_cdf dataset

    """
    # rename latitude and longitude if necessary
    if "latitude" in nc.dims:
        nc = nc.rename({"latitude": "lat", "longitude": "lon"})
    else:
        pass

    # find biggest polygon
    big_shape = poly_from_multipoly(geom=shape)

    # find extent coordinates
    min_lon, max_lon, min_lat, max_lat = find_extent(ws=big_shape, grid_res=grid_res, dataset=dataset)

    # select nc inside of extent
    masked_nc = (
        nc.where(nc.lat >= min_lat, drop=True)
        .where(nc.lat <= max_lat, drop=True)
        .where(nc.lon >= min_lon, drop=True)
        .where(nc.lon <= max_lon, drop=True)
    )
    # masked_nc = masked_nc.chunk(chunks="auto")
    return masked_nc


def aggregation_definer(dataset: str, variable: str):
    """Determine aggregation method (sum or mean) for a variable based on dataset and variable name.

    Args:
        dataset (str): Dataset name (e.g., 'gleam').
        variable (str): Variable name to inspect.

    Returns:
        str: 'sum' for accumulative variables, otherwise 'mean'.
    """
    if dataset == "gleam":
        return "sum"
    elif (
        ("precipitation" in variable)
        | ("evaporation" in variable)
        | ("tot_prec" in variable)
        | ("pr" in variable)
        | ("prcp" in variable)
    ):
        return "sum"
    else:
        return "mean"


def make_intersected_generator(
    inter: list[gpd.GeoDataFrame],
) -> Generator[pd.DataFrame | gpd.GeoDataFrame, None, None]:
    """Create a generator that returns a geodataframe.

    For each section in the passed list of intersections (inter).
    This geodataframe is empty if the section is empty
    contains the geometry of the largest feature in that section otherwise.

    Args:
    ----
        inter (list[gpd.GeoDataFrame]) : list with geoDataFrames

    Returns:
    -------
        _type_: Generator[gpd.GeoDataFrame]

    """
    return (
        create_gdf(poly_from_multipoly(section.loc[0, "geometry"]))
        if len(section) != 0
        else gpd.GeoDataFrame()
        for section in inter
    )
