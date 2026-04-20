"""Package CAMELS-RU dataset for Zenodo release.

Creates the release directory structure described in Table 4 of the ESSD paper:
  - camels_ru_boundaries.gpkg    Watershed boundaries (GeoPackage)
  - camels_ru_discharge.nc       Daily discharge time series (NetCDF-4)
  - camels_ru_forcing.nc         Meteorological forcing (NetCDF-4)
  - camels_ru_attributes.csv     HydroATLAS physiographic attributes
  - camels_ru_signatures.csv     Hydrological signatures
  - camels_ru_water_level/       Daily water level CSVs

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
MSWEP_DIR = DATA_DIR / "parsed_meteo" / "mswep"
GLEAM_DIR = DATA_DIR / "parsed_meteo" / "gleam"
ATTRS_FILE = DATA_DIR / "attributes" / "hydro_atlas_cis_camels.csv"

PERIOD_START = "2008-01-01"
PERIOD_END = "2023-12-31"


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
                ["gauge", "time"],
                q_mm,
                {
                    "long_name": "Daily mean discharge as runoff depth",
                    "standard_name": "runoff_flux",
                    "units": "mm d-1",
                    "source": "AIS GMVO / Roshydromet",
                },
            ),
            "discharge_m3s": (
                ["gauge", "time"],
                q_m3s,
                {
                    "long_name": "Daily mean discharge volume",
                    "standard_name": "water_volume_transport_in_river_channel",
                    "units": "m3 s-1",
                    "source": "AIS GMVO / Roshydromet",
                },
            ),
            "quality_flag": (
                ["gauge", "time"],
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
            "gauge": ws_ids,
            "time": dates,
        },
        attrs={
            "title": "CAMELS-RU daily discharge",
            "Conventions": "CF-1.8",
            "source": "AIS GMVO / Roshydromet",
            "period": f"{PERIOD_START} to {PERIOD_END}",
            "quality_flag_values": "0=observed, 3=missing",
        },
    )
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

    # Variables: MSWEP precip, ERA5-Land temp (mean, min, max), PET
    precip = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_mean = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_min = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    t_max = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)
    pet = np.full((n_gauges, n_dates), np.nan, dtype=np.float32)

    for i, gid in enumerate(ws_ids):
        # MSWEP precipitation
        mswep_file = MSWEP_DIR / f"{gid}.csv"
        if mswep_file.exists():
            df = pd.read_csv(mswep_file, index_col="date", parse_dates=True)
            if "precipitation" in df.columns:
                sub = df["precipitation"].reindex(dates)
                valid = sub.notna()
                precip[i, valid.values] = sub[valid].values.astype(np.float32)

        # ERA5-Land temperature — prefer filled CSV if the gauge had gaps.
        era5_file = ERA5_FILLED_DIR / f"{gid}.csv"
        if not era5_file.exists():
            era5_file = ERA5_DIR / f"{gid}.csv"
        if era5_file.exists():
            df = pd.read_csv(era5_file, index_col="date", parse_dates=True)
            for var, arr in [("t_mean", t_mean), ("t_min", t_min), ("t_max", t_max)]:
                if var in df.columns:
                    sub = df[var].reindex(dates)
                    valid = sub.notna()
                    arr[i, valid.values] = sub[valid].values.astype(np.float32)

        # GLEAM4 potential evaporation
        gleam_file = GLEAM_DIR / f"{gid}.csv"
        if gleam_file.exists():
            df = pd.read_csv(
                gleam_file,
                index_col="date",
                parse_dates=True,
                usecols=["date", "potential_evaporation"],
            )
            sub = df["potential_evaporation"].reindex(dates)
            valid = sub.notna()
            pet[i, valid.values] = sub[valid].values.astype(np.float32)

    ds = xr.Dataset(
        {
            "precip_mswep": (
                ["gauge", "time"],
                precip,
                {
                    "long_name": "Precipitation (MSWEP v2.8)",
                    "units": "mm d-1",
                    "source": "MSWEP v2.8 (Beck et al., 2019)",
                },
            ),
            "temp_mean": (
                ["gauge", "time"],
                t_mean,
                {
                    "long_name": "Mean daily air temperature at 2m",
                    "units": "degC",
                    "source": "ERA5-Land (Munoz-Sabater et al., 2021)",
                },
            ),
            "temp_min": (
                ["gauge", "time"],
                t_min,
                {
                    "long_name": "Minimum daily air temperature at 2m",
                    "units": "degC",
                    "source": "ERA5-Land (Munoz-Sabater et al., 2021)",
                },
            ),
            "temp_max": (
                ["gauge", "time"],
                t_max,
                {
                    "long_name": "Maximum daily air temperature at 2m",
                    "units": "degC",
                    "source": "ERA5-Land (Munoz-Sabater et al., 2021)",
                },
            ),
            "pet": (
                ["gauge", "time"],
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
        coords={"gauge": ws_ids, "time": dates},
        attrs={
            "title": "CAMELS-RU meteorological forcing",
            "Conventions": "CF-1.8",
            "precip_source": "MSWEP v2.8 (Beck et al., 2019)",
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
        },
    )
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


def package_water_level() -> None:
    """Copy water level CSVs to release directory."""
    print("Packaging water level...")
    out_dir = OUTPUT_DIR / "camels_ru_water_level"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Get gauge IDs that have watersheds
    ws = gpd.read_file(GEOM_DIR / "camels_watersheds.gpkg")
    ws_ids = set(ws.gauge_id.astype(str))

    count = 0
    for src_dir in [LEVEL_DIR, LEVEL_GTS_DIR]:
        if not src_dir.exists():
            continue
        for f in sorted(src_dir.glob("*.csv")):
            if f.stem in ws_ids:
                shutil.copy2(f, out_dir / f.name)
                count += 1

    print(f"  {count} gauge files -> {out_dir.name}/")


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
