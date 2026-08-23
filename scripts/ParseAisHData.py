import multiprocessing as mp
from pathlib import Path

import pandas as pd
from tqdm.auto import tqdm

from data_processing.ais import ais_merger, fill_short_gaps, level_to_csv

LEVEL_XLS_DIR = Path("data/Russia/AISxls/levels_xls")
LEVEL_CSV_DIR = Path("data/CAMELS_RU/AisLevelCsv")
LEVEL_OUT_DIR = Path("data/CAMELS_RU/HydroData/Level")

GTS_XLS_DIR = Path("data/Russia/AISxls/levels_GTS_xls")
GTS_CSV_DIR = Path("data/CAMELS_RU/AisLevelGTSCsv")
GTS_OUT_DIR = Path("data/CAMELS_RU/HydroData/LevelGTS")


def mp_ais_level(level_file: Path) -> dict:
    """Parse a single AIS level .xls file into per-gauge CSVs."""
    return level_to_csv(data_path=level_file, save_folder=LEVEL_CSV_DIR)


def mp_ais_level_gts(level_file: Path) -> dict:
    """Parse a single AIS GTS level .xls file into per-gauge CSVs."""
    return level_to_csv(data_path=level_file, save_folder=GTS_CSV_DIR)


def build_heights_df(label_records: list[dict]) -> pd.DataFrame:
    """Build a deduplicated gauge-heights DataFrame from label_id dicts."""
    df = pd.concat(
        [pd.DataFrame(record).T for record in label_records],
        ignore_index=False,
    )
    df = df.rename(columns={0: "name", 1: "height"})
    return df[~df.index.duplicated(keep="first")]


def replace_zeros_with_seasonal(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Replace zero values with day-of-year median (excluding zeros).

    Water level of exactly 0 is almost certainly a data artifact in the AIS
    export. The seasonal median is a reasonable fill because level has strong
    annual periodicity.
    """
    zero_mask = df[column] == 0
    if not zero_mask.any():
        return df

    df["month"] = df.index.month
    df["day"] = df.index.day
    seasonal_med = df[~zero_mask].groupby(["month", "day"])[column].median()

    # Vectorized fill via index join
    zero_idx = df.index[zero_mask]
    keys = pd.MultiIndex.from_arrays([zero_idx.month, zero_idx.day])
    fill_vals = seasonal_med.reindex(keys)
    df.loc[zero_mask, column] = fill_vals.values

    return df.drop(columns=["month", "day"])


def interpolate_level(file: Path, column: str = "lvl_sm", *, interp_limit: int = 6) -> None:
    """Replace zeros with the seasonal median, then fill interior gaps of at most ``interp_limit`` days.

    Both alterations are recovered and flagged at packaging time by
    ``scripts/derive_water_level_fill_mask.py`` (quality_flag 2 and 1).
    """
    df = pd.read_csv(file, index_col="date", parse_dates=True)
    df = df[~df.index.duplicated(keep="first")]
    df = replace_zeros_with_seasonal(df, column)
    df[column] = fill_short_gaps(df[column], max_gap=interp_limit)
    df.to_csv(file)


if __name__ == "__main__":
    # ── Step 1: Regular levels ────────────────────────────────────────────
    h_path = list(LEVEL_XLS_DIR.glob("*.xls"))
    with mp.Pool() as pool:
        h_lbl_asso = list(
            tqdm(pool.imap(mp_ais_level, h_path), total=len(h_path), desc="Parsing level .xls files")
        )

    heights = build_heights_df(h_lbl_asso)
    heights.to_csv(LEVEL_CSV_DIR / "gauge_heights.csv")

    ais_merger(
        files_list=list(LEVEL_CSV_DIR.glob("*/*.csv")),
        save_storage=LEVEL_OUT_DIR,
        initial_column="level",
        column_variable="lvl_sm",
    )

    for file in tqdm(list(LEVEL_OUT_DIR.glob("*.csv")), desc="Interpolating level files"):
        interpolate_level(file)

    # ── Step 2: GTS levels ────────────────────────────────────────────────
    h_path_gts = list(GTS_XLS_DIR.glob("*.xls"))
    with mp.Pool() as pool:
        h_lbl_asso_gts = list(
            tqdm(
                pool.imap(mp_ais_level_gts, h_path_gts),
                total=len(h_path_gts),
                desc="Parsing GTS level .xls files",
            )
        )

    heights_gts = build_heights_df(h_lbl_asso_gts)
    heights_gts.index.name = "gauge_id"
    heights_gts.index = heights_gts.index.astype(str)
    heights_gts.to_csv(GTS_CSV_DIR / "GTS_heights.csv")

    ais_merger(
        files_list=list(GTS_CSV_DIR.glob("*/*.csv")),
        save_storage=GTS_OUT_DIR,
        initial_column="lvl_sm",
        column_variable="lvl_sm",
    )

    for file in tqdm(list(GTS_OUT_DIR.glob("*.csv")), desc="Interpolating GTS level files"):
        interpolate_level(file, interp_limit=15)
