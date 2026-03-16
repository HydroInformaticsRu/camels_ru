"""CAMELS-RU Zenodo Dataset Packaging.

Assembles the CAMELS-RU dataset into the directory structure required for
Zenodo publication.  No figures are produced — this is a data-packaging script.

Steps:
  1. Merge per-ROI watershed/gauge GeoPackages into single geometry files.
  2. Enrich watersheds with Roshydromet area and area-difference metrics.
  3. Merge legacy gauge locations with the current gauge set.
  4. Copy discharge CSVs (by quality grade), forcing NetCDFs, and attributes.
  5. Build Zenodo directory tree:
       zenodo/
         geometry/     — camels_ru_gauges.gpkg, camels_ru_watersheds.gpkg
         attributes/   — camels_ru_attributes.csv
         hydrology/    — discharge CSVs by grade
         meteo/        — forcing time-series
         raw/          — original unprocessed data
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from transliterate import translit

sys.path.append(str(Path(__file__).parent.parent))
from src.utils.logger import setup_logger

gpd.options.io_engine = "pyogrio"
warnings.simplefilter(action="ignore", category=FutureWarning)

log = setup_logger("ZenodoDataset", log_file="../logs/zenodo_dataset.log")

# ── Paths ───────────────────────────────────────────────────────────────────
DATA_ROOT = Path("../data/CAMELS_RU")
GEOMETRY_SRC = DATA_ROOT / "geometry"
DISCHARGE_SRC = DATA_ROOT / "HydroData" / "Compound"
METEO_SRC = DATA_ROOT / "parsed_meteo"
ATTRIBUTES_SRC = DATA_ROOT / "attributes"

ZENODO_ROOT = Path("../data/zenodo")

# ROI identifiers used for per-region watershed files
ROI_IDS: list[int] = [10, 12, 13, 14, 16, 18, 19, 20, 21, 22, 24, 28]


# ── Helper functions ────────────────────────────────────────────────────────
def parse_area_value(value: object) -> float:
    """Parse area values, handling fractions/ranges like '20800/22100'.

    Parameters
    ----------
    value : object
        Raw area value from the Roshydromet catalogue.  May be a number,
        a string with a comma decimal separator, or a 'val1/val2' range.

    Returns:
    -------
    float
        Parsed numeric area, or ``np.nan`` on failure.
    """
    if pd.isna(value):
        return float(np.nan)

    s = str(value).strip().replace(",", ".")

    if "/" in s:
        parts = s.split("/")
        if len(parts) == 2:
            try:
                return (float(parts[0].strip()) + float(parts[1].strip())) / 2.0
            except (ValueError, AttributeError):
                pass

    try:
        return float(s)
    except (ValueError, AttributeError):
        return float(np.nan)


def read_watershed(ws_path: Path) -> gpd.GeoDataFrame:
    """Read a single GeoPackage and set *gauge_id* as index."""
    ws: gpd.GeoDataFrame = gpd.read_file(ws_path)
    ws.set_index("gauge_id", inplace=True)
    return ws


# ── 1. Merge per-ROI watersheds and enrich with Roshydromet area ────────────
def merge_roi_watersheds(
    roi_ids: list[int],
    geometry_temp: Path,
    catalog_csv: Path,
) -> gpd.GeoDataFrame:
    """Concatenate per-ROI watershed files and add area-difference metrics.

    Parameters
    ----------
    roi_ids : list[int]
        Region-of-interest identifiers.
    geometry_temp : Path
        Directory containing ``roi_<id>/roi_<id>_watersheds.gpkg`` files.
    catalog_csv : Path
        Path to the Roshydromet ``hydropost_catalog.csv``.

    Returns:
    -------
    gpd.GeoDataFrame
        Merged watersheds with columns: name, area_km2, area_roshydromet,
        area_diff_perc, geometry.
    """
    import pyogrio  # noqa: E402 — lazy import for optional dependency

    # --- load Roshydromet reference areas ---
    rshdmt = pd.read_csv(catalog_csv)
    rshdmt.rename(
        columns={"Unnamed: 0": "gauge_id", "Unnamed: 7": "area_roshydromet"},
        inplace=True,
    )
    rshdmt = rshdmt[["gauge_id", "area_roshydromet"]].copy()
    rshdmt["gauge_id"] = rshdmt["gauge_id"].astype(str)
    rshdmt["area_roshydromet"] = [parse_area_value(v) for v in rshdmt["area_roshydromet"]]
    rshdmt.set_index("gauge_id", inplace=True)

    # --- build path mapping ---
    ws_paths: dict[int, Path] = {
        rid: geometry_temp / f"roi_{rid}" / f"roi_{rid}_watersheds.gpkg" for rid in roi_ids
    }

    # --- iterate ROIs, enrich, and collect ---
    frames: list[gpd.GeoDataFrame] = []
    for rid in roi_ids:
        try:
            ws = read_watershed(ws_paths[rid])
        except (pyogrio.errors.DataSourceError, FileNotFoundError):
            log.warning("Skipping ROI %d — file not found", rid)
            continue

        for gauge_id in ws.index:
            try:
                ref_area = rshdmt.loc[gauge_id, "area_roshydromet"]
                ws.loc[gauge_id, "area_roshydromet"] = ref_area
                if ref_area > 0:
                    ws.loc[gauge_id, "area_diff_perc"] = (
                        (ref_area - ws.loc[gauge_id, "area_km2"]) / ref_area * 100
                    )
                else:
                    ws.loc[gauge_id, "area_diff_perc"] = np.nan
            except KeyError:
                ws.loc[gauge_id, "area_roshydromet"] = np.nan
                ws.loc[gauge_id, "area_diff_perc"] = np.nan

        ws = ws[["name", "area_km2", "area_roshydromet", "area_diff_perc", "geometry"]]
        ws.to_file(ws_paths[rid], driver="GPKG")
        frames.append(ws)
        log.info("Processed ROI %d — %d watersheds", rid, len(ws))

    if not frames:
        msg = "No watershed files found for any ROI"
        raise FileNotFoundError(msg)

    merged = gpd.GeoDataFrame(pd.concat(frames))
    merged.crs = "EPSG:4326"
    return merged


def merge_roi_gauges(geometry_temp: Path) -> gpd.GeoDataFrame:
    """Concatenate per-ROI gauge files into a single GeoDataFrame."""
    gauge_files = sorted(geometry_temp.glob("roi_*/roi_*_gauges.gpkg"))
    if not gauge_files:
        msg = f"No gauge files found under {geometry_temp}"
        raise FileNotFoundError(msg)

    frames = [gpd.read_file(f) for f in gauge_files]
    merged = gpd.GeoDataFrame(pd.concat(frames))
    merged.set_index("gauge_id", inplace=True)
    merged.crs = "EPSG:4326"
    return merged


# ── 2. Gauge metadata: clean names, transliterate, merge legacy set ─────────
def prepare_gauge_metadata(
    raw_gauges_gpkg: Path,
    legacy_gauges_gpkg: Path | None = None,
) -> gpd.GeoDataFrame:
    """Clean gauge metadata and optionally merge with a legacy gauge file.

    Parameters
    ----------
    raw_gauges_gpkg : Path
        GeoPackage with raw gauge info (wmo_id, name, height, area, geometry).
    legacy_gauges_gpkg : Path | None
        Optional older gauge GeoPackage whose geometries take priority for
        overlapping gauge_ids, and whose unique gauges are appended.

    Returns:
    -------
    gpd.GeoDataFrame
        Cleaned gauge metadata with columns: name_en, name_ru, height, area,
        geometry.
    """
    gdf: gpd.GeoDataFrame = gpd.read_file(raw_gauges_gpkg)
    gdf["wmo_id"] = gdf["wmo_id"].astype(str)
    gdf.set_index("wmo_id", inplace=True)
    gdf.index.name = "gauge_id"
    gdf = gdf[["name", "height", "area", "geometry"]]

    # --- clean area ---
    gdf["area"] = gdf["area"].astype(str).str.replace(r"[^\d.-]", "", regex=True)
    gdf["area"] = pd.to_numeric(gdf["area"], errors="coerce")
    gdf["area"] = gdf["area"].replace(0.0, np.nan)

    # --- clean height ---
    gdf["height"] = [h.replace(",", ".") if isinstance(h, str) else h for h in gdf["height"]]
    gdf["height"] = gdf["height"].astype(str).str.replace(r"[^\d.-]", "", regex=True)
    gdf["height"] = pd.to_numeric(gdf["height"], errors="coerce")

    # --- transliterate station names ---
    gdf.rename(columns={"name": "name_ru"}, inplace=True)
    gdf["name_en"] = [translit(n, "ru", reversed=True) for n in gdf["name_ru"]]
    gdf = gdf[["name_en", "name_ru", "height", "area", "geometry"]]

    # --- merge legacy gauges if provided ---
    if legacy_gauges_gpkg is not None and legacy_gauges_gpkg.exists():
        old: gpd.GeoDataFrame = gpd.read_file(legacy_gauges_gpkg)
        old.set_index("gauge_id", inplace=True)

        common = gdf.index.intersection(old.index)
        log.info("Overwriting geometry for %d common gauges from legacy file", len(common))
        for gid in common:
            gdf.loc[gid, "geometry"] = old.loc[gid, "geometry"]

        only_in_old = old.index.difference(gdf.index)
        if len(only_in_old) > 0:
            to_add = old.loc[only_in_old].copy()
            for col in gdf.columns:
                if col not in to_add.columns and col != "geometry":
                    to_add[col] = np.nan
            to_add = to_add[gdf.columns]
            gdf = gpd.GeoDataFrame(pd.concat([gdf, to_add]))
            log.info("Added %d gauges from legacy file", len(only_in_old))

    return gdf


# ── 3. Copy data into Zenodo directory structure ────────────────────────────
def build_zenodo_tree(zenodo_root: Path) -> dict[str, Path]:
    """Create the Zenodo directory tree and return a mapping of subdirs.

    Returns:
    -------
    dict[str, Path]
        Keys: 'geometry', 'attributes', 'hydrology', 'meteo', 'raw'.
    """
    subdirs = ["geometry", "attributes", "hydrology", "meteo", "raw"]
    paths: dict[str, Path] = {}
    for name in subdirs:
        p = zenodo_root / name
        p.mkdir(parents=True, exist_ok=True)
        paths[name] = p
    log.info("Zenodo directory tree created at %s", zenodo_root)
    return paths


def copy_attributes(src_csv: Path, dest_dir: Path) -> None:
    """Copy HydroATLAS attribute CSV into the Zenodo attributes folder."""
    if not src_csv.exists():
        log.warning("Attribute source not found: %s", src_csv)
        return
    df = pd.read_csv(src_csv, index_col="gauge_id", dtype={"gauge_id": str})
    out = dest_dir / "camels_ru_attributes.csv"
    df.to_csv(out)
    log.info("Attributes written to %s (%d gauges)", out, len(df))


def copy_discharge(src_dir: Path, dest_dir: Path) -> None:
    """Copy discharge CSV files into the Zenodo hydrology folder.

    Preserves the grade-based subdirectory structure (decent / poor).
    """
    if not src_dir.exists():
        log.warning("Discharge source not found: %s", src_dir)
        return

    csv_files = list(src_dir.rglob("*.csv"))
    if not csv_files:
        log.warning("No CSV files found under %s", src_dir)
        return

    for f in csv_files:
        rel = f.relative_to(src_dir)
        target = dest_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)

    log.info("Copied %d discharge files to %s", len(csv_files), dest_dir)


def copy_meteo(src_dir: Path, dest_dir: Path) -> None:
    """Copy meteorological forcing files into the Zenodo meteo folder."""
    if not src_dir.exists():
        log.warning("Meteo source not found: %s", src_dir)
        return

    files = list(src_dir.rglob("*.nc")) + list(src_dir.rglob("*.csv"))
    if not files:
        log.warning("No meteo files found under %s", src_dir)
        return

    for f in files:
        rel = f.relative_to(src_dir)
        target = dest_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)

    log.info("Copied %d meteo files to %s", len(files), dest_dir)


def validate_discharge_coverage(
    discharge_dir: Path,
    gauge_index: pd.Index,
) -> None:
    """Log how many discharge gauges are missing from the gauge geometry."""
    csv_files = list(discharge_dir.rglob("*.csv"))
    discharge_ids = {f.stem for f in csv_files}
    gauge_ids = set(gauge_index.astype(str))

    missing = discharge_ids - gauge_ids
    if missing:
        log.warning(
            "%d discharge gauges missing from geometry: %s",
            len(missing),
            sorted(missing)[:10],
        )
    else:
        log.info("All %d discharge gauges present in geometry", len(discharge_ids))


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    """Assemble the CAMELS-RU Zenodo dataset."""
    # --- directory tree ---
    dirs = build_zenodo_tree(ZENODO_ROOT)

    # --- geometry: merge ROI watersheds ---
    geometry_temp = GEOMETRY_SRC / "temp"
    catalog_csv = DATA_ROOT / "hydropost_catalog.csv"

    if geometry_temp.exists() and catalog_csv.exists():
        watersheds = merge_roi_watersheds(ROI_IDS, geometry_temp, catalog_csv)
        ws_out = dirs["geometry"] / "camels_ru_watersheds.gpkg"
        watersheds.to_file(ws_out, driver="GPKG")
        log.info("Watersheds written to %s (%d catchments)", ws_out, len(watersheds))
    else:
        log.warning("Skipping ROI watershed merge — missing temp dir or catalogue CSV")
        watersheds = None

    # --- geometry: gauges ---
    raw_gauges = GEOMETRY_SRC / "GaugesFull.gpkg"
    legacy_gauges = GEOMETRY_SRC / "2803_gauge.gpkg"

    if raw_gauges.exists():
        gauges = prepare_gauge_metadata(raw_gauges, legacy_gauges)
        gauges_out = dirs["geometry"] / "camels_ru_gauges.gpkg"
        gauges.to_file(gauges_out, driver="GPKG")
        log.info("Gauges written to %s (%d stations)", gauges_out, len(gauges))
    else:
        log.warning("Raw gauge file not found: %s", raw_gauges)
        gauges = None

    # --- propagate area diffs from watersheds to gauges ---
    if watersheds is not None and gauges is not None:
        common = gauges.index.intersection(watersheds.index)
        gauges.loc[common, "area_diff_perc"] = watersheds.loc[common, "area_diff_perc"].astype(float)
        gauges.loc[common, "area_roshydromet"] = watersheds.loc[common, "area_roshydromet"].astype(float)
        gauges.to_file(dirs["geometry"] / "camels_ru_gauges.gpkg", driver="GPKG")
        log.info("Area metrics propagated to gauges for %d stations", len(common))

    # --- attributes ---
    attr_csv = ATTRIBUTES_SRC / "hydro_atlas_cis_camels.csv"
    copy_attributes(attr_csv, dirs["attributes"])

    # --- discharge ---
    copy_discharge(DISCHARGE_SRC, dirs["hydrology"])

    # --- meteo ---
    copy_meteo(METEO_SRC, dirs["meteo"])

    # --- validate coverage ---
    if gauges is not None and DISCHARGE_SRC.exists():
        validate_discharge_coverage(DISCHARGE_SRC, gauges.index)

    log.info("Zenodo dataset assembly complete at %s", ZENODO_ROOT.resolve())


if __name__ == "__main__":
    main()
