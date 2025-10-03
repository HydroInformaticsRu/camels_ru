"""Extracts hydrographic attributes from the HydroATLAS dataset for specified watersheds.

This script processes watershed and streamgage geometries, extracts relevant
hydrographic attributes from the BasinATLAS v10 geodatabase, and saves the
results to a CSV file. It uses multiprocessing to parallelize the extraction
process, significantly improving performance for large numbers of watersheds.

The main workflow is as follows:
1.  **Load Data**: Reads watershed and streamgage geometries from GeoPackage files.
2.  **Parallel Processing**: Submits a task for each watershed to a
    `ProcessPoolExecutor`. Each task, executed by the `ha_worker` function,
    extracts hydrographic data for one watershed.
3.  **Data Extraction**: The `ha_worker` function (from `src.data_processing`)
    handles the core logic of interacting with the HydroATLAS geodatabase and
    associated raster files.
4.  **Collect and Save Results**: Aggregates the results from all worker processes
    into a single pandas DataFrame and saves it to a CSV file.

Configuration parameters, such as file paths, are defined at the top of the
script.

Functions:
    main: Orchestrates the entire data extraction and processing workflow.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from pathlib import Path
import sys
from typing import Any

import geopandas as gpd
import pandas as pd
from tqdm.auto import tqdm

sys.path.append(str(Path(__file__).parent.parent))
from src.static.hydro_atlas_reader import ha_worker
from src.utils.logger import setup_logger

# --- Logger Setup ---
logger = setup_logger("hydroAtlasWS", log_file="logs/hydroAtlasWS.log")

# --- Configuration ---
HYDRO_KW: dict[str, Any] = {
    "gdb_path": Path("data/BasinATLAS_v10.gdb/"),
    "elev_path": Path("data/Rasters/gage_elv/"),
    "fdir_path": Path("data/DEM/MeritDEM"),
    "tmp_dir": Path("data/.tmp_raster"),
}
WATERSHED_FILE = "data/Geometry/WatershedGeomCAMELS.gpkg"
GAGES_FILE = "data/Geometry/GaugeGeomCAMELS.gpkg"
OUTPUT_CSV = "data/attributes/hydro_atlas_cis_camels.csv"


def main():
    """Main function to orchestrate the extraction of HydroATLAS attributes."""
    try:
        ws = gpd.read_file(WATERSHED_FILE).set_index("gage_id")
        gages = gpd.read_file(GAGES_FILE).set_index("gage_id")
    except FileNotFoundError as e:
        logger.error(f"Required file not found: {e}")
        return

    ha_res: dict[str, pd.Series] = {}
    max_workers = max(cpu_count() - 1, 1)
    logger.info(f"Starting HydroATLAS extraction with {max_workers} workers.")

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                ha_worker,
                gid,
                ws=ws.loc[gid, "geometry"],
                gauge=gages.loc[[gid], "geometry"],
                **HYDRO_KW,
            ): gid
            for gid in ws.index
        }

        for fut in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Extracting HydroATLAS Attributes",
        ):
            gid = futures[fut]
            try:
                ha_res[gid] = fut.result()[1]
            except Exception as exc:
                logger.error(f"Error processing gauge {gid}: {exc}")

    if not ha_res:
        logger.warning("No data was extracted. The output file will not be created.")
        return

    static_df = pd.DataFrame.from_dict(ha_res, orient="index")
    static_df.index.name = "gage_id"
    static_df.to_csv(OUTPUT_CSV)
    logger.info(f"Successfully extracted attributes for {len(ha_res)} watersheds.")
    logger.info(f"Results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
