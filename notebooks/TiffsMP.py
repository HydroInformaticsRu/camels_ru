from multiprocessing import Pool, cpu_count
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent

import geopandas as gpd
from osgeo import gdal

sys.path.append("../src")

from data_processing.gdal_processing import (
    create_mosaic,
    flood_extent_tiles,
    gdal_extent_clipper,
)
from utils.logger import setup_logger

log = setup_logger("ZenodoDataset", log_file="../logs/zenodo_dataset.log")
save_path = Path("../data/zenodo")
save_path.mkdir(parents=True, exist_ok=True)
geom_path = save_path / "geometry"
geom_path.mkdir(parents=True, exist_ok=True)

# full_gauges = gpd.read_file("../data/Geometry/GaugesFull.gpkg")
# full_gauges["wmo_id"] = full_gauges["wmo_id"].astype(str)
# full_gauges.set_index("wmo_id", inplace=True)
# full_gauges.index.name = "gauge_id"
# full_gauges = full_gauges[["name", "height", "area", "geometry"]]
# full_gauges["area"] = full_gauges["area"].str.replace(r"[^\d.-]", "", regex=True)
# full_gauges["area"] = pd.to_numeric(full_gauges["area"], errors="coerce")
# full_gauges.replace({"area": {0.0: np.nan}}, inplace=True)
# full_gauges["height"] = [h.replace(",", ".") if isinstance(h, str) else h for h in full_gauges["height"]]
# full_gauges["height"] = full_gauges["height"].str.replace(r"[^\d.-]", "", regex=True)
# full_gauges["height"] = pd.to_numeric(full_gauges["height"], errors="coerce")
# full_gauges.rename(columns={"name": "name_ru"}, inplace=True)
# full_gauges["name_en"] = [translit(n, "ru", reversed=True) for n in full_gauges["name_ru"]]

# full_gauges = full_gauges[["name_en", "name_ru", "height", "area", "geometry"]]
# full_gauges.to_file(geom_path / "camels_ru_gauges.gpkg")

full_gauges = gpd.read_file(PROJECT_ROOT / "data" / "CAMELS_RU" / "geometry" / "camels_ru_gauges.gpkg")
full_gauges.set_index("gauge_id", inplace=True)


hybas_mapping = gpd.read_file(PROJECT_ROOT / "data" / "Russia" / "Geometry" / "HybasSelection.gpkg")
hybas_mapping = hybas_mapping[["OBJECTID", "geometry"]]
hybas_mapping = hybas_mapping.loc[hybas_mapping["OBJECTID"].isin([24, 28]), :]


name_dict = {
    "elv": "adjusted_elevation",
    "dir": "flow_direction",
    "upg": "upstream_drainage_pixels",
}

dtype_dict = {
    "dir": gdal.GDT_Byte,
    "elv": gdal.GDT_Float32,
    "upg": gdal.GDT_Int32,
}
nodata_dict = {"dir": 247, "elv": -9999.0, "upg": -9999}


elv_path = PROJECT_ROOT / "data" / "Russia" / "SpatialData" / "MeritRU"
elv_path.mkdir(parents=True, exist_ok=True)
tmp_tif = Path("../data/tmp/rasters")
tmp_tif.mkdir(parents=True, exist_ok=True)


def process_raster_task(args: tuple) -> tuple[str, int, str]:
    """Process a single raster tile for a given HYBAS object and data tag.

    Args:
        args: Tuple containing (data_tag, obj_id, roi, hybas_gdf_row)

    Returns:
        Tuple of (data_tag, obj_id, status_message)
    """
    data_tag, obj_id, roi, hybas_gdf_row = args

    try:
        # Create temporary boundary file
        boundary_path = tmp_tif / f"{obj_id}_{data_tag}_boundary.gpkg"
        hybas_gdf_row.to_file(boundary_path, driver="GPKG")

        tif_epsg = 4326
        upper_left_x, lower_right_y, lower_right_x, upper_left_y = roi.bounds
        wgs_window = (upper_left_x, upper_left_y, lower_right_x, lower_right_y)

        tiles = flood_extent_tiles(
            topo_p="/mnt/storage/ResearchData/HydroHub/Storage/SpatialData/DEM/MeritDEM/",
            extent_coords=wgs_window,
            variable_dict=name_dict,
        )

        data_mosaic = create_mosaic(
            file_name=f"hybas_{obj_id}_{data_tag}",
            file_path=elv_path,
            tiles=tiles[data_tag],
        )

        raster_path = elv_path / data_tag
        raster_path.mkdir(parents=True, exist_ok=True)

        gdal_extent_clipper(
            initial_tif=data_mosaic,
            extent=wgs_window,
            tmp_tif=f"{tmp_tif}/{obj_id}_{data_tag}.tif",
            final_tif=f"{raster_path}/{obj_id}_{data_tag}.tif",
            crs_epsg=tif_epsg,
            dtype=dtype_dict[data_tag],
            nodata=nodata_dict[data_tag],
        )

        return (data_tag, obj_id, "success")

    except Exception as e:
        log.error("Failed processing %s for HYBAS %s: %s", data_tag, obj_id, str(e))
        return (data_tag, obj_id, f"error: {str(e)}")


def create_task_list(data_tags, hybas_mapping_gdf):
    """Create list of tasks for multiprocessing.

    Args:
        data_tags: List of data tags to process
        hybas_mapping_gdf: GeoDataFrame with HYBAS geometries

    Returns:
        List of tuples (data_tag, obj_id, roi, hybas_gdf_row)
    """
    tasks = []
    for data_tag in data_tags:
        for i, (obj_id, roi) in enumerate(hybas_mapping_gdf.itertuples(index=False)):
            hybas_gdf_row = hybas_mapping_gdf.iloc[[i], :]
            tasks.append((data_tag, obj_id, roi, hybas_gdf_row))
    return tasks


def process_in_batches(tasks, batch_size=None, n_workers=None):
    """Process tasks in batches using multiprocessing.

    Args:
        tasks: List of task tuples
        batch_size: Number of tasks per batch (default: 2 * n_workers)
        n_workers: Number of parallel workers (default: cpu_count() - 1)

    Returns:
        List of results from all tasks
    """
    if n_workers is None:
        n_workers = max(1, cpu_count() - 1)

    if batch_size is None:
        batch_size = n_workers * 2

    log.info("Processing %d tasks with %d workers in batches of %d", len(tasks), n_workers, batch_size)

    results = []
    total_batches = (len(tasks) + batch_size - 1) // batch_size

    for batch_idx in range(0, len(tasks), batch_size):
        batch = tasks[batch_idx : batch_idx + batch_size]
        current_batch_num = (batch_idx // batch_size) + 1

        log.info("Processing batch %d/%d (%d tasks)", current_batch_num, total_batches, len(batch))

        with Pool(processes=n_workers) as pool:
            batch_results = pool.map(process_raster_task, batch)
            results.extend(batch_results)

        # Log batch completion
        success_count = sum(1 for _, _, status in batch_results if status == "success")
        log.info(
            "Batch %d/%d complete: %d/%d successful",
            current_batch_num,
            total_batches,
            success_count,
            len(batch),
        )

    return results


# Create output directories for each data tag
for data_tag in ["elv", "dir", "upg"]:
    raster_path = elv_path / data_tag
    raster_path.mkdir(parents=True, exist_ok=True)

# Create task list
tasks = create_task_list(["elv", "dir", "upg"], hybas_mapping)

# Process tasks in batches with multiprocessing
# Adjust batch_size based on available memory (default: 2 * workers)
# For memory-intensive tasks, reduce batch_size (e.g., 4 or 8)
results = process_in_batches(tasks, batch_size=8, n_workers=None)

# Log final results
total_tasks = len(results)
successful = sum(1 for _, _, status in results if status == "success")
failed = total_tasks - successful

log.info("Processing complete: %d/%d successful, %d failed", successful, total_tasks, failed)

if failed > 0:
    log.warning("Failed tasks:")
    for data_tag, obj_id, status in results:
        if status != "success":
            log.warning("  - %s for HYBAS %s: %s", data_tag, obj_id, status)
