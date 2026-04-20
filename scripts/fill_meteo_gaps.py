"""Fill ERA5 temperature gaps for the 24 release gauges with incomplete coverage.

Root causes (inspected 2026-04-17 via ``.tmp/inspect_era5_problem_gauges.py``):

* **DOMAIN_EDGE (7 gauges)** – basins sit east of 170°E; the 2008–2022 ERA5-Land
  tiles end at lon 170°E, so 15/16 years of coverage is NaN. Strategy: read the
  raw tiles at lat = basin centroid, lon = 170.0°E (the easternmost valid column)
  to synthesise a 2008–2022 time series, then splice the gauge's own (valid)
  2023 values on top.

* **YEAR_2023_PARTIAL (17 gauges)** – basins fall inside the ~37 %-NaN
  region of the under-sized 2023 ERA5-Land tiles. 2008–2022 coverage is 100 %,
  which gives 15 donor years for DOY-climatology fill of 2023.

Outputs:

* Filled per-gauge CSVs written to
  ``data/Russia/MeteoData/CamelsRU/era5_land_filled/<gauge_id>.csv`` – same
  column layout as the source CSVs.
* ``forcing_note`` mapping written to
  ``data/Russia/MeteoData/CamelsRU/era5_land_filled/forcing_notes.json`` –
  consumed by ``scripts/package_dataset.py`` to populate
  ``gauge_summary.csv``.

The originals under ``data/Russia/MeteoData/CamelsRU/era5_land/`` are never
modified; ``package_dataset.py`` reads filled CSVs first and falls back to the
original if a gauge's filled copy is absent.

Run with ``pixi run python scripts/fill_meteo_gaps.py``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

# -- Configuration --------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_ERA5 = Path("/media/dmbrmv/ssd_2tb/Russia/MeteoData/ParsedMonthly/era5_land")
SRC_ERA5 = REPO_ROOT / "data" / "Russia" / "MeteoData" / "CamelsRU" / "era5_land"
OUT_ERA5 = REPO_ROOT / "data" / "Russia" / "MeteoData" / "CamelsRU" / "era5_land_filled"
BOUNDARIES = REPO_ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_boundaries.gpkg"

DATE_START = "2008-01-01"
DATE_END = "2023-12-31"
MIN_DONOR_YEARS = 3
ERA5_EAST_LIMIT_LON = 170.0  # easternmost valid longitude in 2008-2022 tiles

# Problem gauges identified by .tmp/inspect_era5_problem_gauges.py (2026-04-17)
DOMAIN_EDGE_GAUGES = ["1433", "1434", "1507", "1508", "1587", "1611", "2241"]
YEAR_2023_PARTIAL_GAUGES = [
    "1104",
    "1105",
    "1107",
    "1625",
    "11674",
    "2155",
    "2272",
    "49116",
    "70626",
    "75443",
    "78067",
    "78076",
    "78116",
    "78118",
    "81602",
    "81748",
    "9194",
]

TEMP_COLS = ["t_mean", "t_min", "t_max"]
RAW_VARS = ["t_mean", "t_min", "t_max", "prcp"]

log = logging.getLogger("fill_meteo_gaps")


# -- Utilities ------------------------------------------------------------


def _load_centroids() -> dict[str, tuple[float, float]]:
    """Return {gauge_id: (centroid_lat, centroid_lon)} for all release gauges.

    Uses bounding-box midpoints rather than true polygon centroids because the
    nearest-cell fallback for domain-edge gauges only reads longitude ``170°E``
    (hard-coded) and a coarse basin-midpoint latitude. For small basins bbox
    midpoint and true centroid coincide within one grid cell; for the two large
    domain-edge basins (1433 = 6,796 km², 1587 = 18,404 km²) the spread is
    <0.15° — still within one ERA5-Land grid cell (0.1°).
    """
    ws = gpd.read_file(BOUNDARIES)
    ws["gauge_id"] = ws["gauge_id"].astype(str)
    bounds = ws.geometry.bounds  # minx, miny, maxx, maxy — geographic CRS
    centroid_lon = (bounds["minx"] + bounds["maxx"]) / 2
    centroid_lat = (bounds["miny"] + bounds["maxy"]) / 2
    return {
        gid: (float(lat), float(lon))
        for gid, lat, lon in zip(ws["gauge_id"].to_numpy(), centroid_lat, centroid_lon, strict=True)
    }


def _read_source_csv(gauge_id: str) -> pd.DataFrame:
    path = SRC_ERA5 / f"{gauge_id}.csv"
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    df = df.loc[DATE_START:DATE_END]
    # Guard against accidental date-index duplicates.
    if not df.index.is_unique:
        df = df[~df.index.duplicated(keep="first")]
    return df


def _doy_climatology_fill(
    df: pd.DataFrame,
    cols: list[str],
    donor_year_range: tuple[int, int] = (2008, 2022),
    min_donor_years: int = MIN_DONOR_YEARS,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fill NaN entries in *cols* using day-of-year climatology.

    Donor values are drawn from non-NaN rows in *donor_year_range* (inclusive)
    of the *same* DataFrame. A given NaN day is filled only if at least
    ``min_donor_years`` donor years provide a non-NaN value for its DOY.
    Returns the filled frame and a per-column count of filled cells.
    """
    out = df.copy()
    filled: dict[str, int] = {}
    doy = out.index.dayofyear
    year = out.index.year
    donor_mask = (year >= donor_year_range[0]) & (year <= donor_year_range[1])
    for col in cols:
        vals = out[col].to_numpy()
        nan_mask = np.isnan(vals)
        if not nan_mask.any():
            filled[col] = 0
            continue
        # Per-DOY donor mean + donor count (from donor window only).
        donor_slice = out.loc[donor_mask, col]
        donor_doy = donor_slice.index.dayofyear
        donor_df = pd.DataFrame({"doy": donor_doy, "val": donor_slice.to_numpy()})
        donor_stats = donor_df.groupby("doy")["val"].agg(["mean", "count"])
        # Map DOY → (mean, count) per row.
        mean_per_row = donor_stats["mean"].reindex(doy).to_numpy()
        count_per_row = donor_stats["count"].reindex(doy).to_numpy()
        fill_here = nan_mask & (count_per_row >= min_donor_years) & ~np.isnan(mean_per_row)
        vals[fill_here] = mean_per_row[fill_here]
        out[col] = vals
        filled[col] = int(fill_here.sum())
    return out, filled


def _find_nearest_land_cells(
    points_by_id: dict[str, tuple[float, float]],
    reference_tile: Path,
    max_west_scan_degrees: float = 5.0,
) -> dict[str, tuple[float, float]]:
    """Resolve each requested ``(lat, target_lon)`` to the nearest valid land cell.

    ERA5-Land masks ocean as NaN. A gauge sampled at ``170°E`` but sitting at a
    latitude where 170°E is ocean (e.g. Chaunskaya Bay at 69.58°N) returns all
    NaN. We scan westward in 0.1° grid steps from the requested longitude and
    return the first cell whose ``t_mean[0]`` is finite. If nothing is found
    within ``max_west_scan_degrees``, we log an error and fall through with the
    original point (the caller will then see NaN fills and can escalate).
    """
    with xr.open_dataset(reference_tile) as ds:
        lat_name = "latitude" if "latitude" in ds.coords else "lat"
        lon_name = "longitude" if "longitude" in ds.coords else "lon"
        resolved: dict[str, tuple[float, float]] = {}
        for gid, (lat, lon) in points_by_id.items():
            found = None
            lon_try = lon
            while lon_try >= lon - max_west_scan_degrees:
                pt = ds.sel({lat_name: lat, lon_name: lon_try}, method="nearest")
                val = float(pt["t_mean"][0])
                if val == val:  # not NaN
                    found = (float(pt[lat_name]), float(pt[lon_name]))
                    break
                lon_try -= 0.1
            if found is None:
                log.error(
                    "gauge %s: no land cell found within %.1f° west of lon %.2f at lat %.2f",
                    gid,
                    max_west_scan_degrees,
                    lon,
                    lat,
                )
                resolved[gid] = (lat, lon)
            else:
                resolved[gid] = found
                if abs(found[1] - lon) > 0.05:
                    log.info(
                        "gauge %s: land cell shifted west of target lon %.2f -> used %.2f°E (lat %.2f)",
                        gid,
                        lon,
                        found[1],
                        found[0],
                    )
    return resolved


def _extract_raw_era5_batch(
    points_by_id: dict[str, tuple[float, float]],
    years: range,
) -> dict[str, pd.DataFrame]:
    """Extract per-gauge raw ERA5 time series in a single pass over monthly tiles.

    Each monthly NetCDF is opened exactly once and every requested
    ``(lat, lon)`` point is read from it before the file is closed. Scales as
    O(tiles) rather than O(tiles × gauges), which is the difference between
    ~3 and ~20 minutes for 15 years × 7 domain-edge gauges on spinning-disk I/O.
    """
    if not points_by_id:
        return {}
    # Pre-allocate one list of per-month frames per gauge id.
    frames_by_id: dict[str, list[pd.DataFrame]] = {gid: [] for gid in points_by_id}

    for year in years:
        for mo in range(1, 13):
            path = RAW_ERA5 / f"{year:04d}_{mo:02d}.nc"
            if not path.exists():
                log.warning("missing raw tile %s", path.name)
                continue
            with xr.open_dataset(path) as ds:
                lat_name = "latitude" if "latitude" in ds.coords else "lat"
                lon_name = "longitude" if "longitude" in ds.coords else "lon"
                time_name = "time" if "time" in ds.dims else list(ds.dims)[0]
                time_index = pd.DatetimeIndex(ds[time_name].to_numpy(), name="date")
                for gid, (lat, lon) in points_by_id.items():
                    point = ds.sel({lat_name: lat, lon_name: lon}, method="nearest")
                    frames_by_id[gid].append(
                        pd.DataFrame(
                            {v: point[v].to_numpy() for v in RAW_VARS if v in point.data_vars},
                            index=time_index,
                        )
                    )

    out: dict[str, pd.DataFrame] = {}
    for gid, frames in frames_by_id.items():
        df = pd.concat(frames).sort_index()
        if not df.index.is_unique:
            df = df.groupby(df.index).mean()
        out[gid] = df
    return out


# -- Per-class fill implementations ----------------------------------------


def fill_domain_edge(
    gauge_id: str,
    raw_point_series: pd.DataFrame,
    centroid_lat: float,
    sampled: tuple[float, float],
) -> tuple[pd.DataFrame, str]:
    """Fill 2008–2022 for an east-of-170°E gauge using the nearest-land column.

    2023 rows are preserved as-is because the gauge's own aggregation already
    captured valid values from the wider 2023 tiles. ``raw_point_series`` is
    the single-cell time series produced by ``_extract_raw_era5_batch``.
    ``sampled`` is ``(actual_lat, actual_lon)`` of the cell used — may differ
    from the request if ERA5-Land's ocean mask forced a westward shift.
    """
    src = _read_source_csv(gauge_id)
    raw = raw_point_series.loc[DATE_START:"2022-12-31"]

    out = src.copy()
    pre_2023 = out.index.year < 2023
    for col in TEMP_COLS:
        if col in raw.columns:
            # Only overwrite when the source is NaN (preserves any valid points).
            raw_on_out = raw[col].reindex(out.index)
            mask = pre_2023 & out[col].isna() & raw_on_out.notna()
            out.loc[mask, col] = raw_on_out[mask]
    lat_s, lon_s = sampled
    shift_note = ""
    if abs(lon_s - ERA5_EAST_LIMIT_LON) > 0.05:
        shift_note = (
            f" (shifted {ERA5_EAST_LIMIT_LON - lon_s:.1f}° west of 170°E to clear ERA5-Land ocean mask)"
        )
    note = (
        f"ERA5 temperature filled from raw ERA5-Land at (lat {lat_s:.2f}°, "
        f"lon {lon_s:.2f}°E){shift_note} for 2008–2022; basin sits east of the "
        "locally-downloaded ERA5-Land tile domain. 2023 values retained from "
        "native basin aggregation."
    )
    return out, note


def fill_year_2023_partial(
    gauge_id: str,
) -> tuple[pd.DataFrame, str]:
    """Fill 2023 temperature NaNs using 2008–2022 DOY climatology."""
    src = _read_source_csv(gauge_id)
    before_nan = {col: int(src[col].isna().sum()) for col in TEMP_COLS}
    filled, stats = _doy_climatology_fill(src, TEMP_COLS)
    after_nan = {col: int(filled[col].isna().sum()) for col in TEMP_COLS}
    if any(after_nan[col] > 0 for col in TEMP_COLS):
        log.warning(
            "gauge %s still has NaN after DOY fill: before=%s after=%s",
            gauge_id,
            before_nan,
            after_nan,
        )
    note = (
        "ERA5 temperature 2023 gaps DOY-climatology-filled from 2008–2022 "
        f"record (filled cells per column: {stats})."
    )
    return filled, note


# -- Orchestration --------------------------------------------------------


def process_all(dry_run: bool = False) -> dict[str, dict]:
    """Run both fill classes end-to-end; return a diagnostic per-gauge dict."""
    OUT_ERA5.mkdir(parents=True, exist_ok=True)
    centroids = _load_centroids()
    report: dict[str, dict] = {}
    notes: dict[str, str] = {}

    log.info("== DOMAIN_EDGE (%d gauges) – batched raw-tile read ==", len(DOMAIN_EDGE_GAUGES))
    missing = [g for g in DOMAIN_EDGE_GAUGES if g not in centroids]
    if missing:
        log.error("no centroid for gauges %s – skipping", missing)
    initial_points = {
        gid: (centroids[gid][0], ERA5_EAST_LIMIT_LON) for gid in DOMAIN_EDGE_GAUGES if gid in centroids
    }
    reference_tile = RAW_ERA5 / "2008_01.nc"
    resolved_points = _find_nearest_land_cells(initial_points, reference_tile=reference_tile)
    raw_by_id = _extract_raw_era5_batch(resolved_points, years=range(2008, 2023))
    for gid, raw_df in raw_by_id.items():
        lat_src = centroids[gid][0]
        resolved = resolved_points[gid]
        filled, note = fill_domain_edge(gid, raw_df, centroid_lat=lat_src, sampled=resolved)
        notes[gid] = note
        report[gid] = _summarise(gid, filled, class_="DOMAIN_EDGE", centroid=centroids[gid])
        if not dry_run:
            filled.to_csv(OUT_ERA5 / f"{gid}.csv")

    log.info("== YEAR_2023_PARTIAL (%d gauges) ==", len(YEAR_2023_PARTIAL_GAUGES))
    for gid in YEAR_2023_PARTIAL_GAUGES:
        filled, note = fill_year_2023_partial(gid)
        notes[gid] = note
        lat, lon = centroids.get(gid, (float("nan"), float("nan")))
        report[gid] = _summarise(gid, filled, class_="YEAR_2023_PARTIAL", centroid=(lat, lon))
        if not dry_run:
            filled.to_csv(OUT_ERA5 / f"{gid}.csv")

    if not dry_run:
        with (OUT_ERA5 / "forcing_notes.json").open("w") as fh:
            json.dump(notes, fh, indent=2, sort_keys=True)

    return report


def _summarise(
    gauge_id: str,
    df: pd.DataFrame,
    class_: Literal["DOMAIN_EDGE", "YEAR_2023_PARTIAL"],
    centroid: tuple[float, float],
) -> dict:
    summary: dict = {"class": class_, "centroid": centroid}
    for col in TEMP_COLS:
        vals = df[col].to_numpy()
        mask = ~np.isnan(vals)
        summary[col] = {
            "nan_frac": float(1 - mask.mean()),
            "range": (
                float(np.nanmin(vals)) if mask.any() else None,
                float(np.nanmax(vals)) if mask.any() else None,
            ),
        }
    return summary


def main() -> None:
    """Fill ERA5 temperature gaps for all 24 flagged gauges and emit forcing_notes.json."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    report = process_all()
    # Quick sanity print for the 7 originally-flagged gauges.
    log.info("\n== Post-fill summary for the 7 originally-flagged problem gauges ==")
    for gid in ["1508", "2241", "11674", "81602", "81748", "2155", "9194"]:
        if gid not in report:
            continue
        s = report[gid]
        t = s["t_mean"]
        log.info(
            "  %s [%s]: t_mean nan_frac=%.4f range=(%.2f, %.2f) °C",
            gid,
            s["class"],
            t["nan_frac"],
            t["range"][0] if t["range"][0] is not None else float("nan"),
            t["range"][1] if t["range"][1] is not None else float("nan"),
        )


if __name__ == "__main__":
    main()
