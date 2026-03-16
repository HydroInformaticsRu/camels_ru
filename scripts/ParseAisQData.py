import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from data_processing.ais import ais_merger, discharge_to_csv

DISCHARGE_XLS_DIR = Path("data/Russia/AISxls/discharge_xls")
DISCHARGE_CSV_DIR = Path("data/CAMELS_RU/AisDischargeCsv")
DISCHARGE_OUT_DIR = Path("data/CAMELS_RU/HydroData/Discharge")


def mp_ais_discharge(discharge_file: Path) -> dict:
    """Parse a single AIS discharge .xls file into per-gauge CSVs."""
    return discharge_to_csv(data_path=discharge_file, save_folder=DISCHARGE_CSV_DIR)


def interpolate_discharge(file: Path, column: str = "q_cms") -> None:
    """Polynomial-interpolate short gaps, then clamp negatives to NaN."""
    df = pd.read_csv(file, index_col="date", parse_dates=True)
    df = df[~df.index.duplicated(keep="first")]
    df[column] = df[column].interpolate(method="polynomial", order=2, limit=6)
    if (df[column] < 0).any():
        df.loc[df[column] < 0, column] = np.nan
    df.to_csv(file)


if __name__ == "__main__":
    # Step 1: parse .xls → per-gauge CSVs
    q_path = list(DISCHARGE_XLS_DIR.glob("*.xls"))
    with mp.Pool(processes=6) as pool:
        list(
            tqdm(
                pool.imap(mp_ais_discharge, q_path),
                total=len(q_path),
                desc="Parsing discharge .xls files",
            )
        )

    # Step 2: merge per-gauge CSVs into a single time series per gauge
    ais_merger(
        files_list=list(DISCHARGE_CSV_DIR.glob("*/*.csv")),
        save_storage=DISCHARGE_OUT_DIR,
        initial_column="discharge",
        column_variable="q_cms",
    )

    # Step 3: interpolate short gaps and clamp negatives
    files = list(DISCHARGE_OUT_DIR.glob("*.csv"))
    for file in tqdm(files, desc="Interpolating discharge files"):
        interpolate_discharge(file)
