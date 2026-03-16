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


def _write_combined_outputs(
    watersheds: list[gpd.GeoDataFrame],
    gauges: list[gpd.GeoDataFrame],
    geom_path: Path,
) -> None:
    """Merge processed ROIs into single files for manual review."""
    if watersheds:
        combined_watersheds = pd.concat(watersheds, ignore_index=False)
        combined_watersheds = combined_watersheds.loc[~combined_watersheds.index.duplicated(keep="last")]
        output_path = geom_path / "camels_ru_watersheds.gpkg"
        combined_watersheds.to_file(output_path, driver="GPKG")
        log.info(
            "Updated combined watersheds (%d features) at %s", len(combined_watersheds), output_path
        )

    if gauges:
        combined_gauges = pd.concat(gauges, ignore_index=False)
        combined_gauges = combined_gauges.loc[~combined_gauges.index.duplicated(keep="last")]
        gauges_output = geom_path / "camels_ru_gauges.gpkg"
        combined_gauges.to_file(gauges_output, driver="GPKG")
        log.info("Updated combined gauges (%d points) at %s", len(combined_gauges), gauges_output)


def merge_stream_saved_roi(roi_id: int, geom_path: Path) -> gpd.GeoDataFrame:
    """Merge per-watershed GPKGs for an ROI into a single watersheds file.

    Call this after processing the ROI with stream_save_roi_ids when you have
    enough memory. Reads each roi_{id}_watershed_{gauge_id}.gpkg and writes
    roi_{id}_watersheds.gpkg.
    """
    roi_temp_dir = geom_path / "temp" / f"roi_{roi_id}"
    pattern = f"roi_{roi_id}_watershed_*.gpkg"
    paths = sorted(roi_temp_dir.glob(pattern))
    if not paths:
        log.warning("No stream-saved watershed files found for ROI %d in %s", roi_id, roi_temp_dir)
        return gpd.GeoDataFrame()

    frames = []
    for p in paths:
        gdf = gpd.read_file(p)
        frames.append(gdf)
    merged = pd.concat(frames, ignore_index=True)
    merged = gpd.GeoDataFrame(merged, crs="EPSG:4326")
    if "gauge_id" in merged.columns:
        merged.set_index("gauge_id", inplace=True)

    out_path = roi_temp_dir / f"roi_{roi_id}_watersheds.gpkg"
    merged.to_file(out_path, driver="GPKG")
    log.info("Merged %d watersheds for ROI %d to %s", len(merged), roi_id, out_path)
    return merged


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


def process_single_watershed(
    gauge_id: str, gauge_x: float, gauge_y: float, gauge_name: str, acc_coeff: float | None = None
) -> dict:
    """Process a single watershed using pre-loaded worker rasters.

    Args:
        gauge_id: Station identifier
        gauge_x: Longitude of gauge location
        gauge_y: Latitude of gauge location
        gauge_name: Place name for the gauge
        acc_coeff: Optional accumulation coefficient override; if None, use worker default.

    Returns:
        Dictionary containing gauge_id, name, area_km2, and geometry
    """
    coeff = (acc_coeff if acc_coeff is not None else _worker_ACC_COEFF) or 1e3
    original_viewfinder = None
    try:
        if _worker_grid is None:
            raise ValueError("Worker grid not initialized.")

        # Save the original viewfinder (lightweight metadata, not raster data)
        original_viewfinder = deepcopy(_worker_grid.viewfinder)

        acc = _worker_acc
        fdir = _worker_fdir

        # Snap pour point to high accumulation cell
        x_snap, y_snap = _worker_grid.snap_to_mask(acc > coeff, (gauge_x, gauge_y))

        # Delineate catchment
        catch_mask = _worker_grid.catchment(
            x=x_snap,
            y=y_snap,
            fdir=fdir,
            dirmap=_worker_D8_DIRMAP,
            xytype="coordinate",
        )
        _worker_grid.clip_to(catch_mask)

        # Vectorize catchment
        ws = _worker_grid.polygonize()
        ws = ops.unary_union([geometry.shape(shape) for shape, _ in ws])
        ws = poly_from_multipoly(ws)

        area_km2 = polygon_area(ws)

        # Restore original grid view (no deepcopy of multi-GB rasters needed)
        _worker_grid.viewfinder = original_viewfinder
        del catch_mask

        return {
            "gauge_id": gauge_id,
            "name": gauge_name,
            "area_km2": area_km2,
            "geometry": ws,
        }
    except Exception as e:
        # Restore viewfinder even on failure to keep grid usable
        if _worker_grid is not None and original_viewfinder is not None:
            _worker_grid.viewfinder = original_viewfinder
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
    stream_save_roi_ids: list[int] | None = None,
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
        stream_save_roi_ids: If set, for these ROI IDs each watershed is saved to its own
            file immediately (roi_{id}_watershed_{gauge_id}.gpkg) and not held in memory.
            Use merge_stream_saved_roi(roi_id, geom_path) later to merge when resources allow.

    Returns:
        GeoDataFrame containing processed watershed geometries (empty if stream_save used).
    """
    # Create temp directory for this ROI
    roi_temp_dir = geom_path / "temp" / f"roi_{roi_id}"
    roi_temp_dir.mkdir(parents=True, exist_ok=True)

    stream_save = stream_save_roi_ids is not None and roi_id in stream_save_roi_ids
    if stream_save:
        log.info("ROI %d: stream-save mode (one file per watershed, no in-memory accumulation)", roi_id)

    # Prepare gauges for this ROI (saved regardless of watershed reprocessing)
    roi_gauges = full_gauges.loc[roi_gauge_ids, :].copy()
    roi_gauges = roi_gauges.to_crs(epsg=4326)

    gauges_path = roi_temp_dir / f"roi_{roi_id}_gauges.gpkg"
    roi_gauges.to_file(gauges_path, driver="GPKG")
    log.info("ROI %d: Saved gauges to %s", roi_id, gauges_path)

    # Check if watersheds already exist for this ROI (skip when stream_save: we use per-gauge files)
    watersheds_path = roi_temp_dir / f"roi_{roi_id}_watersheds.gpkg"
    if not stream_save and watersheds_path.exists():
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
    ACC_COEFF_DEFAULT = 1e3
    ACC_COEFF_STRICT = 1e2

    # Per-gauge ACC_COEFF: use stricter threshold (1e2) when area_roshydromet < 100 and area_diff_perc outside ±20%
    if "area_roshydromet" in roi_gauges.columns and "area_diff_perc" in roi_gauges.columns:
        area_small = roi_gauges["area_roshydromet"] < 100
        diff_out_of_bounds = roi_gauges["area_diff_perc"].lt(-20) | roi_gauges["area_diff_perc"].gt(20)
        use_strict = area_small & diff_out_of_bounds
        acc_coeff_by_gauge = np.where(use_strict, ACC_COEFF_STRICT, ACC_COEFF_DEFAULT)
    else:
        acc_coeff_by_gauge = np.full(len(roi_gauges), ACC_COEFF_DEFAULT)

    ACC_COEFF = ACC_COEFF_DEFAULT  # default for worker init

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

    # Prepare task arguments (gauge_id, x, y, name_en, acc_coeff)
    tasks: list[tuple[str, float, float, str, float]] = [
        (
            str(gauge_id),
            gauge.geometry.x,
            gauge.geometry.y,
            gauge["name_en"],
            float(acc_coeff_by_gauge[i]),
        )
        for i, (gauge_id, gauge) in enumerate(roi_gauges.iterrows())
    ]
    if stream_save:
        # Skip gauges that already have a saved watershed file (resume support)
        existing = {
            p.stem.replace(f"roi_{roi_id}_watershed_", "")
            for p in roi_temp_dir.glob(f"roi_{roi_id}_watershed_*.gpkg")
        }
        tasks = [t for t in tasks if t[0] not in existing]
        if existing:
            log.info("ROI %d: Resuming, skipping %d already-saved watersheds", roi_id, len(existing))
    total_tasks = len(tasks)

    watersheds_list = []

    if use_multiprocessing and max_workers > 1 and not stream_save:
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

    # Sequential mode (always run if multiprocessing disabled, failed, or stream_save)
    if not use_multiprocessing or max_workers == 1 or not watersheds_list or stream_save:
        if watersheds_list and not stream_save:
            log.info("ROI %d: Continuing with sequential processing for remaining gauges", roi_id)
            # Remove successfully processed gauges
            processed_ids = {w["gauge_id"] for w in watersheds_list}
            tasks = [t for t in tasks if t[0] not in processed_ids]
        elif stream_save:
            # Stream-save: process all sequentially, no list accumulation
            tasks = tasks
            watersheds_list.clear()

        log.info(
            "Processing ROI %d: %d watersheds sequentially%s",
            roi_id,
            len(tasks),
            " (stream-save mode)" if stream_save else " (memory-safe mode)",
        )

        # Initialize worker state in main process
        _init_worker(grid_path, acc_path, fdir_path, D8_DIRMAP, ACC_COEFF)

        # Process each watershed sequentially
        for task in tqdm(tasks, desc=f"ROI {roi_id} gauges", unit="gauge"):
            gauge_id = task[0]
            try:
                result = process_single_watershed(*task)
                if stream_save:
                    # Save immediately to avoid memory buildup; do not keep in list
                    one_gdf = gpd.GeoDataFrame([result], crs="EPSG:4326")
                    one_path = roi_temp_dir / f"roi_{roi_id}_watershed_{gauge_id}.gpkg"
                    one_gdf.to_file(one_path, driver="GPKG")
                    del one_gdf
                    gc.collect()
                else:
                    watersheds_list.append(result)
            except Exception as exc:
                log.error("Gauge %s generated exception: %s", gauge_id, str(exc))

            # Periodic garbage collection (non-stream mode)
            if not stream_save and len(watersheds_list) % 10 == 0:
                gc.collect()

    if stream_save:
        n_saved = len(list(roi_temp_dir.glob(f"roi_{roi_id}_watershed_*.gpkg")))
        log.info(
            "ROI %d: %d/%d watersheds saved as individual files. Merge later with: merge_stream_saved_roi(%d, geom_path)",
            roi_id,
            n_saved,
            len(roi_gauge_ids),
            roi_id,
        )
        return gpd.GeoDataFrame()

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

        return watersheds_gdf
    else:
        log.warning("ROI %d: No watersheds were successfully processed", roi_id)
        return gpd.GeoDataFrame()


def main():
    """Main execution function."""
    # Set up paths
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data"

    save_path = data_dir / "CAMELS_RU"
    save_path.mkdir(parents=True, exist_ok=True)
    geom_path = save_path / "geometry_v2"
    geom_path.mkdir(parents=True, exist_ok=True)

    elv_path = data_dir / "Russia" / "SpatialData" / "MeritRU"

    # Load gauge data
    log.info("Loading gauge data...")
    full_gauges = gpd.read_file(save_path / "geometry" / "camels_gauges_edit_v2.gpkg")
    full_gauges.set_index("gauge_id", inplace=True)

    # Load HYBAS mapping
    log.info("Loading HYBAS mapping...")
    hybas_mapping = gpd.read_file(data_dir / "Russia" / "Geometry" / "HybasSelection.gpkg")

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
    all_gauges = []

    for roi_id, roi_gauges_df in gauges_by_roi:
        # Get the gauge IDs directly from the grouped dataframe index
        roi_gauge_ids = roi_gauges_df.index.tolist()

        log.info("=" * 60)
        log.info("Processing ROI %d with %d gauges", roi_id, len(roi_gauge_ids))

        try:
            watersheds_gdf = process_roi_watersheds(
                roi_id=int(roi_id),
                roi_gauge_ids=roi_gauge_ids,
                full_gauges=full_gauges,
                elv_path=elv_path,
                geom_path=geom_path,
                use_multiprocessing=False,  # Set to True to enable multiprocessing (risky!)
                batch_size=10,
                max_workers=1,  # Only used if use_multiprocessing=True
                stream_save_roi_ids=[22],  # Save each watershed to its own file to avoid OOM
            )

            if not watersheds_gdf.empty:
                all_watersheds.append(watersheds_gdf)
                roi_gauges_merge = full_gauges.loc[roi_gauge_ids, :].copy()
                roi_gauges_merge = roi_gauges_merge.to_crs(epsg=4326)
                all_gauges.append(roi_gauges_merge)
                _write_combined_outputs(all_watersheds, all_gauges, geom_path)

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
        output_path = geom_path / "camels_ru_watersheds_v2.gpkg"
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
