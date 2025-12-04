#!/usr/bin/env python3
"""Multiprocessing watershed delineation script with batch processing.

This script processes watershed contours for gauges within HYBAS ROIs using
pysheds and MeritHYDRO DEM data. It uses ProcessPoolExecutor with batching
to efficiently manage memory while processing multiple watersheds in parallel.
"""

from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, as_completed
from copy import deepcopy
import gc
import os
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from pysheds.grid import Grid
from shapely import geometry, ops
from tqdm.auto import tqdm

# Fix GDAL library path issue - use conda environment's libstdc++
conda_env = os.environ.get("CONDA_PREFIX")
if conda_env:
    lib_path = os.path.join(conda_env, "lib")
    current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
    if lib_path not in current_ld_path:
        os.environ["LD_LIBRARY_PATH"] = f"{lib_path}:{current_ld_path}" if current_ld_path else lib_path

sys.path.append("../src")

from data_processing.geom_functions import poly_from_multipoly, polygon_area
from utils.logger import setup_logger

log = setup_logger("WatershedDelineation", log_file="../logs/watershed_delineation.log")

# Global worker state (loaded once per worker process)
_worker_grid = None
_worker_acc = None
_worker_fdir = None
_worker_D8_DIRMAP = None
_worker_ACC_COEFF = None


def _init_worker(grid_path: str, acc_path: str, fdir_path: str, dirmap: tuple, acc_coeff: float) -> None:
    """Initialize worker: load rasters ONCE per worker process.

    Args:
        grid_path: Path to elevation grid raster
        acc_path: Path to flow accumulation raster
        fdir_path: Path to flow direction raster
        dirmap: D8 direction mapping tuple
        acc_coeff: Accumulation coefficient for stream threshold
    """
    global _worker_grid, _worker_acc, _worker_fdir, _worker_D8_DIRMAP, _worker_ACC_COEFF

    try:
        # Each worker loads rasters once and reuses them
        _worker_grid = Grid.from_raster(
            grid_path,
            name="grid",
            nodata=-9999,
            dtype=np.float32,
        )

        _worker_acc = _worker_grid.read_raster(
            acc_path,
            nodata=-9999,
            dtype=np.int32,
            dirmap=dirmap,
            routing="d8",
        )

        _worker_fdir = _worker_grid.read_raster(
            fdir_path,
            dtype="uint8",
            dirmap=dirmap,
            routing="d8",
            nodata=247,
        )

        _worker_D8_DIRMAP = dirmap
        _worker_ACC_COEFF = acc_coeff

        log.info("Worker initialized successfully with rasters from: %s", Path(grid_path).parent)
    except Exception as e:
        log.error("Failed to initialize worker: %s", str(e))
        raise


def process_single_watershed(gauge_id: str, gauge_x: float, gauge_y: float, gauge_name: str) -> dict:
    """Process a single watershed using pre-loaded worker rasters.

    Args:
        gauge_id: Station identifier
        gauge_x: Longitude of gauge location
        gauge_y: Latitude of gauge location
        gauge_name: Place name for the gauge

    Returns:
        Dictionary containing gauge_id, name, area_km2, and geometry
    """
    try:
        # Create a copy of the grid for this watershed (grid metadata only, ~1KB)
        gauge_grid = deepcopy(_worker_grid)

        if gauge_grid is None:
            raise ValueError("Worker grid not initialized.")

        # Use pre-loaded rasters (no disk I/O per watershed!)
        acc = _worker_acc
        fdir = _worker_fdir

        # Snap pour point to high accumulation cell
        x_snap, y_snap = gauge_grid.snap_to_mask(acc > _worker_ACC_COEFF, (gauge_x, gauge_y))

        # Delineate catchment
        catch_mask = gauge_grid.catchment(
            x=x_snap,
            y=y_snap,
            fdir=fdir,
            dirmap=_worker_D8_DIRMAP,
            xytype="coordinate",
        )
        gauge_grid.clip_to(catch_mask)

        # Vectorize catchment
        ws = gauge_grid.polygonize()
        ws = ops.unary_union([geometry.shape(shape) for shape, _ in ws])
        ws = poly_from_multipoly(ws)

        area_km2 = polygon_area(ws)

        # Clean up only the clipped objects
        del catch_mask, gauge_grid

        return {
            "gauge_id": gauge_id,
            "name": gauge_name,
            "area_km2": area_km2,
            "geometry": ws,
        }
    except Exception as e:
        log.error("Failed processing gauge %s (%s): %s", gauge_id, gauge_name, str(e))
        raise


def get_optimal_workers(base_workers: int = 3) -> int:
    """Calculate optimal number of workers based on CPU and memory.

    Args:
        base_workers: Base number of workers to use

    Returns:
        Optimal worker count (capped at 3 to avoid memory issues)
    """
    cpu_count = os.cpu_count() or 4
    # Use fewer workers to avoid memory overflow
    return min(base_workers, cpu_count - 1, 3)


def process_roi_watersheds(
    roi_id: int,
    roi_gauge_ids: list,
    full_gauges: gpd.GeoDataFrame,
    elv_path: Path,
    geom_path: Path,
    use_multiprocessing: bool = False,
    batch_size: int = 10,
    max_workers: int = 1,
) -> gpd.GeoDataFrame:
    """Process all watersheds for a given ROI.

    Args:
        roi_id: HYBAS OBJECTID for the region of interest
        roi_gauge_ids: List of gauge IDs to process
        full_gauges: GeoDataFrame with all gauge information
        elv_path: Path to MeritHYDRO raster data
        geom_path: Path to save geometry outputs
        use_multiprocessing: Whether to use multiprocessing (default: False for memory safety)
        batch_size: Number of tasks per batch (default: 10)
        max_workers: Number of parallel workers if multiprocessing enabled (default: 1)

    Returns:
        GeoDataFrame containing processed watershed geometries
    """
    # Create temp directory for this ROI
    roi_temp_dir = geom_path / "temp" / f"roi_{roi_id}"
    roi_temp_dir.mkdir(parents=True, exist_ok=True)

    # Check if watersheds already exist for this ROI
    watersheds_path = roi_temp_dir / f"roi_{roi_id}_watersheds.gpkg"
    if watersheds_path.exists():
        log.info("ROI %d: Watersheds already exist at %s, skipping processing", roi_id, watersheds_path)
        try:
            watersheds_gdf = gpd.read_file(watersheds_path)
            watersheds_gdf.set_index("gauge_id", inplace=True)
            log.info("ROI %d: Loaded %d existing watersheds", roi_id, len(watersheds_gdf))
            return watersheds_gdf
        except Exception as e:
            log.warning(
                "ROI %d: Failed to load existing watersheds (%s), reprocessing...", roi_id, str(e)
            )

    D8_DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
    ACC_COEFF = 1e2

    # Set up file paths
    grid_path = str(elv_path / "elv" / f"{roi_id}_elv.tif")
    acc_path = str(elv_path / "upg" / f"{roi_id}_upg.tif")
    fdir_path = str(elv_path / "dir" / f"{roi_id}_dir.tif")

    # Verify files exist
    for path_str, name in [
        (grid_path, "elevation"),
        (acc_path, "accumulation"),
        (fdir_path, "flow direction"),
    ]:
        if not Path(path_str).exists():
            raise FileNotFoundError(f"Missing {name} raster: {path_str}")

    # Get gauges for this ROI
    roi_gauges = full_gauges.loc[roi_gauge_ids, :].copy()
    roi_gauges = roi_gauges.to_crs(epsg=4326)

    # Prepare task arguments
    tasks: list[tuple[str, float, float, str]] = [
        (str(gauge_id), gauge.geometry.x, gauge.geometry.y, gauge["name_en"])
        for gauge_id, gauge in roi_gauges.iterrows()
    ]
    total_tasks = len(tasks)

    watersheds_list = []

    if use_multiprocessing and max_workers > 1:
        # Multiprocessing mode (risky with limited memory)
        log.info(
            "Processing ROI %d: %d watersheds with %d workers in batches of %d",
            roi_id,
            len(tasks),
            max_workers,
            batch_size,
        )

        try:
            with ProcessPoolExecutor(
                initializer=_init_worker,
                initargs=(grid_path, acc_path, fdir_path, D8_DIRMAP, ACC_COEFF),
                max_workers=max_workers,
            ) as executor:
                # Process in batches
                for batch_start in tqdm(
                    range(0, len(tasks), batch_size), desc=f"ROI {roi_id} batches", unit="batch"
                ):
                    batch_tasks = tasks[batch_start : batch_start + batch_size]

                    # Submit only current batch
                    futures = {
                        executor.submit(process_single_watershed, *task): task[0] for task in batch_tasks
                    }

                    # Collect results for this batch
                    for future in as_completed(futures):
                        gauge_id = futures[future]
                        try:
                            result = future.result()
                            watersheds_list.append(result)
                        except Exception as exc:
                            log.error("Gauge %s generated exception: %s", gauge_id, str(exc))

                    # Force garbage collection between batches
                    gc.collect()

        except BrokenExecutor as e:
            log.error("ROI %d: Process pool broken: %s", roi_id, str(e))
            log.error("Falling back to sequential processing...")
            # Continue with sequential processing below

    # Sequential mode (always run if multiprocessing disabled or failed)
    if not use_multiprocessing or max_workers == 1 or not watersheds_list:
        if watersheds_list:
            log.info("ROI %d: Continuing with sequential processing for remaining gauges", roi_id)
            # Remove successfully processed gauges
            processed_ids = {w["gauge_id"] for w in watersheds_list}
            tasks = [t for t in tasks if t[0] not in processed_ids]

        log.info("Processing ROI %d: %d watersheds sequentially (memory-safe mode)", roi_id, len(tasks))

        # Initialize worker state in main process
        _init_worker(grid_path, acc_path, fdir_path, D8_DIRMAP, ACC_COEFF)

        # Process each watershed sequentially
        for task in tqdm(tasks, desc=f"ROI {roi_id} gauges", unit="gauge"):
            gauge_id = task[0]
            try:
                result = process_single_watershed(*task)
                watersheds_list.append(result)
            except Exception as exc:
                log.error("Gauge %s generated exception: %s", gauge_id, str(exc))

            # Periodic garbage collection
            if len(watersheds_list) % 10 == 0:
                gc.collect()

    log.info(
        "ROI %d: Successfully processed %d/%d watersheds", roi_id, len(watersheds_list), total_tasks
    )

    # Convert to GeoDataFrame
    if watersheds_list:
        watersheds_gdf = gpd.GeoDataFrame(watersheds_list, crs="EPSG:4326")
        watersheds_gdf.set_index("gauge_id", inplace=True)

        # Save ROI watersheds and gauges to temp directory for manual evaluation
        watersheds_gdf.to_file(watersheds_path, driver="GPKG")
        log.info("ROI %d: Saved watersheds to %s", roi_id, watersheds_path)

        # Save corresponding gauges
        gauges_path = roi_temp_dir / f"roi_{roi_id}_gauges.gpkg"
        roi_gauges.to_file(gauges_path, driver="GPKG")
        log.info("ROI %d: Saved gauges to %s", roi_id, gauges_path)

        return watersheds_gdf
    else:
        log.warning("ROI %d: No watersheds were successfully processed", roi_id)
        return gpd.GeoDataFrame()


def main():
    """Main execution function."""
    # Set up paths
    save_path = Path("../data/zenodo")
    save_path.mkdir(parents=True, exist_ok=True)
    geom_path = save_path / "geometry"
    geom_path.mkdir(parents=True, exist_ok=True)

    elv_path = Path("../data/SpatialData/MeritRU")

    # Load gauge data
    log.info("Loading gauge data...")
    full_gauges = gpd.read_file("../data/Geometry/CompleteGauges2025.gpkg")
    full_gauges.set_index("gauge_id", inplace=True)

    # Load HYBAS mapping
    log.info("Loading HYBAS mapping...")
    hybas_mapping = gpd.read_file("../data/Geometry/HybasSelection.gpkg")

    # Spatial join to find which gauges are in which HYBAS regions
    full_gauges_with_crs = full_gauges.copy()
    full_gauges_with_crs = full_gauges_with_crs.to_crs(hybas_mapping.crs)

    gauges_intersecting_hybas = gpd.sjoin(
        full_gauges_with_crs, hybas_mapping[["OBJECTID", "geometry"]], how="inner", predicate="within"
    )

    # Group gauges by HYBAS region
    gauges_by_roi = gauges_intersecting_hybas.groupby("OBJECTID")

    log.info("Found %d HYBAS regions with gauges", len(gauges_by_roi))

    # Process each ROI
    all_watersheds = []

    for roi_id, roi_gauges_df in gauges_by_roi:
        # Get the gauge IDs directly from the grouped dataframe index
        roi_gauge_ids = roi_gauges_df.index.tolist()

        log.info("=" * 60)
        log.info("Processing ROI %d with %d gauges", roi_id, len(roi_gauge_ids))

        try:
            watersheds_gdf = process_roi_watersheds(
                roi_id=roi_id,
                roi_gauge_ids=roi_gauge_ids,
                full_gauges=full_gauges,
                elv_path=elv_path,
                geom_path=geom_path,
                use_multiprocessing=False,  # Set to True to enable multiprocessing (risky!)
                batch_size=10,
                max_workers=1,  # Only used if use_multiprocessing=True
            )

            if not watersheds_gdf.empty:
                all_watersheds.append(watersheds_gdf)

        except Exception as e:
            log.error("Failed to process ROI %d: %s", roi_id, str(e))
            # Continue to next ROI instead of stopping
            continue

    # Combine all watersheds
    if all_watersheds:
        log.info("=" * 60)
        log.info("Combining all watersheds...")
        combined_watersheds = pd.concat(all_watersheds, ignore_index=False)

        # Save to file
        output_path = geom_path / "camels_ru_watersheds.gpkg"
        combined_watersheds.to_file(output_path, driver="GPKG")

        log.info("Successfully processed %d watersheds", len(combined_watersheds))
        log.info("Saved to: %s", output_path)

        # Print summary statistics
        log.info("=" * 60)
        log.info("Summary Statistics:")
        log.info("  Total watersheds: %d", len(combined_watersheds))
        log.info(
            "  Area range: %.2f - %.2f km²",
            combined_watersheds["area_km2"].min(),
            combined_watersheds["area_km2"].max(),
        )
        log.info("  Mean area: %.2f km²", combined_watersheds["area_km2"].mean())
        log.info("  Median area: %.2f km²", combined_watersheds["area_km2"].median())
    else:
        log.error("No watersheds were successfully processed!")


if __name__ == "__main__":
    main()
