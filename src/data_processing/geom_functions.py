"""Geometric helper functions.

All areas returned in square kilometers (km^2) unless stated otherwise.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from functools import reduce
from itertools import chain, product
import math
from pathlib import Path

import geopandas as gpd
from numba import jit
import numpy as np
from numpy import append, arctan2, cos, diff, pi, radians, sin, sqrt
from shapely.geometry import MultiPolygon, Point, Polygon, base

__all__ = [
    "area_from_gdf",
    "find_float_len",
    "min_max_xy",
    "polygon_area",
    "poly_from_multipoly",
    "round_up",
    "round_down",
    "find_extent",
    "round_nearest",
    "create_gdf",
    "RotM",
    "getSquareVertices",
    "point_distance",
    "inside_mask",
    "get_river_points",
    "str_to_np",
    "update_geometry",
]


# ---------------------------------------------------------------------------
# Area / polygon utilities
# ---------------------------------------------------------------------------


def area_from_gdf(gdf: gpd.GeoDataFrame) -> float:
    """Calculate the area of the (first) geometry in a GeoDataFrame.

    Parameters
    ----------
    gdf : GeoDataFrame
        GeoDataFrame containing at least one geometry (Polygon or MultiPolygon) in EPSG:4326.

    Returns:
    -------
    float
        Area in km^2. np.nan if empty.
    """
    if gdf.empty or "geometry" not in gdf:
        return float("nan")

    geom = gdf.geometry.iloc[0]
    geom = poly_from_multipoly(geom)
    return polygon_area(geom)


def find_float_len(number: float) -> bool:
    """Return True if number has at least two digits after decimal point.

    (Name kept for backward compatibility; function returns a boolean.)
    """
    parts = f"{number}".split(".")
    if len(parts) == 1:
        return False
    return len(parts[1]) >= 2


def min_max_xy(poly: Polygon) -> tuple[float, float, float, float]:
    """Return bounding box (x_min, y_min, x_max, y_max) for a polygon."""
    xs, ys = poly.exterior.xy  # type: ignore
    return (float(np.min(xs)), float(np.min(ys)), float(np.max(xs)), float(np.max(ys)))


def polygon_area(geo_shape: Polygon, radius: float = 6_378_137.0) -> float:
    """Approximate area of a (multi)polygon on a sphere (spherical excess / Green's theorem).

    Parameters
    ----------
    geo_shape : Polygon
        Polygon in longitude/latitude degrees (EPSG:4326).
    radius : float, default 6378137.0
        Radius of sphere in meters.

    Returns:
    -------
    float
        Area in km^2.
    """
    lons, lats = geo_shape.exterior.xy
    lats_rad, lons_rad = np.deg2rad(lats), np.deg2rad(lons)

    if lats_rad[0] != lats_rad[-1] or lons_rad[0] != lons_rad[-1]:
        lats_rad = append(lats_rad, lats_rad[0])
        lons_rad = append(lons_rad, lons_rad[0])

    a = sin(lats_rad / 2) ** 2 + cos(lats_rad) * sin(lons_rad / 2) ** 2
    colat = 2 * arctan2(sqrt(a), sqrt(1 - a))
    az = arctan2(cos(lats_rad) * sin(lons_rad), sin(lats_rad)) % (2 * pi)

    daz = diff(az)
    daz = (daz + pi) % (2 * pi) - pi

    deltas = diff(colat) / 2
    colat_m = colat[:-1] + deltas
    integrands = (1 - cos(colat_m)) * daz

    spherical_excess_ratio = abs(np.sum(integrands)) / (4 * pi)
    spherical_excess_ratio = min(spherical_excess_ratio, 1 - spherical_excess_ratio)

    return spherical_excess_ratio * 4 * pi * (radius**2) / 1e6  # km^2


def poly_from_multipoly(geom: base.BaseGeometry) -> Polygon:
    """Return biggest polygon if input is MultiPolygon; else return input.

    Parameters
    ----------
    geom : Polygon | MultiPolygon

    Returns:
    -------
    Polygon
    """
    if isinstance(geom, MultiPolygon):
        # Use shapely area in degrees (not meaningful) replaced by spherical area for consistency
        areas = [polygon_area(p) for p in geom.geoms]
        geom = geom.geoms[int(np.argmax(areas))]
    if not isinstance(geom, Polygon):
        raise TypeError("Geometry must be Polygon or MultiPolygon.")
    return geom


# ---------------------------------------------------------------------------
# AOI and bounding helpers
# ---------------------------------------------------------------------------


def round_up(x: float, round_val: float = 5) -> int:
    """Round up to nearest multiple of round_val."""
    return int(np.ceil(x / round_val)) * int(round_val)


def round_down(x: float, round_val: float = 5) -> int:
    """Round down to nearest multiple of round_val."""
    return int(np.floor(x / round_val)) * int(round_val)


def find_extent(ws: Polygon, grid_res: float, dataset: str = "") -> list[float]:
    """Determine extent [min_lon, max_lon, min_lat, max_lat] snapped to grid resolution.

    Parameters
    ----------
    ws : Polygon
    grid_res : float
        Grid resolution (deg).
    dataset : str
        Special handling if 'gpcp'.

    Returns:
    -------
    list[float]
    """
    lons, lats = ws.exterior.xy  # type: ignore
    max_lat, max_lon = max(lats), max(lons)
    min_lat, min_lon = min(lats), min(lons)

    if dataset == "gpcp":
        return [round((x - 0.25) * 2) / 2 + 0.25 for x in [min_lon, max_lon, min_lat, max_lat]]
    if dataset:
        min_lon = round_nearest(min_lon, grid_res)
        max_lon = round_nearest(max_lon, grid_res)
        min_lat = round_nearest(min_lat, grid_res)
        max_lat = round_nearest(max_lat, grid_res)

        if abs(min_lon - max_lon) <= grid_res * 2:
            max_lon = round_nearest(max_lon + grid_res, grid_res)
            min_lon = round_nearest(min_lon - grid_res, grid_res)
        if abs(min_lat - max_lat) <= grid_res * 2:
            max_lat = round_nearest(max_lat + grid_res, grid_res)
            min_lat = round_nearest(min_lat - grid_res, grid_res)
        return [min_lon, max_lon, min_lat, max_lat]

    raise ValueError(f"Invalid dataset argument: '{dataset}' with grid_res={grid_res}")


def round_nearest(x: float, a: float) -> float:
    """Round x to nearest multiple of a while preserving reasonable decimal precision.

    Parameters
    ----------
    x : float
    a : float

    Returns:
    -------
    float
    """
    if a == 0:
        return x
    q = round(x / a) * a
    # Determine decimals from a (e.g., 0.25 -> 2 decimals)
    if a >= 1:
        return round(q)
    decimals = max(0, -int(math.floor(math.log(a))))
    # Add one extra decimal to mitigate FP artifacts
    return round(q, decimals + 1)


def create_gdf(shape: Polygon | MultiPolygon) -> gpd.GeoDataFrame:
    """Create a GeoDataFrame (EPSG:4326) containing provided shape (largest polygon if MultiPolygon)."""
    polygon = poly_from_multipoly(shape)
    return gpd.GeoDataFrame({"geometry": [polygon]}, crs="EPSG:4326")


def gauge_buffer_creator(
    gauge_geometry: Point,
    ws_gdf: gpd.GeoSeries | gpd.GeoDataFrame,
    tif_epsg: int,
    area_size: float = 0.0,
) -> tuple[gpd.GeoDataFrame, tuple[float, float, float, float], float, float]:
    """Create a square buffer for flood modelling extent around a gauge point.

    Args:
        gauge_geometry (Point): Shapely Point object from geometry column.
        ws_gdf (gpd.GeoSeries | gpd.GeoDataFrame): Watershed geometry for the gauge.
        tif_epsg (int): Metric EPSG code for area calculation.
        area_size (float): Size of the buffer area around the gauge point.

    Returns:
        tuple: (
            buffer_gdf (gpd.GeoDataFrame): Buffer for river intersection search,
            wgs_window (tuple[float, float, float, float]): Extent coordinates (minx, maxy, maxx, miny),
            acc_coef (float): Number of 90m cells in the watershed,
            ws_area (float): Watershed area in sq. km
        )

    Raises:
        ValueError: If input geometry is invalid.
    """
    # Calculate watershed area in square kilometers
    ws_area = ws_gdf.to_crs(epsg=tif_epsg).geometry.area.iloc[0] * 1e-6
    if area_size == 0.0:
        # Determine buffer size in degrees based on area
        if ws_area > 500_000:
            area_size = 0.30
        elif ws_area > 50_000:
            area_size = 0.20
        elif ws_area > 5_000:
            area_size = 0.5
        else:
            area_size = 0.05

    # Calculate number of 90m cells in the watershed
    acc_coef = (ws_area * 1e6) / (90 * 90)

    # Create square buffer for extent and for river intersection search
    buffer = gauge_geometry.buffer(area_size, cap_style="square")
    buffer_isc = gauge_geometry.buffer(area_size - 0.015, cap_style="square")

    # Create GeoDataFrame for buffer_isc
    buffer_gdf = gpd.GeoDataFrame(geometry=[buffer_isc], crs="EPSG:4326")

    # Get bounds: (minx, miny, maxx, maxy)
    minx, miny, maxx, maxy = buffer.bounds
    # Return as (minx, maxy, maxx, miny) for wgs_window
    wgs_window = (minx, maxy, maxx, miny)

    return buffer_gdf, wgs_window, acc_coef, ws_area


# ---------------------------------------------------------------------------
# Geometry construction helpers
# ---------------------------------------------------------------------------


def RotM(alpha: float) -> np.ndarray:
    """Return 2x2 rotation matrix for angle alpha (radians)."""
    sa, ca = np.sin(alpha), np.cos(alpha)
    return np.array([[ca, -sa], [sa, ca]])


def getSquareVertices(center: Iterable[float], side: float, phi: float) -> np.ndarray:
    """Return vertices (4x2) of a rotated square.

    Parameters
    ----------
    center : (x, y)
    side : float
        Side length.
    phi : float
        Rotation radians.
    """
    c = np.asarray(center)
    half = np.ones(2) * side
    return np.asarray([c + reduce(np.dot, [RotM(phi), RotM(np.pi / 2 * i), half]) for i in range(4)])


# ---------------------------------------------------------------------------
# Distance / selection helpers
# ---------------------------------------------------------------------------


@jit(nopython=True, fastmath=True)
def point_distance(new_lon: float, new_lat: float, old_lon: float, old_lat: float) -> float:
    """Great-circle distance (Haversine) between two points given in radians.

    Returns km.
    """
    dlon = old_lon - new_lon
    dlat = old_lat - new_lat
    a = sin(dlat / 2) ** 2 + cos(old_lat) * cos(new_lat) * sin(dlon / 2) ** 2
    c = 2 * arctan2(sqrt(a), sqrt(1 - a))
    return 6371.0088 * c  # WGS84 mean radius


def inside_mask(pt: tuple[float, float], bbox: tuple[float, float, float, float]) -> bool:
    """Check if point (x,y) strictly inside bounding box (x1,y1,x2,y2)."""
    x1, y1, x2, y2 = bbox
    x, y = pt
    return x1 < x < x2 and y1 < y < y2


def get_river_points(pnt, partial_path: str) -> str | None:
    """Find river tile file containing point (approx, based on naming scheme).

    Parameters
    ----------
    pnt : shapely Point
    partial_path : str
        Root path containing 'partial' subfolders.

    Returns:
    -------
    str | None
        Path to gpkg file or None if not found.
    """
    lon_txt = round_down(pnt.x, round_val=0.5)
    lat_txt = round_up(pnt.y, round_val=0.5)

    base_dir = Path(partial_path) / "partial"
    if not base_dir.is_dir():
        return None

    for subfolder in (p for p in base_dir.iterdir() if p.is_dir()):
        tag = subfolder.name
        candidate = base_dir / tag / f"{tag}_{lon_txt}_{lat_txt}.gpkg"
        if candidate.exists():
            return str(candidate)
    return None


# ---------------------------------------------------------------------------
# Data conversion & update helpers
# ---------------------------------------------------------------------------


def gauge_to_utm(
    gauge_series: gpd.GeoSeries, return_gdf: bool = False
) -> tuple[gpd.GeoDataFrame, int] | Point | None:
    """Project a gauge geometry from WGS84 to its appropriate UTM zone.

    Args:
        gauge_series (gpd.GeoSeries): GeoSeries containing geometry in WGS84 (EPSG:4326).
        return_gdf (bool, optional): If True, return a tuple of (projected GeoDataFrame, EPSG code).
            If False, return the projected Point geometry. Defaults to False.

    Returns:
        tuple[gpd.GeoDataFrame, int] | Point | None: Projected geometry and EPSG code if return_gdf is True,
            otherwise the projected Point. Returns None if input is empty.

    Raises:
        ValueError: If gauge_series is empty or does not contain valid geometry.
    """
    if gauge_series.empty or not hasattr(gauge_series, "geometry"):
        raise ValueError("Input gauge_series must be a non-empty GeoSeries with a 'geometry' attribute.")

    # Ensure input is a GeoDataFrame with correct CRS
    gdf = gpd.GeoDataFrame(geometry=gauge_series, crs="EPSG:4326")

    # Estimate UTM CRS and EPSG code
    utm_crs = gdf.estimate_utm_crs()
    utm_epsg = utm_crs.to_epsg() if utm_crs is not None else None
    if utm_epsg is None:
        raise ValueError("Unable to estimate UTM CRS for the provided geometry.")

    # Project to UTM CRS
    gdf_utm = gdf.to_crs(epsg=utm_epsg)

    if return_gdf:
        return gdf_utm, utm_epsg

    # Return the projected Point geometry
    geom = gdf_utm.geometry.iloc[0]
    if not isinstance(geom, Point):
        raise ValueError("Projected geometry is not a Point.")
    return geom


def str_to_np(s: str) -> np.ndarray:
    """Convert a space (or comma) separated string of numbers to numpy array.

    Falls back to ast.literal_eval if fast parse fails.
    """
    s_clean = " ".join(s.strip().replace(",", " ").split())
    try:
        arr = np.fromstring(s_clean, sep=" ")
        if arr.size:
            return arr
    except Exception:
        pass
    # Fallback (expects something like "[x y]" or tuple)
    return np.array(ast.literal_eval(s_clean.replace(" ", ",")))


def update_geometry(pnt, tile: str) -> gpd.GeoDataFrame:
    """For a point and a tile geopackage, find nearest river geometry.

    Parameters
    ----------
    pnt : shapely Point
    tile : str
        Path to GeoPackage containing columns: geom_np (string rep of lon,lat), rank.

    Returns:
    -------
    GeoDataFrame
        Rows: geometry, distance (km), approx_area.
    """
    scale_actual = {
        "small_rivers": 80,
        "medium_rivers": 800,
        "rivers": 8000,
        "big_rivers": 80000,
        "large_rivers": 800000,
    }

    df = gpd.read_file(tile)
    if df.empty:
        return df

    old_lon, old_lat = pnt.x, pnt.y

    # Convert stored coordinate strings to numpy arrays (lon, lat)
    df["geom_np"] = df["geom_np"].apply(str_to_np)

    # Vectorized distance computation
    coords = np.vstack(df["geom_np"].to_numpy())
    new_lons_rad = np.radians(coords[:, 0])
    new_lats_rad = np.radians(coords[:, 1])
    old_lon_rad = radians(old_lon)
    old_lat_rad = radians(old_lat)

    # Haversine (vector)
    dlon = old_lon_rad - new_lons_rad
    dlat = old_lat_rad - new_lats_rad
    a = np.sin(dlat / 2) ** 2 + np.cos(old_lat_rad) * np.cos(new_lats_rad) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    df["distance"] = 6371.0088 * c

    df["approx_area"] = df["rank"].map(scale_actual)

    df_sorted = df.sort_values(by=["distance", "approx_area"]).reset_index(drop=True)
    return df_sorted.loc[[0], ["geometry", "distance", "approx_area"]]


def format_tile(lat: int, lon: int) -> str:
    """Format tile name based on latitude and longitude.

    Args:
        lat: Latitude integer.
        lon: Longitude integer.

    Returns:
        Formatted tile string.
    """
    lat_prefix = f"n{abs(lat)}" if lat >= 0 else f"s{abs(lat)}"
    lon_prefix = f"e{abs(lon):03}" if lon >= 0 else f"w{abs(lon):03}"
    return f"{lat_prefix}{lon_prefix}"


def roi_extent_tiles(
    topo_p: Path, extent_coords: tuple[float, float, float, float], tif_tag: str = "elv"
) -> list[Path]:
    """Return the paths for .tiff files of elevation and flow direction in a given folder.

    Args:
        topo_p: Folder with pre-downloaded files.
        extent_coords: tuple with extent (x_min, y_max, x_max, y_min).
        tif_tag: Tag to filter TIFF files (e.g., "con" for connectivity).

    Returns:
        Dictionary with ['elv'] and ['dir'] keys, containing the corresponding files
        for the gauge of interest.

    Raises:
        ValueError: If extent_coords is not a tuple of four floats.
    """
    if not (
        isinstance(extent_coords, tuple)
        and len(extent_coords) == 4
        and all(isinstance(v, float | int) for v in extent_coords)
    ):
        raise ValueError(
            "extent_coords must be a tuple of four floats or ints (x_min, y_max, x_max, y_min)."
        )

    x_min, y_max, x_max, y_min = extent_coords

    # Adjust extent coordinates
    x_min, y_min = round_down(x_min, round_val=5), round_down(y_min, round_val=5)
    x_max, y_max = round_up(x_max, round_val=5), round_up(y_max, round_val=5)

    # Generate tile boundaries
    latitudes = np.arange(start=y_min, stop=y_max + 5, step=5, dtype=int)
    longitudes = np.arange(start=x_min, stop=x_max + 5, step=5, dtype=int)
    tile_boundaries = [format_tile(lat, lon) for lat, lon in product(latitudes, longitudes)]

    topo_p = topo_p / tif_tag
    found_tiles = list(
        chain.from_iterable(topo_p.rglob(f"{boundary}_{tif_tag}.tiff") for boundary in tile_boundaries)
    )

    return found_tiles
