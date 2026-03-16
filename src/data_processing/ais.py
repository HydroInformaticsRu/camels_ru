"""AIS GMVO data parsing utilities.

Parses discharge and water level exports from AIS GMVO (https://gmvo.skniivh.ru/)
Excel format into per-gauge CSV files with standardized daily time series.
"""

from pathlib import Path
import re

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from utils.logger import setup_logger

logger = setup_logger(Path(__file__).name, log_file="")

# Pre-compiled regex: keep only digits and dots
_NON_NUMERIC_RE = re.compile(r"[^0-9.]")

# 30-day months in the AIS 31-row grid (April, June, September, November)
_SHORT_MONTH_COLS = ("Unnamed: 4", "Unnamed: 6", "Unnamed: 9", "Unnamed: 11")


# ---------------------------------------------------------------------------
# Cell-level helpers
# ---------------------------------------------------------------------------


def _clean_cell(x: object) -> str:
    """Normalize AIS cell: Cyrillic hydro codes -> '0', comma -> dot, strip non-numeric.

    "npscx" (flow passing) and "npms" (frozen) are standard AIS notation.
    """
    s = str(x).replace("прсх", "0").replace("прмз", "0").replace(",", ".")
    return _NON_NUMERIC_RE.sub("", s)


def _to_float(val: object) -> float:
    """Convert a cleaned cell value to float.

    Returns NaN for non-string padding (from _trim_short_months), and -9999
    sentinel for empty/no-data strings. The sentinel survives the NaN filter
    and is replaced with NaN later in _df_from_observations.
    """
    if not isinstance(val, str):
        return np.nan  # padding cells set by _trim_short_months
    if not val or val.isspace():
        return -9999.0  # no-observation sentinel (e.g. "нб" cleaned to "")
    s = val.rstrip("-")
    if not s:
        return -9999.0
    try:
        return float(s)
    except ValueError:
        return np.nan


def _df_from_observations(
    observations: np.ndarray, dates: pd.DatetimeIndex, col_name: str
) -> pd.DataFrame:
    """Build DataFrame from flat observation array + dates, replacing -9999 with NaN."""
    df = pd.DataFrame({"date": dates, col_name: observations})
    df.loc[df[col_name] == -9999, col_name] = np.nan
    return df


# ---------------------------------------------------------------------------
# Block-level helpers (operating on a 31x12 year-grid)
# ---------------------------------------------------------------------------


def _interpolate_dots(selection: pd.DataFrame) -> None:
    """Replace lone '.' cells with the mean of vertical neighbors (in-place)."""
    if "." not in selection.values:
        return

    mask = (selection == ".").values
    rows, cols = np.divmod(np.flatnonzero(mask), selection.shape[1])

    for r, c in zip(rows, cols, strict=False):
        try:
            prev = pd.to_numeric(selection.iloc[r - 1, c])
        except (IndexError, ValueError):
            prev = pd.to_numeric(selection.iloc[r + 1, c])
        try:
            nxt = pd.to_numeric(selection.iloc[r + 1, c])
        except (IndexError, ValueError):
            nxt = pd.to_numeric(selection.iloc[r - 1, c])
        selection.iat[r, c] = str(np.mean([prev, nxt]))


def _trim_short_months(selection: pd.DataFrame, year_days: int) -> None:
    """NaN-pad the 31-row grid for months with fewer than 31 days."""
    feb = "Unnamed: 2"
    if year_days == 365:
        # Non-leap: Feb has 28 days -> last 3 rows are padding
        selection.loc[:, feb].values[-3:] = [np.nan, np.nan, np.nan]
    elif year_days == 366:
        # Leap: Feb has 29 days -> day 29 may be blank, last 2 are padding
        if selection.loc[:, feb].values[-3] == "":
            try:
                avg = selection.loc[selection.index[:-3], feb].astype(int).mean()
                selection.loc[:, feb].values[-3] = str(int(avg))
            except ValueError:
                pass
            selection.loc[:, feb].values[-2:] = [np.nan, np.nan]
        else:
            selection.loc[:, feb].values[-2:] = [np.nan, np.nan]

    # 30-day months: last row is padding
    for col in _SHORT_MONTH_COLS:
        selection.loc[:, col].values[-1:] = [np.nan]


def _process_year_block(
    file_df: pd.DataFrame,
    block_idx: int,
    monthes_range: list[int],
    year_fields: list[int],
    col_name: str,
) -> pd.DataFrame | None:
    """Parse one year-block (31x12 grid) into a tidy (date, value) DataFrame.

    Returns None on parsing failure (e.g. date/observation length mismatch).
    """
    month_days = 31
    sel = file_df.iloc[monthes_range[block_idx] : monthes_range[block_idx] + month_days, 1:]
    sel = sel.map(_clean_cell)
    sel.columns = [f"Unnamed: {c}" for c in range(1, 13)]

    year = file_df.iloc[year_fields[block_idx], 1]
    dates = pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31")

    _trim_short_months(sel, len(dates))
    _interpolate_dots(sel)

    # Flatten column-major: each column is one month, rows are days 1-31
    flat = np.array(list(map(_to_float, sel.to_numpy().T.flatten())), dtype=float)
    flat = flat[~np.isnan(flat)]

    try:
        return _df_from_observations(flat, dates, col_name)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public API: discharge
# ---------------------------------------------------------------------------


def discharge_to_csv(data_path: Path, save_folder: Path) -> dict:
    """Parse AIS GMVO discharge .xls export into per-gauge CSV files.

    Args:
        data_path: Path to .xls file from AIS GMVO discharge export.
        save_folder: Folder where per-gauge CSVs will be saved.

    Returns:
        Dict mapping river_id -> [DataFrame] of daily discharge.
    """
    save_path = save_folder / data_path.stem
    save_path.mkdir(exist_ok=True, parents=True)

    # Read file -- format depends on encoding
    try:
        river_step, river_label, year_step = 4, 6, 5
        month_step, table_step = 9, 47
        xml = pd.read_html(data_path, decimal=".", thousands=" ")
        file_df = xml[0]
    except UnicodeDecodeError:
        river_step, river_label, year_step = 0, 2, 1
        month_step, table_step = 5, 53
        file_df = pd.read_excel(data_path, skiprows=18, skipfooter=0)

    monthes_range = list(range(month_step, file_df.shape[0], table_step))
    river_fields = list(range(river_step, file_df.shape[0], table_step))
    river_labels = list(range(river_label, file_df.shape[0], table_step))
    year_fields = list(range(year_step, file_df.shape[0], table_step))
    n_blocks = len(monthes_range)

    river_ids = np.array(
        [file_df.iloc[river_fields[i], 1] for i in range(n_blocks)],
        dtype=np.int32,
    )
    river_names = np.array([file_df.iloc[river_labels[i], 1] for i in range(n_blocks)])

    unique_rivers = np.unique(river_ids)
    results: dict[int, list[pd.DataFrame]] = {int(r): [] for r in unique_rivers}

    # Single pass: process each year-block once and assign to its river
    for i in range(n_blocks):
        river_id = int(river_ids[i])
        if river_id not in results:
            continue

        df = _process_year_block(file_df, i, monthes_range, year_fields, col_name="discharge")
        if df is not None:
            results[river_id].append(df)
        else:
            logger.warning(
                "%s: length mismatch for river %d at year %s",
                data_path.name,
                river_id,
                file_df.iloc[year_fields[i], 1],
            )

    # Build label_id mapping (river_id -> [river_name])
    label_id: dict[int, list] = {}
    for i, r_id in enumerate(river_ids):
        if r_id not in label_id:
            label_id[int(r_id)] = [river_names[i]]

    # Concatenate per-river DataFrames and save
    for river_id, frames in results.items():
        if frames:
            combined = pd.concat(frames).reset_index(drop=True)
            results[river_id] = [combined]
            combined.to_csv(save_path / f"{river_id}.csv", index=False)

    return results


# ---------------------------------------------------------------------------
# Public API: water level
# ---------------------------------------------------------------------------


def level_to_csv(data_path: Path, save_folder: Path) -> dict:
    """Parse AIS GMVO water level .xls export into per-gauge CSV files.

    Args:
        data_path: Path to .xls file from AIS GMVO level export.
        save_folder: Folder where per-gauge CSVs will be saved.

    Returns:
        Dict mapping river_id -> [river_name, baltic_height].
    """
    save_path = save_folder / data_path.stem
    save_path.mkdir(exist_ok=True, parents=True)

    try:
        river_step, river_label, year_step, m_bs_step = 52, 54, 53, 55
        month_step, table_step = 59, 49
        xml = pd.read_html(data_path, decimal=".", thousands=" ")
        file_df = xml[0]
    except UnicodeDecodeError:
        river_step, river_label, year_step, m_bs_step = 0, 2, 1, 3
        month_step, table_step = 7, 55
        file_df = pd.read_excel(data_path, skiprows=39, skipfooter=0)

    monthes_range = list(range(month_step, file_df.shape[0], table_step))
    river_fields = list(range(river_step, file_df.shape[0], table_step))
    river_labels = list(range(river_label, file_df.shape[0], table_step))
    m_bs_fields = list(range(m_bs_step, file_df.shape[0], table_step))
    year_fields = list(range(year_step, file_df.shape[0], table_step))
    n_blocks = len(monthes_range)

    river_ids = np.array(
        [file_df.iloc[river_fields[i], 1] for i in range(n_blocks)],
        dtype=np.int32,
    )
    river_names = np.array([file_df.iloc[river_labels[i], 1] for i in range(n_blocks)])
    m_bs_values = np.array(
        [file_df.iloc[m_bs_fields[i], 1] for i in range(n_blocks)],
        dtype=np.float32,
    )

    unique_rivers = np.unique(river_ids)
    results: dict[int, list[pd.DataFrame]] = {int(r): [] for r in unique_rivers}

    # Single pass: process each year-block once and assign to its river
    for i in range(n_blocks):
        river_id = int(river_ids[i])
        if river_id not in results:
            continue

        df = _process_year_block(file_df, i, monthes_range, year_fields, col_name="lvl_sm")
        if df is not None:
            results[river_id].append(df)
        else:
            logger.warning(
                "%s: length mismatch for river %d at year %s",
                data_path.name,
                river_id,
                file_df.iloc[year_fields[i], 1],
            )

    # Build label_id mapping (river_id -> [name, baltic_height])
    label_id: dict[int, list] = {}
    for i, r_id in enumerate(river_ids):
        if r_id not in label_id:
            label_id[int(r_id)] = [river_names[i], m_bs_values[i]]

    # Concatenate per-river DataFrames and save
    for river_id, frames in results.items():
        if frames:
            pd.concat(frames).to_csv(save_path / f"{river_id}.csv", index=False)

    return label_id


# ---------------------------------------------------------------------------
# Public API: merger (combine per-district CSVs into unified time series)
# ---------------------------------------------------------------------------


def ais_merger(
    files_list: list[Path],
    save_storage: Path,
    initial_column: str,
    column_variable: str,
) -> None:
    """Merge per-gauge CSVs into standardized daily time series (2008-2023).

    Groups source files by gauge, merges all sources in memory, then writes
    once per gauge. This avoids the race condition of parallel read-modify-write
    on shared output files.

    Args:
        files_list: Paths to per-gauge CSV files to merge.
        save_storage: Output directory for merged time series.
        initial_column: Column name in input files to rename.
        column_variable: Target column name after renaming.
    """
    save_storage.mkdir(exist_ok=True, parents=True)

    # Group source files by gauge_id (filename stem)
    gauge_files: dict[str, list[Path]] = {}
    for f in files_list:
        gauge_files.setdefault(f.stem, []).append(f)

    for gauge_id, files in tqdm(
        gauge_files.items(), desc="Merging per-gauge files", total=len(gauge_files)
    ):
        out_path = save_storage / f"{gauge_id}.csv"

        base_df = pd.DataFrame(
            index=pd.date_range(start="2008-01-01", end="2023-12-31", freq="D"),
            columns=[column_variable],
            dtype=float,
        )
        base_df.index.name = "date"

        for f in files:
            new_data = pd.read_csv(f, index_col="date", parse_dates=True)
            new_data = new_data.rename(columns={initial_column: column_variable})
            base_df = base_df.combine_first(new_data)

        # Drop duplicate dates (can occur when a river appears twice in one
        # AIS export, e.g. correction entries)
        base_df = base_df[~base_df.index.duplicated(keep="first")]
        base_df.to_csv(out_path)
