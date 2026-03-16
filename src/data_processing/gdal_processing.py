from collections.abc import Generator, Sequence
from itertools import product
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
from osgeo import gdal
import rasterio
from rasterio.warp import transform
from shapely.geometry import MultiPolygon, Point, Polygon

sys.path.append(str(Path(__file__).parent.parent))
from data_processing.geom_functions import (
    create_gdf,
    gauge_buffer_creator,
    gauge_to_utm,
    roi_extent_tiles,
    round_down,
    round_up,
)
from utils.logger import setup_logger

logger = setup_logger(__name__, level="INFO")

gdal.UseExceptions()


def reproject_and_clip(
    input_raster: str | Path,
    output_raster: str | Path,
    projection: str,
    shapefile: str = "",
    resolution: float = 0.0,
    nodata: float = -9999.0,
    output_type: int | None = None,
) -> str:
    """Reproject and optionally clip a raster using GDAL Warp.

    Args:
        input_raster: Path to the input raster file.
        output_raster: Path for the output raster file.
        projection: Target spatial reference system (e.g., "EPSG:4326").
        shapefile: Path to shapefile for clipping (optional).
        resolution: Target resolution in units of the projection (optional).
        nodata: Nodata value for the output raster (default: -9999.0 for float32).
        output_type: GDAL output data type (e.g., gdal.GDT_Byte, gdal.GDT_Float32).
                     If None, preserves input data type.

    Returns:
        Path to the output raster file.

    Raises:
        RuntimeError: If GDAL Warp operation fails.
    """
    logger.info("Reprojecting raster to %s", projection)

    # Build warp options based on parameters
    warp_kwargs = {
        "format": "GTiff",
        "dstSRS": projection,
        "cropToCutline": True,
        "dstNodata": nodata,
        "creationOptions": [
            "COMPRESS=DEFLATE",
            "TILED=YES",
            "BIGTIFF=IF_SAFER",
        ],
    }

    if shapefile:
        warp_kwargs["cutlineDSName"] = shapefile

    if resolution > 0:
        warp_kwargs["xRes"] = resolution
        warp_kwargs["yRes"] = resolution

    if output_type is not None:
        warp_kwargs["outputType"] = output_type

    options = gdal.WarpOptions(**warp_kwargs)
    result = gdal.Warp(
        srcDSOrSrcDSTab=str(input_raster),
        destNameOrDestDS=str(output_raster),
        options=options,
    )

    if result is None:
        raise RuntimeError(f"GDAL Warp failed for {input_raster}")

    result.FlushCache()
    result = None  # Ensure cleanup

    return str(output_raster)


def vrt_to_geotif(vrt_path: str | Path, geotif_path: str | Path) -> str:
    """Convert a VRT mosaic to a GeoTIFF file.

    Args:
        vrt_path: Path to the VRT mosaic.
        geotif_path: Path for the output GeoTIFF file.

    Returns:
        Path to the output GeoTIFF file.

    Raises:
        RuntimeError: If GDAL Translate operation fails.
    """
    logger.info("Converting VRT to GeoTIFF: %s -> %s", vrt_path, geotif_path)

    src_ds = gdal.Open(str(vrt_path), gdal.GA_ReadOnly)
    if src_ds is None:
        raise RuntimeError(f"Failed to open VRT file: {vrt_path}")

    result = gdal.Translate(
        str(geotif_path),
        src_ds,
        format="GTiff",
        creationOptions=[
            "COMPRESS=DEFLATE",
            "TILED=YES",
            "BIGTIFF=YES",
            "NUM_THREADS=8",
        ],
        callback=gdal.TermProgress_nocb,
    )

    if result is None:
        raise RuntimeError(f"GDAL Translate failed for {vrt_path}")

    result.FlushCache()
    result = None
    src_ds = None

    return str(geotif_path)


def gdal_extent_clipper(
    initial_tif: str | Path,
    extent: tuple[float, float, float, float],
    tmp_tif: str | Path,
    final_tif: str | Path,
    crs_epsg: int | None = 4326,
    nodata: float = -9999.0,
    dtype: int | None = None,
) -> None:
    """Clip and reproject a GeoTIFF file to a desired extent and EPSG code.

    This function clips a GeoTIFF to the specified extent, then reprojects it
    to the target EPSG code. Intermediate and original files are removed after
    successful processing.

    Args:
        initial_tif: Path to the input GeoTIFF file.
        extent: Bounding box as (minX, maxY, maxX, minY) in source CRS.
        tmp_tif: Path for the intermediate clipped file (pre-projection).
        final_tif: Path for the final reprojected and clipped file.
        crs_epsg: Target EPSG code for reprojection.
        nodata: Nodata value for the output raster (default: -9999.0 for float32).
        dtype: GDAL output data type (e.g., gdal.GDT_Byte, gdal.GDT_Float32).
                     If None, preserves input data type.

    Raises:
        FileNotFoundError: If the input file does not exist.
        RuntimeError: If GDAL operations fail.
    """
    initial_path = Path(initial_tif)
    tmp_path = Path(tmp_tif)
    final_path = Path(final_tif)

    if not initial_path.is_file():
        raise FileNotFoundError(f"Input file not found: {initial_tif}")

    logger.info("Clipping %s to extent %s", initial_path.name, extent)

    # Clip to extent
    translate_kwargs = {
        "destName": str(tmp_path),
        "srcDS": str(initial_path),
        "projWin": extent,
        "creationOptions": [
            "COMPRESS=DEFLATE",
            "TILED=YES",
            "BIGTIFF=IF_SAFER",
        ],
    }
    if dtype is not None:
        translate_kwargs["outputType"] = dtype
        translate_kwargs["noData"] = nodata

    clipped_ds = gdal.Translate(**translate_kwargs)
    if clipped_ds is None:
        raise RuntimeError(f"GDAL Translate failed for {initial_tif} with extent {extent}")
    clipped_ds.FlushCache()
    clipped_ds = None

    logger.info("Reprojecting to EPSG:%d", crs_epsg)

    # Reproject to target CRS
    warp_kwargs = {
        "destNameOrDestDS": str(final_path),
        "srcDSOrSrcDSTab": str(tmp_path),
        "format": "GTiff",
        "dstSRS": f"EPSG:{crs_epsg}",
        "dstNodata": nodata,
        "creationOptions": [
            "COMPRESS=DEFLATE",
            "TILED=YES",
            "BIGTIFF=IF_SAFER",
        ],
    }
    if dtype is not None:
        warp_kwargs["outputType"] = dtype

    projected_ds = gdal.Warp(**warp_kwargs)
    if projected_ds is None:
        raise RuntimeError(f"GDAL Warp failed for {tmp_tif} to EPSG:{crs_epsg}")
    projected_ds.FlushCache()
    projected_ds = None

    # Cleanup intermediate files
    initial_path.unlink(missing_ok=True)
    tmp_path.unlink(missing_ok=True)


def flood_extent_tiles(
    topo_p: Path | str,
    extent_coords: tuple,
    variable_dict: dict[str, str],
) -> dict:
    """Return the paths for .tiff files of elevation and flow direction in a given folder.

    Args:
    ----
        topo_p (Union[pathlib.Path, str]): Folder with pre-downloaded files.
        extent_coords (tuple): Tuple with extent max, min latitude and longitude.
        variable_dict (dict[str, str]): Dictionary mapping variable short names to their full names.

    Returns:
    -------
        dict: Dictionary with ['elv'] and ['dir'] keys, containing the corresponding files
              for the gauge of interest.

    """
    x_min, y_max, x_max, y_min = extent_coords

    # Adjust extent coordinates
    x_min, y_min = list(map(round_down, [x_min, y_min]))
    x_max, y_max = list(map(round_up, [x_max, y_max]))

    # Generate tile boundaries with handling for negative longitudes
    def format_tile(lat, lon):
        """Format tile name based on latitude and longitude.

        Replaces 'e' with 'w' for negative longitudes.
        """
        lat_prefix = f"n{lat}" if lat >= 0 else f"s{-lat}"
        if lon >= 0:
            lon_prefix = f"e{abs(lon):03}"
        else:
            lon_prefix = f"w{abs(lon):03}"
        return f"{lat_prefix}{lon_prefix}"

    tile_boundaries = [
        format_tile(lat, lon)
        for lat, lon in product(
            np.arange(start=y_min, stop=y_max + 5, step=5),
            np.arange(start=x_min, stop=x_max + 5, step=5),
        )
    ]

    # Find matching files for each variable
    tiles = {
        short_name: [
            Path(f"{topo_p}/{long_name}/rasters/{boundary}_{short_name}.tif")
            for boundary in tile_boundaries
            if Path(f"{topo_p}/{long_name}/rasters/{boundary}_{short_name}.tif").exists()
        ]
        for short_name, long_name in variable_dict.items()
    }

    return tiles


def create_mosaic(
    file_path: str | Path,
    file_name: str,
    tiles: Generator[Path, None, None] | Sequence[str | Path],
) -> str:
    """Generate a VRT mosaic from a collection of GeoTIFF tiles.

    Args:
        file_path: Directory where the mosaic VRT will be saved.
        file_name: Name for the output VRT file (without extension).
        tiles: Generator or sequence of GeoTIFF file paths to mosaic.

    Returns:
        Path to the created VRT mosaic.

    Raises:
        ValueError: If the tiles collection is empty.
        RuntimeError: If GDAL BuildVRT operation fails.
    """
    # Convert to list to check emptiness and reuse
    tile_list = list(tiles) if isinstance(tiles, Generator) else tiles

    if not tile_list:
        raise ValueError("Tiles list must not be empty.")

    output_dir = Path(file_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    vrt_target = output_dir / f"{file_name}.vrt"

    logger.info("Creating VRT mosaic with %d tiles at %s", len(tile_list), vrt_target)

    # Convert all paths to strings for GDAL compatibility
    tile_paths = [str(tile) for tile in tile_list]

    mosaic_ds = gdal.BuildVRT(destName=str(vrt_target), srcDSOrSrcDSTab=tile_paths)
    if mosaic_ds is None:
        raise RuntimeError(f"GDAL BuildVRT failed for {len(tile_paths)} tiles")

    mosaic_ds.FlushCache()
    mosaic_ds = None

    return str(vrt_target)


def get_point_height_from_dem(
    pt_geoser: gpd.GeoSeries,
    dem_path: str | Path,
) -> float:
    """Retrieve elevation value at a point from a digital elevation model (DEM).

    Args:
        pt_geoser: GeoSeries containing a single Point geometry.
        dem_path: Path to the DEM raster file.

    Returns:
        Elevation value at the point location. Returns np.nan if the point
        falls on a nodata pixel.

    Raises:
        TypeError: If the geometry is not a Point.
        ValueError: If the GeoSeries is empty or contains multiple geometries.
        RuntimeError: If the DEM file cannot be opened.
    """
    if len(pt_geoser) != 1:
        raise ValueError(f"Expected single geometry, got {len(pt_geoser)}")

    point_crs = pt_geoser.crs
    pt_geom = pt_geoser.geometry.iloc[0]

    # Type guard: ensure we have a Point geometry with isinstance check
    if not isinstance(pt_geom, Point):
        raise TypeError(f"Geometry must be a Point, got {type(pt_geom).__name__}")

    logger.debug("Extracting elevation for point (%.6f, %.6f)", pt_geom.x, pt_geom.y)

    with rasterio.open(str(dem_path)) as src:
        # Reproject point to DEM's CRS if necessary
        if src.crs != point_crs:
            result = transform(
                point_crs,
                src.crs,
                [pt_geom.x],
                [pt_geom.y],
            )
            xs, ys = result[0], result[1]
            x_coord, y_coord = xs[0], ys[0]
        else:
            x_coord, y_coord = pt_geom.x, pt_geom.y

        # Convert geographic coordinates to pixel indices
        row, col = src.index(x_coord, y_coord)

        # Read elevation value from band 1
        elevation = src.read(1)[row, col]

        # Handle nodata values
        if src.nodata is not None and elevation == src.nodata:
            logger.warning("Point falls on nodata pixel in DEM")
            return np.nan

    return float(elevation)


def create_tif_get_area(
    tmp_raster_folder: Path,
    gauge_id: str,
    geom_point: gpd.GeoSeries,
    ws_geom: Polygon | MultiPolygon,
    fdir_path: Path,
    result_tiff_storage: Path,
) -> tuple[float, float]:
    """Create a clipped elevation TIFF for a gauge and calculate watershed area.

    Clips the elevation raster to the AOI buffer and mosaics the tiles. Calculates
    the watershed area and accumulation coefficient.

    Args:
        tmp_raster_folder: Temporary folder for intermediate files.
        gauge_id: Gauge identifier.
        geom_point: Gauge point geometry.
        ws_geom: Watershed geometry (Polygon or MultiPolygon).
        fdir_path: Path to the flow direction raster directory.
        result_tiff_storage: Output directory for the clipped elevation TIFF.

    Returns:
        Tuple containing (accumulation coefficient, watershed area in sq. km).

    Raises:
        FileNotFoundError: If required directories or files are missing.
        ValueError: If input geometries are invalid.
    """
    tif_trim_folder = tmp_raster_folder / "trimmed_tifs"
    elv_path_dir = Path(result_tiff_storage)

    # Create necessary directories
    for folder in (tmp_raster_folder, tif_trim_folder, elv_path_dir):
        folder.mkdir(exist_ok=True, parents=True)

    # Project gauge to UTM and create AOI buffer
    _, tif_epsg = gauge_to_utm(gauge_series=geom_point, return_gdf=True)  # type: ignore

    # Ensure the geometry is a Point
    gauge_geom = geom_point.geometry.values[0]
    if not gauge_geom.geom_type == "Point":
        raise ValueError("geom_point must contain a Point geometry.")

    _, wgs_window, acc_coef, ws_area = gauge_buffer_creator(
        gauge_geometry=gauge_geom,
        ws_gdf=create_gdf(ws_geom),
        tif_epsg=tif_epsg,
    )

    # Get relevant elevation tiles for the AOI
    elv_tiles = roi_extent_tiles(topo_p=fdir_path, extent_coords=wgs_window)
    if not elv_tiles:
        raise FileNotFoundError("No elevation tiles found for the specified AOI.")

    # Create mosaic for AOI buffer with elevation data
    elv_vrt = create_mosaic(
        file_path=str(tmp_raster_folder),
        file_name=f"{gauge_id}_elv",
        tiles=elv_tiles,
    )

    # Clip the mosaic to the AOI extent
    trimmed_tiff = tif_trim_folder / f"{gauge_id}_elv.tiff"
    final_tiff = elv_path_dir / f"{gauge_id}.tiff"
    gdal_extent_clipper(
        initial_tif=elv_vrt,
        extent=wgs_window,
        tmp_tif=str(trimmed_tiff),
        final_tif=str(final_tiff),
        crs_epsg=4326,
    )
    Path(elv_vrt).unlink(missing_ok=True)

    return acc_coef, ws_area
