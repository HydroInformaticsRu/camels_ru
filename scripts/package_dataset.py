"""Package CAMELS-RU dataset for Zenodo release.

Creates the release directory structure described in Table 4 of the CAMELS-RU manuscript:
  - camels_ru_boundaries.gpkg    Watershed boundaries (GeoPackage)
  - camels_ru_discharge.nc       Daily discharge time series (NetCDF-4)
  - camels_ru_forcing.nc         Meteorological forcing (NetCDF-4)
  - camels_ru_attributes.csv     HydroATLAS physiographic attributes
  - camels_ru_signatures.csv     Hydrological signatures
  - camels_ru_water_level.nc     Daily water level time series (NetCDF-4)

Usage:
    pixi run python scripts/package_dataset.py
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "CAMELS_RU"
OUTPUT_DIR = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0"

# Source directories
GEOM_DIR = DATA_DIR / "geometry"
DISCHARGE_DIR = DATA_DIR / "HydroData" / "Discharge"
COMPOUND_DIR = DATA_DIR / "HydroData" / "Compound"
LEVEL_DIR = DATA_DIR / "HydroData" / "Level"
LEVEL_GTS_DIR = DATA_DIR / "HydroData" / "LevelGTS"
# ERA5-Land aggregation lives on the Russia-wide meteo tree, not the CAMELS-RU one,
# because it is produced by a pipeline that serves multiple projects.
ERA5_DIR = PROJECT_ROOT / "data" / "Russia" / "MeteoData" / "CamelsRU" / "era5_land"
ERA5_FILLED_DIR = PROJECT_ROOT / "data" / "Russia" / "MeteoData" / "CamelsRU" / "era5_land_filled"
# Corrected, de-accumulated ERA5-Land total precipitation (col "prcp"); the
# authoritative source used to recompute the Sect. 5 forcing numbers. Shipped
# as the precip_era5 intercomparison variable (MSWEP remains primary).
ERA5_TP_DIR = PROJECT_ROOT / "data" / "Russia" / "MeteoData" / "CamelsRU" / "era5land_tp_new"
MSWEP_DIR = DATA_DIR / "parsed_meteo" / "mswep"
GLEAM_DIR = DATA_DIR / "parsed_meteo" / "gleam"
GPCP_DIR = DATA_DIR / "parsed_meteo" / "gpcp"  # GPCP v3.3 (col "precip"); intercomparison variable
ATTRS_FILE = DATA_DIR / "attributes" / "hydro_atlas_cis_camels.csv"

PERIOD_START = "2008-01-01"
PERIOD_END = "2023-12-31"

# ACDD/CF discovery metadata shared by every released NetCDF (conformance audit
# items C4/C5/C6, docs/camels_conformance_audit.md). Values verified against the
# manuscript author block; the Zenodo DOI is deliberately omitted until assigned
# (no fabricated citations).
INSTITUTION = (
    "International Center for Corporate Data Analysis, Astana, Kazakhstan; "
    "Water Problems Institute, Russian Academy of Sciences, Moscow, Russia"
)
LICENSE = "CC BY 4.0"
REFERENCES = (
    "Abramov et al.: CAMELS-RU dataset description (Hydrology and Earth System "
    "Sciences, in review); processing code: "
    "https://github.com/HydroInformaticsRu/camels_ru"
)
# CF discrete-sampling-geometry attributes for the per-gauge time-series id.
_GAUGE_ID_ATTRS = {"long_name": "Gauge identifier", "cf_role": "timeseries_id"}
_ACDD_ATTRS = {
    "institution": INSTITUTION,
    "references": REFERENCES,
    "license": LICENSE,
    "featureType": "timeSeries",
}


def package_boundaries() -> None:
    """Copy watershed boundaries GeoPackage."""
    print("Packaging boundaries...")
    src = GEOM_DIR / "camels_watersheds.gpkg"
    dst = OUTPUT_DIR / "camels_ru_boundaries.gpkg"

    ws = gpd.read_file(src)
    # Keep essential columns only
    keep_cols = ["gauge_id", "name", "area_km2", "area_roshydromet", "area_diff_perc", "geometry"]
    ws = ws[[c for c in keep_cols if c in ws.columns]]
    ws.to_file(dst, driver="GPKG")
    print(f"  {len(ws)} catchments -> {dst.name}")


def package_discharge() -> None:
    """Build discharge NetCDF from per-gauge CSVs."""
    print("Packaging discharge...")

    # Get gauge list from geometry
    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws_ids = sorted(ws.gauge_id.astype(str).unique())

    dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
    n_dates = len(dates)
    n_gauges = len(ws_ids)

    # Initialize arrays
    q_mm = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    q_m3s = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    q_flag = np.full((n_gauges, n_dates), 3, dtype=np.int8)  # 3 = missing

    for i, gid in enumerate(ws_ids):
        # Try Compound first (has q_mm_day), then raw Discharge
        compound_file = COMPOUND_DIR / f"{gid}.csv"
        discharge_file = DISCHARGE_DIR / f"{gid}.csv"

        if compound_file.exists():
            df = pd.read_csv(compound_file, index_col="date", parse_dates=True)
            if "q_mm_day" in df.columns:
                sub = df["q_mm_day"].reindex(dates)
                valid = sub.notna()
                q_mm[i, valid.values] = sub[valid].values.astype(np.float32)
                q_flag[i, valid.values] = 0  # observed
            if "q_cms" in df.columns:
                sub = df["q_cms"].reindex(dates)
                valid = sub.notna()
                q_m3s[i, valid.values] = sub[valid].values.astype(np.float32)
        elif discharge_file.exists():
            df = pd.read_csv(discharge_file, index_col="date", parse_dates=True)
            col = [c for c in df.columns if "q" in c.lower() or "discharge" in c.lower()]
            if col:
                sub = df[col[0]].reindex(dates)
                valid = sub.notna()
                q_m3s[i, valid.values] = sub[valid].values.astype(np.float32)
                q_flag[i, valid.values] = 0

    ds = xr.Dataset(
        {
            "discharge_mm": (
                ["gauge_id", "time"],
                q_mm,
                {
                    "long_name": "Daily mean discharge as runoff depth",
                    # No CF standard_name: 'runoff_flux' is canonically kg m-2 s-1,
                    # not UDUNITS-convertible to the depth-rate mm d-1 (audit C2).
                    "units": "mm d-1",
                    "source": "AIS GMVO / Roshydromet",
                },
            ),
            "discharge_m3s": (
                ["gauge_id", "time"],
                q_m3s,
                {
                    "long_name": "Daily mean discharge volume",
                    "standard_name": "water_volume_transport_in_river_channel",
                    "units": "m3 s-1",
                    "source": "AIS GMVO / Roshydromet",
                },
            ),
            "quality_flag": (
                ["gauge_id", "time"],
                q_flag,
                {
                    "long_name": "Data quality flag",
                    "flag_values": np.array([0, 3], dtype=np.int8),
                    "flag_meanings": "observed missing",
                    "description": (
                        "0 = observed (gauge-reported; gap-fills ≤6 days via "
                        "second-order polynomial interpolation are written in "
                        "place and share this flag). 3 = missing."
                    ),
                },
            ),
        },
        coords={
            "gauge_id": ws_ids,
            "time": dates,
        },
        attrs={
            "title": "CAMELS-RU daily discharge",
            "Conventions": "CF-1.8",
            "source": "AIS GMVO / Roshydromet",
            "period": f"{PERIOD_START} to {PERIOD_END}",
            "quality_flag_values": "0=observed, 3=missing",
            **_ACDD_ATTRS,
        },
    )
    ds["gauge_id"].attrs = dict(_GAUGE_ID_ATTRS)
    out = OUTPUT_DIR / "camels_ru_discharge.nc"
    ds.to_netcdf(
        out,
        encoding={
            "discharge_mm": {"dtype": "float32", "zlib": True, "complevel": 4},
            "discharge_m3s": {"dtype": "float32", "zlib": True, "complevel": 4},
            "quality_flag": {"dtype": "int8", "zlib": True, "complevel": 4},
        },
    )
    n_with_data = int((q_flag != 3).any(axis=1).sum())
    print(f"  {n_with_data}/{n_gauges} gauges with data -> {out.name}")


def _load_forcing_notes() -> dict[str, str]:
    """Load the per-gauge fill notes produced by scripts/fill_meteo_gaps.py."""
    notes_file = ERA5_FILLED_DIR / "forcing_notes.json"
    if not notes_file.exists():
        return {}
    with notes_file.open() as fh:
        return json.load(fh)


def _read_gauge_series(path: Path, col: str, dates: pd.DatetimeIndex) -> np.ndarray | None:
    """Read one daily column from a per-gauge forcing CSV, reindexed to ``dates``.

    Returns a float32 array aligned to ``dates`` (NaN where the source has no
    value for a date) or ``None`` when the file or column is absent.
    """
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col="date", parse_dates=True)
    if col not in df.columns:
        return None
    return df[col].reindex(dates).to_numpy(dtype=np.float32)


def package_forcing() -> dict[str, str]:
    """Build meteorological forcing NetCDF.

    For each gauge's ERA5 temperature we read ``era5_land_filled/<gid>.csv``
    when it exists (the 24 gauges whose 2023 or 2008-2022 ERA5-Land coverage
    had gaps — see ``scripts/fill_meteo_gaps.py``) and fall back to the
    as-aggregated CSV at ``era5_land/`` otherwise. Returns the fill-notes
    dict so downstream packaging (``gauge_summary.csv``) can attach
    per-gauge provenance strings.
    """
    print("Packaging forcing...")

    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws_ids = sorted(ws.gauge_id.astype(str).unique())
    dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
    n_dates = len(dates)
    n_gauges = len(ws_ids)

    forcing_notes = _load_forcing_notes()
    n_filled_gauges = sum(1 for gid in ws_ids if gid in forcing_notes)
    print(
        f"  reading forcing: {n_gauges} gauges, {n_filled_gauges} with gap-fill applied "
        f"(from {ERA5_FILLED_DIR.name}/)"
    )

    # Variables: MSWEP precip (primary) + ERA5-Land/GPCP precip (intercomparison),
    # ERA5-Land temp (mean, min, max), PET
    precip = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    precip_era5 = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    precip_gpcp = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_mean = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_min = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_max = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    pet = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)

    for i, gid in enumerate(ws_ids):
        # MSWEP precipitation (primary released forcing)
        s = _read_gauge_series(MSWEP_DIR / f"{gid}.csv", "precipitation", dates)
        if s is not None:
            precip[i] = s

        # ERA5-Land precipitation (corrected, de-accumulated) — intercomparison only
        s = _read_gauge_series(ERA5_TP_DIR / f"{gid}.csv", "prcp", dates)
        if s is not None:
            precip_era5[i] = s

        # GPCP v3.3 precipitation — intercomparison only
        s = _read_gauge_series(GPCP_DIR / f"{gid}.csv", "precip", dates)
        if s is not None:
            precip_gpcp[i] = s

        # ERA5-Land temperature — prefer filled CSV if the gauge had gaps.
        era5_file = ERA5_FILLED_DIR / f"{gid}.csv"
        if not era5_file.exists():
            era5_file = ERA5_DIR / f"{gid}.csv"
        for var, arr in (("t_mean", t_mean), ("t_min", t_min), ("t_max", t_max)):
            s = _read_gauge_series(era5_file, var, dates)
            if s is not None:
                arr[i] = s

        # GLEAM4 potential evaporation
        s = _read_gauge_series(GLEAM_DIR / f"{gid}.csv", "potential_evaporation", dates)
        if s is not None:
            pet[i] = s

    ds = xr.Dataset(
        {
            "precip_mswep": (
                ["gauge_id", "time"],
                precip,
                {
                    "long_name": "Precipitation (MSWEP v2.8)",
                    "units": "mm d-1",
                    "source": "MSWEP v2.8 (Beck et al., 2019)",
                    "note": "Recommended primary precipitation forcing.",
                },
            ),
            "precip_era5": (
                ["gauge_id", "time"],
                precip_era5,
                {
                    "long_name": "Precipitation (ERA5-Land, de-accumulated)",
                    "units": "mm d-1",
                    "source": "ERA5-Land (Munoz-Sabater et al., 2021)",
                    "note": (
                        "Corrected de-accumulated ERA5-Land total precipitation, "
                        "provided for forcing intercomparison (manuscript Sect. 5). "
                        "Not the recommended forcing; use precip_mswep for modelling."
                    ),
                },
            ),
            "precip_gpcp": (
                ["gauge_id", "time"],
                precip_gpcp,
                {
                    "long_name": "Precipitation (GPCP v3.3)",
                    "units": "mm d-1",
                    "source": "GPCP v3.3 (NASA MEaSUREs, doi:10.5067/MEASURES/GPCP/DATA307)",
                    "note": (
                        "Provided for forcing intercomparison (manuscript Sect. 5). "
                        "0.5-degree product; coverage is sparser than MSWEP/ERA5-Land. "
                        "Not the recommended forcing; use precip_mswep for modelling."
                    ),
                },
            ),
            "temp_mean": (
                ["gauge_id", "time"],
                t_mean,
                {
                    "long_name": "Mean daily air temperature at 2m",
                    "standard_name": "air_temperature",
                    "cell_methods": "time: mean",
                    "units": "degC",
                    "source": "ERA5-Land (Munoz-Sabater et al., 2021)",
                },
            ),
            "temp_min": (
                ["gauge_id", "time"],
                t_min,
                {
                    "long_name": "Minimum daily air temperature at 2m",
                    "standard_name": "air_temperature",
                    "cell_methods": "time: minimum",
                    "units": "degC",
                    "source": "ERA5-Land (Munoz-Sabater et al., 2021)",
                },
            ),
            "temp_max": (
                ["gauge_id", "time"],
                t_max,
                {
                    "long_name": "Maximum daily air temperature at 2m",
                    "standard_name": "air_temperature",
                    "cell_methods": "time: maximum",
                    "units": "degC",
                    "source": "ERA5-Land (Munoz-Sabater et al., 2021)",
                },
            ),
            "pet": (
                ["gauge_id", "time"],
                pet,
                {
                    "long_name": "Potential evaporation (GLEAM4)",
                    "units": "mm d-1",
                    "source": "GLEAM4 (Miralles et al., 2025, Sci. Data 12, 416)",
                    "method": (
                        "Modified Priestley-Taylor scaled by a multiplicative "
                        "evaporative-stress factor (GLEAM4)"
                    ),
                },
            ),
        },
        coords={"gauge_id": ws_ids, "time": dates},
        attrs={
            "title": "CAMELS-RU meteorological forcing",
            "Conventions": "CF-1.8",
            "precip_source": "MSWEP v2.8 (Beck et al., 2019)",
            "alt_precip_sources": (
                "precip_era5 = ERA5-Land de-accumulated total precipitation (corrected); "
                "precip_gpcp = GPCP v3.3. Both are provided for the forcing "
                "intercomparison of manuscript Sect. 5; precip_mswep (MSWEP v2.8) "
                "is the recommended primary forcing."
            ),
            "temp_source": "ERA5-Land (Munoz-Sabater et al., 2021)",
            "pet_source": "GLEAM4 (Miralles et al., 2025)",
            "pet_method": "Modified Priestley-Taylor with evaporative-stress factor (GLEAM4)",
            "period": f"{PERIOD_START} to {PERIOD_END}",
            "precip_units": "mm d-1",
            "temp_units": "degC",
            "pet_units": "mm d-1",
            "gap_fill_method": (
                "ERA5-Land temperature gaps filled for 24 gauges: DOY climatology "
                "from 2008–2022 for 17 gauges whose 2023 tile was partial; nearest "
                "valid land-cell near 170°E from the 2008–2022 raw tiles for 7 gauges "
                "east of the locally-downloaded ERA5-Land tile domain. MSWEP "
                "precipitation and GLEAM4 PET require no fill (0 % NaN). See "
                "camels_ru_gauge_summary.csv forcing_note column for per-gauge "
                "provenance."
            ),
            "gap_fill_n_gauges_affected": len(forcing_notes),
            **_ACDD_ATTRS,
        },
    )
    ds["gauge_id"].attrs = dict(_GAUGE_ID_ATTRS)
    out = OUTPUT_DIR / "camels_ru_forcing.nc"
    encoding = {v: {"dtype": "float32", "zlib": True, "complevel": 4} for v in ds.data_vars}
    ds.to_netcdf(out, encoding=encoding)
    print(f"  {n_gauges} gauges -> {out.name}")
    return forcing_notes


def package_attributes() -> None:
    """Copy HydroATLAS attributes CSV."""
    print("Packaging attributes...")
    if not ATTRS_FILE.exists():
        print(f"  WARNING: {ATTRS_FILE} not found, skipping")
        return
    df = pd.read_csv(ATTRS_FILE)
    out = OUTPUT_DIR / "camels_ru_attributes.csv"
    df.to_csv(out, index=False)
    print(f"  {len(df)} catchments, {len(df.columns)} columns -> {out.name}")


SIGNATURES_STATS_DIR = DATA_DIR / "statistics"
README_SOURCE = PROJECT_ROOT / "release" / "CAMELS_RU_v1.0" / "README.md"


def package_readme() -> None:
    """Copy the canonical Zenodo README into OUTPUT_DIR.

    The source-of-truth lives at ``release/CAMELS_RU_v1.0/README.md`` and is
    hand-maintained (file descriptions, gauge counts, quality-grading summary).
    When OUTPUT_DIR is that same directory we skip the copy (no-op on a
    production build); rebuilds to alternate dirs (e.g. ``.tmp/zenodo_rebuild/``)
    get the README so the bundle is self-contained.
    """
    print("Packaging README...")
    dst = OUTPUT_DIR / "README.md"
    if README_SOURCE.resolve() == dst.resolve():
        print(f"  source == destination ({dst}); skipping copy")
        return
    if not README_SOURCE.exists():
        raise FileNotFoundError(f"README source missing: {README_SOURCE}")
    shutil.copy2(README_SOURCE, dst)
    print(f"  {README_SOURCE.name} -> {dst}")


def package_signatures() -> None:
    """Copy the 15-signature CSVs produced by scripts/create_paper_signatures.py.

    create_paper_signatures.py writes to ``data/CAMELS_RU/statistics/`` by
    default; ``main()`` orchestrates a fresh run before this step, so both files
    are expected to exist when we get here.
    """
    print("Packaging signatures...")
    per_gauge = SIGNATURES_STATS_DIR / "camels_ru_signatures.csv"
    summary = SIGNATURES_STATS_DIR / "camels_ru_signatures_summary.csv"
    missing = [p for p in (per_gauge, summary) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing signature CSVs: {[str(p) for p in missing]}. "
            "Run scripts/create_paper_signatures.py first (orchestrated by main())."
        )
    shutil.copy2(per_gauge, OUTPUT_DIR / per_gauge.name)
    shutil.copy2(summary, OUTPUT_DIR / summary.name)
    print(f"  {per_gauge.name} + {summary.name} -> release/")


def _write_forcing_notes_csv(forcing_notes: dict[str, str]) -> None:
    """Ship the full per-gauge fill-provenance table in the release directory.

    The discharge-gauge-only ``camels_ru_gauge_summary.csv`` captures
    ``forcing_note`` for filled gauges that are also tracked there, but 17 of
    the 24 filled gauges are water-level-only and have no summary row. The
    standalone ``camels_ru_forcing_notes.csv`` file documents all 24 so that
    every fill is discoverable without cross-referencing a JSON artefact.
    """
    out = OUTPUT_DIR / "camels_ru_forcing_notes.csv"
    if not forcing_notes:
        # Still emit the header so downstream tooling has a stable schema.
        pd.DataFrame(columns=["gauge_id", "forcing_note"]).to_csv(out, index=False)
        print(f"  forcing_notes: no gap-fills applied; empty {out.name} written")
        return
    df = pd.DataFrame(
        sorted(forcing_notes.items()),
        columns=["gauge_id", "forcing_note"],
    )
    df.to_csv(out, index=False)
    print(f"  forcing_notes: {len(df)} filled gauges -> {out.name}")


def _update_gauge_summary_with_forcing_notes(forcing_notes: dict[str, str]) -> None:
    """Attach the per-gauge ``forcing_note`` column to ``camels_ru_gauge_summary.csv``.

    The summary file lists only the discharge-gauge subset, so problem gauges
    absent from it are documented separately via ``camels_ru_forcing_notes.csv``
    (see :func:`_write_forcing_notes_csv`). We emit a one-line reminder listing
    the absent gauge IDs so a future diff shows which artefact contains which
    provenance.
    """
    summary = OUTPUT_DIR / "camels_ru_gauge_summary.csv"
    if not summary.exists():
        print(f"  WARNING: {summary} missing, cannot attach forcing_note")
        return
    df = pd.read_csv(summary, dtype={"gauge_id": str})
    df["forcing_note"] = df["gauge_id"].map(forcing_notes).fillna("")
    df.to_csv(summary, index=False)
    n_annotated = int((df["forcing_note"] != "").sum())
    missing = [g for g in forcing_notes if g not in set(df["gauge_id"])]
    print(f"  gauge_summary: {n_annotated} rows annotated with forcing_note")
    if missing:
        print(
            f"  note: {len(missing)} filled gauges absent from gauge_summary "
            f"(water-level only); see camels_ru_forcing_notes.csv for provenance "
            f"({sorted(missing)})"
        )


_LEVEL_HEIGHTS_FILE = DATA_DIR / "AisLevelCsv" / "gauge_heights.csv"
_LEVEL_GTS_HEIGHTS_FILE = DATA_DIR / "AisLevelGTSCsv" / "GTS_heights.csv"


def _load_gauge_zero_heights() -> dict[str, float]:
    """Load per-gauge zero-post elevations (m above BHS-77) from both source tables.

    Returns a single merged ``{gauge_id: height_m}`` mapping covering both the
    river network (``AisLevelCsv/gauge_heights.csv``) and the reservoir /
    hydropower network (``AisLevelGTSCsv/GTS_heights.csv``). Gauges missing
    from both tables are absent from the dict and receive NaN downstream.
    """
    heights: dict[str, float] = {}
    for path in (_LEVEL_HEIGHTS_FILE, _LEVEL_GTS_HEIGHTS_FILE):
        if not path.exists():
            continue
        df = pd.read_csv(path)
        # Unnamed index column in gauge_heights.csv vs. named gauge_id in GTS_heights.csv
        id_col = "gauge_id" if "gauge_id" in df.columns else df.columns[0]
        for gid, h in zip(df[id_col].astype(str), df["height"], strict=False):
            if pd.notna(h):
                heights[gid] = float(h)
    return heights


def package_water_level() -> None:
    """Build water-level NetCDF from per-gauge CSVs.

    Produces a single ``gauge × time`` NetCDF mirroring the discharge layout:

    - ``water_level_cm``: stage above gauge zero-post (native AIS GMVO ``lvl_sm``)
    - ``water_level_mbs``: absolute elevation in meters above BHS-77, computed as
      ``water_level_cm / 100 + gauge_zero_m``; NaN for gauges without a
      known zero-post elevation
    - ``gauge_zero_m`` (per-gauge 1D): zero-post elevation in m above BHS-77
    - ``gauge_type`` (per-gauge 1D): 0 = river, 1 = reservoir / hydropower

    No A–F quality grading is applied to water-level data; users should assess
    per-gauge completeness before use.
    """
    print("Packaging water level...")

    # Remove legacy CSV-per-gauge folder from prior releases to keep the
    # bundle single-source-of-truth and avoid stale files in SHA256SUMS.
    legacy_dir = OUTPUT_DIR / "camels_ru_water_level"
    if legacy_dir.exists() and legacy_dir.is_dir():
        shutil.rmtree(legacy_dir)
        print(f"  removed legacy folder: {legacy_dir.name}/")

    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws_ids = sorted(ws.gauge_id.astype(str).unique())
    dates = pd.date_range(PERIOD_START, PERIOD_END, freq="D")
    n_dates = len(dates)
    n_gauges = len(ws_ids)

    heights = _load_gauge_zero_heights()

    lvl_cm = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    gauge_zero_m = np.full(n_gauges, np.nan, dtype=np.float32)
    gauge_type = np.full(n_gauges, -1, dtype=np.int8)  # -1 = no water-level record (documented class)

    n_river = 0
    n_reservoir = 0
    for i, gid in enumerate(ws_ids):
        river_file = LEVEL_DIR / f"{gid}.csv"
        gts_file = LEVEL_GTS_DIR / f"{gid}.csv"
        if river_file.exists():
            src = river_file
            gauge_type[i] = 0
            n_river += 1
        elif gts_file.exists():
            src = gts_file
            gauge_type[i] = 1
            n_reservoir += 1
        else:
            continue

        df = pd.read_csv(src, index_col="date", parse_dates=True)
        if "lvl_sm" in df.columns:
            sub = df["lvl_sm"].reindex(dates)
            valid = sub.notna()
            lvl_cm[i, valid.values] = sub[valid].values.astype(np.float32)

        if gid in heights:
            gauge_zero_m[i] = np.float32(heights[gid])

    # Absolute elevation (m above BHS-77) = stage (cm) / 100 + zero-post (m)
    lvl_mbs = (lvl_cm / 100.0) + gauge_zero_m[:, np.newaxis]

    ds = xr.Dataset(
        {
            "water_level_cm": (
                ["gauge_id", "time"],
                lvl_cm,
                {
                    "long_name": "Daily water level (stage above gauge zero-post)",
                    "units": "cm",
                    "source": "AIS GMVO / Roshydromet",
                    "comment": (
                        "Relative stage reading in centimetres, measured from the "
                        "gauge zero-post as reported by AIS GMVO. For absolute "
                        "elevation above BHS-77 use water_level_mbs."
                    ),
                },
            ),
            "water_level_mbs": (
                ["gauge_id", "time"],
                lvl_mbs.astype(np.float32),
                {
                    "long_name": "Daily water level (absolute elevation, BHS-77)",
                    "units": "m",
                    "source": "AIS GMVO / Roshydromet + gauge_heights",
                    "comment": (
                        "Absolute water-surface elevation in metres above the "
                        "Baltic Height System 1977 (BHS-77), computed as "
                        "water_level_cm / 100 + gauge_zero_m. NaN where the "
                        "zero-post elevation is unknown."
                    ),
                },
            ),
            "gauge_zero_m": (
                ["gauge_id"],
                gauge_zero_m,
                {
                    "long_name": "Elevation of the gauge zero-post (BHS-77)",
                    "units": "m",
                    "source": "AIS GMVO gauge_heights.csv + GTS_heights.csv",
                },
            ),
            "gauge_type": (
                ["gauge_id"],
                gauge_type,
                {
                    "long_name": "Gauge classification",
                    "flag_values": np.array([-1, 0, 1], dtype=np.int8),
                    "flag_meanings": ("no_water_level_record river reservoir_or_hydropower"),
                    "comment": (
                        "-1 marks gauges with no water-level series (discharge-only "
                        "gauges on the shared 3353-gauge axis); their water_level_* "
                        "values are NaN. It is a documented class, not a missing-data "
                        "sentinel (audit C1)."
                    ),
                },
            ),
        },
        coords={
            "gauge_id": ws_ids,
            "time": dates,
        },
        attrs={
            "title": "CAMELS-RU daily water level",
            "Conventions": "CF-1.8",
            "source": "AIS GMVO / Roshydromet",
            "period": f"{PERIOD_START} to {PERIOD_END}",
            "datum": "Baltic Height System 1977 (BHS-77)",
            "grading": (
                "No A-F quality grade is assigned to water-level data; "
                "users should assess per-gauge completeness before use."
            ),
            "gap_fill_method": (
                "Second-order polynomial interpolation: gaps ≤6 days "
                "(river gauges) or ≤15 days (reservoir/hydropower gauges). "
                "Longer gaps retained as NaN."
            ),
            **_ACDD_ATTRS,
        },
    )
    ds["gauge_id"].attrs = dict(_GAUGE_ID_ATTRS)
    out = OUTPUT_DIR / "camels_ru_water_level.nc"
    ds.to_netcdf(
        out,
        encoding={
            "water_level_cm": {"dtype": "float32", "zlib": True, "complevel": 4},
            "water_level_mbs": {"dtype": "float32", "zlib": True, "complevel": 4},
            "gauge_zero_m": {"dtype": "float32", "zlib": True, "complevel": 4},
            "gauge_type": {"dtype": "int8", "zlib": True, "complevel": 4},
        },
    )
    n_with_mbs = int(np.isfinite(gauge_zero_m).sum())
    n_with_data = n_river + n_reservoir
    print(
        f"  {n_with_data}/{n_gauges} gauges with data "
        f"({n_river} river, {n_reservoir} reservoir/hydropower); "
        f"{n_with_mbs} with zero-post elevation -> {out.name}"
    )


def _run(cmd: list[str], label: str) -> None:
    """Run a pipeline step as a subprocess, streaming output."""
    import subprocess

    print(f"\n[{label}] {' '.join(cmd)}")
    # Command list is constructed internally from hardcoded binary + pipeline flags, not user input.
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)  # noqa: S603


def run_year_grades() -> None:
    """Regenerate year_grades.csv + gauge_summary.csv from Compound/by_grade/."""
    _run(
        [
            "pixi",
            "run",
            "python",
            "scripts/create_year_grades.py",
            "--output-dir",
            str(OUTPUT_DIR),
        ],
        "year_grades",
    )


def run_signatures() -> None:
    """Regenerate the 15-signature CSVs into data/CAMELS_RU/statistics/."""
    SIGNATURES_STATS_DIR.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "pixi",
            "run",
            "python",
            "scripts/create_paper_signatures.py",
            "--discharge-nc",
            str(OUTPUT_DIR / "camels_ru_discharge.nc"),
            "--boundaries",
            str(OUTPUT_DIR / "camels_ru_boundaries.gpkg"),
            "--output-dir",
            str(SIGNATURES_STATS_DIR),
        ],
        "signatures",
    )


def write_checksums() -> None:
    """Write SHA256SUMS for every file in OUTPUT_DIR (relative paths, one per line)."""
    import hashlib

    print("Writing SHA256SUMS...")
    checksum_path = OUTPUT_DIR / "SHA256SUMS"
    # Collect files, sorted, skipping the checksums file itself if already present
    files = sorted(p for p in OUTPUT_DIR.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    lines: list[str] = []
    for f in files:
        h = hashlib.sha256()
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        rel = f.relative_to(OUTPUT_DIR).as_posix()
        lines.append(f"{h.hexdigest()}  {rel}")
    checksum_path.write_text("\n".join(lines) + "\n")
    print(f"  {len(lines)} files -> {checksum_path.name}")


def main() -> None:
    """Parse CLI args and orchestrate the full Zenodo-bundle build pipeline."""
    global OUTPUT_DIR  # noqa: PLW0603 — single override at startup so nested helpers see the new dir
    import argparse

    default_out = OUTPUT_DIR
    parser = argparse.ArgumentParser(
        description="Build the CAMELS-RU Zenodo release bundle.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_out,
        help=f"Release directory (default: {default_out})",
    )
    parser.add_argument(
        "--skip-year-grades",
        action="store_true",
        help="Skip regenerating year_grades.csv / gauge_summary.csv",
    )
    parser.add_argument(
        "--skip-signatures",
        action="store_true",
        help="Skip regenerating signature CSVs (reuses data/CAMELS_RU/statistics/)",
    )
    parser.add_argument(
        "--skip-checksums",
        action="store_true",
        help="Skip writing SHA256SUMS at end",
    )
    args = parser.parse_args()

    OUTPUT_DIR = args.output_dir
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Packaging CAMELS-RU dataset to {OUTPUT_DIR}\n")

    # Stage 1: static artefacts + time-series NetCDFs (both needed before grading/signatures)
    package_readme()
    package_boundaries()
    package_attributes()
    package_water_level()
    package_discharge()
    forcing_notes = package_forcing()

    # Stage 2: quality grading (reads Compound/by_grade/, writes year_grades + gauge_summary)
    if not args.skip_year_grades:
        run_year_grades()

    # Stage 3: forcing-note column on gauge_summary + standalone forcing_notes CSV
    _update_gauge_summary_with_forcing_notes(forcing_notes)
    _write_forcing_notes_csv(forcing_notes)

    # Stage 4: signatures (reads the just-built discharge.nc + boundaries + meteo inputs)
    if not args.skip_signatures:
        run_signatures()
    package_signatures()

    # Stage 5: integrity manifest
    if not args.skip_checksums:
        write_checksums()

    print(f"\nDone. Release package at: {OUTPUT_DIR}")
    total = 0
    for f in OUTPUT_DIR.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    print(f"Total size: {total / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
