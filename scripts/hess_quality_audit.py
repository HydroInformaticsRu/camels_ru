#!/usr/bin/env python3
"""Build reproducible HESS quality-audit artefacts for CAMELS-RU.

This script is intentionally release-facing: it starts from the staged release
bundle plus explicitly required local source folders, then writes reviewer-facing
CSV/JSON diagnostics under results/hess_quality/.

It does not upload to Zenodo, mint a DOI, edit release artefacts, or rewrite the
manuscript.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm.auto import tqdm
import xarray as xr

from utils.release_io import open_release_dataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.paper_analysis_scope import (  # noqa: E402
    PAPER_ANALYSIS_EXCLUSION_LABEL,
    PAPER_ANALYSIS_EXCLUSION_NOTE,
    filter_paper_analysis_index,
    is_paper_analysis_excluded_gauge_id,
    paper_analysis_scope_summary,
)

RELEASE = ROOT / "release" / "CAMELS_RU_v1.0"
DATA = ROOT / "data"
OUT_DIR = ROOT / "results" / "hess_quality"

PRODUCTS: dict[str, tuple[str, str]] = {
    # Corrected de-accumulated ERA5-Land precip; the era5_land copy over-accumulated
    # tp (~1.5x), inflating basin P. era5land_tp_new is the re-downloaded fix (prcp only).
    "ERA5-Land": ("data/Russia/MeteoData/CamelsRU/era5land_tp_new", "prcp"),
    "MSWEP": ("data/CAMELS_RU/parsed_meteo/mswep", "precipitation"),
    "GPCP": ("data/CAMELS_RU/parsed_meteo/gpcp", "precip"),
}
GLEAM_DIR = "data/CAMELS_RU/parsed_meteo/gleam"
PET_COL = "potential_evaporation"
AET_COL = "actual_evaporation"
DAM_PROXY_COL = "dor_pc_pva"

REQUIRED_SOURCE_DIRS = [
    # Corrected de-accumulated ERA5-Land precip (era5land_tp_new); the era5_land copy
    # over-accumulated tp (~1.5x).
    "data/Russia/MeteoData/CamelsRU/era5land_tp_new",
    "data/CAMELS_RU/parsed_meteo/mswep",
    "data/CAMELS_RU/parsed_meteo/gpcp",
    "data/CAMELS_RU/parsed_meteo/gleam",
    "data/Rasters",
    "data/Russia",
    "data/World",
    "data/zenodo",
]

REQUIRED_RELEASE_FILES = [
    "README.md",
    "SHA256SUMS",
    "camels_ru_attributes.csv",
    "camels_ru_boundaries.gpkg",
    "camels_ru_discharge.nc",
    "camels_ru_forcing.nc",
    "camels_ru_forcing_notes.csv",
    "camels_ru_gauge_summary.csv",
    "camels_ru_signatures.csv",
    "camels_ru_signatures_summary.csv",
    "camels_ru_water_level.nc",
    "camels_ru_year_grades.csv",
]


@dataclass
class PreflightRow:
    """One preflight check result."""

    check: str
    path: str
    ok: bool
    detail: str


def _readlink(path: Path) -> str | None:
    if not path.is_symlink():
        return None
    return os.readlink(path)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pct(numer: int | float, denom: int | float) -> float:
    return float(numer) / float(denom) * 100.0 if denom else np.nan


def _annual_mean_mm_yr(s: pd.Series) -> float:
    valid = s.dropna()
    if valid.empty:
        return np.nan
    return float(valid.mean()) * 365.25


def _split_hydro_year(series: pd.Series, start_month: int = 10) -> dict[int, pd.Series]:
    out: dict[int, pd.Series] = {}
    for year, group in series.groupby(
        series.index.year + (series.index.month >= start_month).astype(int)
    ):
        out[int(year)] = group
    return out


def _annual_ratios(
    discharge: pd.Series,
    precipitation: pd.Series,
    pet: pd.Series,
    min_periods: int = 5,
) -> tuple[float, float]:
    q_periods = _split_hydro_year(discharge)
    p_periods = _split_hydro_year(precipitation)
    pet_periods = _split_hydro_year(pet)
    common = set(q_periods) & set(p_periods) & set(pet_periods)
    if len(common) < min_periods:
        return np.nan, np.nan

    aridity: list[float] = []
    evaporative: list[float] = []
    for year in sorted(common):
        q = float(np.nansum(q_periods[year]))
        p = float(np.nansum(p_periods[year]))
        pe = float(np.nansum(pet_periods[year]))
        if p > 0:
            aridity.append(pe / p)
            evaporative.append((p - q) / p)

    if len(aridity) < min_periods:
        return np.nan, np.nan
    return float(np.nanmean(aridity)), float(np.nanmean(evaporative))


def _hydroclimate_worker(
    gauge_id: str,
    q_values: np.ndarray,
    date_values: np.ndarray,
    root_str: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute Budyko and long-term AET adequacy rows for one gauge."""
    root = Path(root_str)
    dates = pd.DatetimeIndex(date_values)
    q = pd.Series(np.asarray(q_values, dtype=np.float64), index=dates, name="q").dropna()
    if len(q) < 365 * 5:
        return [], []

    gleam_path = root / GLEAM_DIR / f"{gauge_id}.csv"
    if not gleam_path.exists():
        return [], []

    try:
        gleam = pd.read_csv(
            gleam_path,
            index_col="date",
            parse_dates=True,
            usecols=["date", AET_COL, PET_COL],
        ).reindex(dates)
    except Exception:
        return [], []

    pet = gleam[PET_COL].dropna()
    if pet.empty:
        return [], []

    q_mm_yr = _annual_mean_mm_yr(q)
    aet_gleam = _annual_mean_mm_yr(gleam[AET_COL])
    pet_gleam = _annual_mean_mm_yr(gleam[PET_COL])

    budyko_rows: list[dict[str, Any]] = []
    aet_rows: list[dict[str, Any]] = []

    for product, (rel_dir, col) in PRODUCTS.items():
        p_path = root / rel_dir / f"{gauge_id}.csv"
        if not p_path.exists():
            continue
        p = pd.read_csv(p_path, index_col="date", parse_dates=True, usecols=["date", col])[col].reindex(
            dates
        )

        aridity, evaporative = _annual_ratios(q, p.dropna(), pet)
        budyko_rows.append(
            {
                "gauge_id": gauge_id,
                "product": product,
                "aridity_index": aridity,
                "evaporative_index": evaporative,
            }
        )

        p_mm_yr = _annual_mean_mm_yr(p)
        aet_wb = p_mm_yr - q_mm_yr if np.isfinite(p_mm_yr) and np.isfinite(q_mm_yr) else np.nan
        aet_rows.append(
            {
                "gauge_id": gauge_id,
                "product": product,
                "q_mm_yr": q_mm_yr,
                "p_mm_yr": p_mm_yr,
                "aet_wb_mm_yr": aet_wb,
                "aet_gleam_mm_yr": aet_gleam,
                "pet_gleam_mm_yr": pet_gleam,
                "aet_wb_minus_gleam_mm_yr": aet_wb - aet_gleam
                if np.isfinite(aet_wb) and np.isfinite(aet_gleam)
                else np.nan,
                "aet_wb_div_gleam": aet_wb / aet_gleam
                if np.isfinite(aet_wb) and np.isfinite(aet_gleam) and aet_gleam != 0
                else np.nan,
                "aet_wb_gt_pet": bool(aet_wb > pet_gleam)
                if np.isfinite(aet_wb) and np.isfinite(pet_gleam)
                else False,
                "aet_wb_lt_zero": bool(aet_wb < 0) if np.isfinite(aet_wb) else False,
            }
        )

    return budyko_rows, aet_rows


def _preflight() -> list[PreflightRow]:
    rows: list[PreflightRow] = []
    data_target = _readlink(DATA)
    rows.append(
        PreflightRow(
            "data_symlink",
            str(DATA),
            DATA.is_symlink(),
            f"target={data_target}" if data_target else "not a symlink",
        )
    )
    if data_target:
        target_path = Path(data_target)
        rows.append(PreflightRow("data_target_exists", data_target, target_path.exists(), ""))

    rows.append(PreflightRow("release_dir_exists", str(RELEASE), RELEASE.is_dir(), ""))

    for rel in REQUIRED_SOURCE_DIRS:
        p = ROOT / rel
        rows.append(PreflightRow("required_source_dir", rel, p.is_dir(), ""))
    for rel in REQUIRED_RELEASE_FILES:
        p = RELEASE / rel
        rows.append(PreflightRow("required_release_file", str(p.relative_to(ROOT)), p.is_file(), ""))
    return rows


def _write_preflight(rows: list[PreflightRow], out_dir: Path) -> None:
    df = pd.DataFrame([asdict(r) for r in rows])
    df.to_csv(out_dir / "preflight.csv", index=False)
    if not bool(df["ok"].all()):
        failed = df.loc[~df["ok"], ["check", "path", "detail"]]
        raise SystemExit("Preflight failed:\n" + failed.to_string(index=False))


def _load_release() -> dict[str, Any]:
    return {
        "attrs": pd.read_csv(RELEASE / "camels_ru_attributes.csv"),
        "gauge_summary": pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv"),
        "year_grades": pd.read_csv(RELEASE / "camels_ru_year_grades.csv"),
        "sigs": pd.read_csv(RELEASE / "camels_ru_signatures.csv"),
        "sig_summary": pd.read_csv(RELEASE / "camels_ru_signatures_summary.csv"),
        "forcing_notes": pd.read_csv(RELEASE / "camels_ru_forcing_notes.csv"),
        "boundaries": gpd.read_file(RELEASE / "camels_ru_boundaries.gpkg"),
    }


def _parse_macro_int(
    name: str, macros_path: Path = ROOT / "paper" / "overleaf" / "macros.tex"
) -> int | None:
    if not macros_path.exists():
        return None
    prefix = f"\\newcommand{{\\{name}}}"
    for raw_line in macros_path.read_text().splitlines():
        line = raw_line.split("%", 1)[0].strip()
        if not line.startswith(prefix):
            continue
        # LaTeX thousands separators use nested braces (e.g. 1{,}716), so a
        # naive "up to first }" regex would incorrectly return only "1".
        digits = re.sub(r"[^0-9]", "", line)
        return int(digits) if digits else None
    return None


def _build_subset_flow(
    data: dict[str, Any], out_dir: Path, strict_trace_summary: pd.DataFrame | None = None
) -> pd.DataFrame:
    attrs = data["attrs"]
    gauge_summary = data["gauge_summary"]
    year_grades = data["year_grades"]
    sigs = data["sigs"]
    boundaries = data["boundaries"]

    with open_release_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        n_discharge = int((~np.isnan(ds["discharge_mm"])).any(dim="time").sum().values)
    with open_release_dataset(RELEASE / "camels_ru_water_level.nc") as ds:
        n_water_level = int((~np.isnan(ds["water_level_cm"])).any(dim="time").sum().values)

    grade_cols = [c for c in year_grades.columns if c.isdigit()]
    strict_a = int(
        year_grades[grade_cols].apply(lambda r: all(v == "A" for v in r.dropna()), axis=1).sum()
    )
    clean_mask = ~sigs["is_anomalous"].astype(bool)

    def strict_trace_row(subset: str, macro_name: str) -> tuple[int, str, str]:
        if strict_trace_summary is not None and not strict_trace_summary.empty:
            matched = strict_trace_summary.loc[strict_trace_summary["subset"] == subset]
            if not matched.empty:
                row = matched.iloc[0]
                return int(row["n"]), str(row["derivation"]), str(row["status"])
        return (
            int(_parse_macro_int(macro_name) or 0),
            "paper/overleaf/macros.tex; strict subset needs intermediate reproduction",
            "macro_only_needs_intermediate_reproduction",
        )

    strict_n, strict_derivation, strict_status = strict_trace_row(
        "strict_completeness_main_text_maps", "nsigngaugesstrict"
    )
    half_strict_n, half_strict_derivation, half_strict_status = strict_trace_row(
        "half_flow_strict_main_text_maps", "nhalfflowstrict"
    )
    rows = [
        {
            "step": 1,
            "subset": "all_delineated_catchments",
            "n": int(len(boundaries)),
            "derivation": "rows in camels_ru_boundaries.gpkg",
            "status": "release_recomputed",
        },
        {
            "step": 2,
            "subset": "hydroatlas_covered_catchments",
            "n": int(len(attrs)),
            "derivation": "rows in camels_ru_attributes.csv",
            "status": "release_recomputed",
        },
        {
            "step": 3,
            "subset": "discharge_bearing_gauges",
            "n": n_discharge,
            "derivation": "gauge rows in discharge.nc with any finite discharge_mm",
            "status": "release_recomputed",
        },
        {
            "step": 4,
            "subset": "water_level_bearing_gauges",
            "n": n_water_level,
            "derivation": "gauge rows in water_level.nc with any finite water_level_cm",
            "status": "release_recomputed",
        },
        {
            "step": 5,
            "subset": "graded_discharge_gauges",
            "n": int(len(gauge_summary)),
            "derivation": "rows in camels_ru_gauge_summary.csv",
            "status": "release_recomputed",
        },
        {
            "step": 6,
            "subset": "grade_a_all_assessed_years",
            "n": strict_a,
            "derivation": "year_grades rows with every assessed year A",
            "status": "release_recomputed",
        },
        {
            "step": 7,
            "subset": "signatures_raw_area_record_filter",
            "n": int(len(sigs)),
            "derivation": "rows in camels_ru_signatures.csv",
            "status": "release_recomputed",
        },
        {
            "step": 8,
            "subset": "signatures_clean_non_anomalous",
            "n": int(clean_mask.sum()),
            "derivation": "camels_ru_signatures.csv rows with is_anomalous == False",
            "status": "release_recomputed",
        },
        {
            "step": 9,
            "subset": "water_balance_released_era5_columns",
            "n": int(
                (
                    clean_mask
                    & sigs[["runoff_ratio", "aridity_index", "evaporative_index"]].notna().all(axis=1)
                ).sum()
            ),
            "derivation": "clean signature rows with runoff_ratio, aridity_index, evaporative_index",
            "status": "release_recomputed",
        },
        {
            "step": 10,
            "subset": "half_flow_clean_non_anomalous",
            "n": int((clean_mask & sigs["half_flow_date"].notna()).sum()),
            "derivation": "clean signature rows with non-null half_flow_date",
            "status": "release_recomputed",
        },
        {
            "step": 11,
            "subset": "strict_completeness_main_text_maps",
            "n": strict_n,
            "derivation": strict_derivation,
            "status": strict_status,
        },
        {
            "step": 12,
            "subset": "half_flow_strict_main_text_maps",
            "n": half_strict_n,
            "derivation": half_strict_derivation,
            "status": half_strict_status,
        },
    ]
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "subset_flow.csv", index=False)
    return df


def _build_release_integrity(out_dir: Path) -> pd.DataFrame:
    manifest: dict[str, str] = {}
    sha_path = RELEASE / "SHA256SUMS"
    if sha_path.exists():
        for line in sha_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                manifest[parts[1].lstrip("* ")] = parts[0]

    rows: list[dict[str, Any]] = []
    for path in sorted(p for p in RELEASE.iterdir() if p.is_file()):
        rel = path.name
        digest = _sha256(path)
        expected = manifest.get(rel)
        rows.append(
            {
                "file": rel,
                "exists": True,
                "size_bytes": int(path.stat().st_size),
                "sha256": digest,
                "manifest_sha256": expected,
                "sha256_ok": bool(expected == digest) if expected else None,
                "required": rel in REQUIRED_RELEASE_FILES,
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "release_integrity.csv", index=False)
    return df


def _build_netcdf_schema(out_dir: Path) -> pd.DataFrame:
    categorical_exceptions = {"quality_flag", "gauge_type"}
    rows: list[dict[str, Any]] = []
    for filename in ["camels_ru_discharge.nc", "camels_ru_forcing.nc", "camels_ru_water_level.nc"]:
        path = RELEASE / filename
        with xr.open_dataset(path) as ds:
            dims = dict(ds.sizes)
            for var_name, da in ds.data_vars.items():
                units = da.attrs.get("units", "")
                long_name = da.attrs.get("long_name", "")
                source = da.attrs.get("source", "")
                missing_attrs = [
                    attr
                    for attr, value in {
                        "units": units,
                        "long_name": long_name,
                        "source": source,
                    }.items()
                    if not value
                ]
                is_categorical_exception = var_name in categorical_exceptions
                required_attrs_ok = bool(long_name) and (
                    (bool(units) and bool(source)) or is_categorical_exception
                )
                rows.append(
                    {
                        "file": filename,
                        "variable": var_name,
                        "dims": "×".join(da.dims),
                        "shape": "×".join(str(da.sizes[d]) for d in da.dims),
                        "dtype": str(da.dtype),
                        "units": units,
                        "long_name": long_name,
                        "source": source,
                        "missing_attrs": ";".join(missing_attrs),
                        "categorical_exception": is_categorical_exception,
                        "required_attrs_ok": required_attrs_ok,
                        "dataset_dims": json.dumps(dims, sort_keys=True),
                    }
                )
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "netcdf_schema.csv", index=False)
    return df


def _build_qc_summary(data: dict[str, Any], out_dir: Path) -> pd.DataFrame:
    gauge_summary = data["gauge_summary"]
    forcing_notes = data["forcing_notes"]
    rows: list[dict[str, Any]] = []
    total = int(len(gauge_summary))
    for grade in ["A", "B", "C", "D", "F"]:
        count = int((gauge_summary["overall_grade"] == grade).sum())
        rows.append(
            {
                "category": "overall_grade",
                "label": grade,
                "n": count,
                "percent_of_graded": _pct(count, total),
            }
        )
    for rec, count in gauge_summary["recommendation"].value_counts(dropna=False).items():
        rows.append(
            {
                "category": "recommendation",
                "label": str(rec),
                "n": int(count),
                "percent_of_graded": _pct(int(count), total),
            }
        )
    rows.append(
        {
            "category": "forcing_gap_fill",
            "label": "ERA5 temperature-filled gauges",
            "n": int(len(forcing_notes)),
            "percent_of_graded": np.nan,
        }
    )
    rows.append(
        {
            "category": "temperature_aware_qc",
            "label": "default_off_screening_heuristic",
            "n": 0,
            "percent_of_graded": np.nan,
        }
    )
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "qc_summary.csv", index=False)
    return df


def _normalize_id_header(name: str) -> str:
    """Normalize a candidate gauge-ID field name for case/spacing variants."""
    return re.sub(r"[^a-z0-9]+", "", str(name).casefold())


def _find_gauge_id_column(columns: list[str] | pd.Index, source: str) -> str:
    """Return the gauge identifier column, accepting capitalization variants only."""
    fields = list(dict.fromkeys(str(col) for col in columns))
    aliases = {"gaugeid": 0, "gauge": 1}
    matches = [
        (aliases[_normalize_id_header(col)], col)
        for col in fields
        if _normalize_id_header(col) in aliases
    ]
    if matches:
        matches.sort(key=lambda item: item[0])
        best_priority = matches[0][0]
        best = [col for priority, col in matches if priority == best_priority]
        if len(best) > 1:
            raise KeyError(f"Ambiguous gauge identifier columns for {source}: {best}")
        return best[0]
    gauge_like = [col for col in fields if "gauge" in col.casefold()]
    raise KeyError(f"No gauge identifier column found for {source}; gauge-like fields: {gauge_like}")


def _gauge_ids_from_frame(frame: pd.DataFrame | gpd.GeoDataFrame, source: str) -> tuple[pd.Series, str]:
    """Extract gauge IDs from a tabular source without assuming lower-case headers."""
    column = _find_gauge_id_column(frame.columns, source)
    return frame[column].astype(str), column


def _gauge_ids_from_csv(path: Path, source: str) -> tuple[pd.Series, str]:
    """Read gauge IDs from a CSV whose ID header may be capitalized."""
    header = pd.read_csv(path, nrows=0)
    column = _find_gauge_id_column(header.columns, source)
    values = pd.read_csv(path, dtype={column: str}, usecols=[column])[column].astype(str)
    return values, column


def _gauge_ids_from_netcdf(path: Path, source: str) -> tuple[pd.Series, str]:
    """Read gauge IDs from a NetCDF coordinate, accepting gauge_id/Gauge ID/gauge."""
    with open_release_dataset(path) as ds:
        names = list(ds.coords) + list(ds.dims)
        field = _find_gauge_id_column(names, source)
        return pd.Series(ds[field].values.astype(str)), field


def _build_gauge_id_length_audit(
    data: dict[str, Any], out_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write gauge-ID length diagnostics only; no auxiliary attribute columns."""
    source_items: list[tuple[str, pd.Series, str]] = []
    for source, frame_key in [
        ("attributes_csv", "attrs"),
        ("boundaries_gpkg", "boundaries"),
        ("year_grades_csv", "year_grades"),
        ("forcing_notes_csv", "forcing_notes"),
        ("signatures_csv", "sigs"),
        ("gauge_summary_csv", "gauge_summary"),
    ]:
        ids, field = _gauge_ids_from_frame(data[frame_key], source)
        source_items.append((source, ids, field))

    for nc_name in ["discharge", "forcing", "water_level"]:
        source = f"{nc_name}_nc"
        ids, field = _gauge_ids_from_netcdf(RELEASE / f"camels_ru_{nc_name}.nc", source)
        source_items.append((source, ids, field))

    optional_outputs = {
        "strict_signature_trace": out_dir / "strict_signature_gauge_ids.csv",
        "strict_half_flow_trace": out_dir / "strict_half_flow_gauge_ids.csv",
        "dam_excluded_signatures": out_dir / "dam_excluded_gauge_ids.csv",
    }
    for source, path in optional_outputs.items():
        if path.exists():
            ids, field = _gauge_ids_from_csv(path, source)
            source_items.append((source, ids, field))

    sources = {source: ids.astype(str) for source, ids, _ in source_items}
    summary_rows: list[dict[str, Any]] = []
    for source, ids, field in source_items:
        ids = ids.astype(str)
        lengths = ids.str.len()
        length_counts = lengths.value_counts().to_dict()
        summary_rows.append(
            {
                "source": source,
                "id_field": field,
                "n": int(len(ids)),
                "n_unique": int(ids.nunique()),
                "n_duplicate_rows": int(len(ids) - ids.nunique()),
                "min_length": int(lengths.min()) if len(lengths) else 0,
                "max_length": int(lengths.max()) if len(lengths) else 0,
                "len_4": int(length_counts.get(4, 0)),
                "len_5": int(length_counts.get(5, 0)),
                "len_6": int(length_counts.get(6, 0)),
                "len_7": int(length_counts.get(7, 0)),
                "len_gt_7": int((lengths > 7).sum()),
                "len_ge_7": int((lengths >= 7).sum()),
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out_dir / "gauge_id_length_summary.csv", index=False)

    all_long_ids = sorted(
        {gauge_id for ids in sources.values() for gauge_id in ids.astype(str) if len(gauge_id) >= 7}
    )
    long_df = pd.DataFrame({"gauge_id": all_long_ids})
    long_df["gauge_id_length"] = long_df["gauge_id"].str.len()
    for source, ids in sources.items():
        long_df[f"in_{source}"] = long_df["gauge_id"].isin(set(ids.astype(str)))
    membership_cols = [col for col in long_df.columns if col.startswith("in_")]
    long_df["source_count"] = long_df[membership_cols].sum(axis=1).astype(int)
    long_df.to_csv(out_dir / "long_gauge_ids.csv", index=False)
    return summary, long_df


def _build_paper_analysis_scope(
    data: dict[str, Any], out_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write the gauge-ID-only exclusion used by manuscript analyses."""

    def row(source: str, ids: pd.Series, derivation: str) -> dict[str, Any]:
        ids = ids.astype(str)
        scope = paper_analysis_scope_summary(ids)
        return {
            "source": source,
            "n_total": scope.n_total,
            "n_paper_analysis": scope.n_included,
            "n_excluded": scope.n_excluded,
            "excluded_min_id_length": scope.excluded_min_id_length,
            "exclusion_rule": PAPER_ANALYSIS_EXCLUSION_LABEL,
            "derivation": derivation,
        }

    rows: list[dict[str, Any]] = []
    for source, frame_key, derivation in [
        ("boundaries_gpkg", "boundaries", "all delineated catchments"),
        ("attributes_csv", "attrs", "HydroATLAS-covered attributes"),
        ("gauge_summary_csv", "gauge_summary", "discharge gauges with grade summary"),
        ("year_grades_csv", "year_grades", "discharge gauges with annual grades"),
        ("signatures_csv", "sigs", "released hydrological signature rows"),
    ]:
        ids, _field = _gauge_ids_from_frame(data[frame_key], source)
        rows.append(row(source, ids, derivation))

    for nc_name in ["discharge", "forcing", "water_level"]:
        source = f"{nc_name}_nc_all_rows"
        ids, _field = _gauge_ids_from_netcdf(RELEASE / f"camels_ru_{nc_name}.nc", source)
        rows.append(row(source, ids, f"all coordinate rows in camels_ru_{nc_name}.nc"))

    nc_data_vars = {
        "discharge": "discharge_mm",
        "water_level": "water_level_cm",
    }
    for nc_name, data_var in nc_data_vars.items():
        with open_release_dataset(RELEASE / f"camels_ru_{nc_name}.nc") as ds:
            gauge_coord = "gauge_id" if "gauge_id" in ds.coords else "gauge"
            ids = pd.Series(ds[gauge_coord].values.astype(str))
            has_data = (~np.isnan(ds[data_var])).any(dim="time").values.astype(bool)
            rows.append(
                row(
                    f"{nc_name}_nc_with_data",
                    ids.loc[has_data],
                    f"{data_var} rows with at least one non-NaN value",
                )
            )

    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "paper_analysis_scope_summary.csv", index=False)

    boundary_ids, _field = _gauge_ids_from_frame(data["boundaries"], "boundaries_gpkg")
    excluded = sorted(
        gauge_id
        for gauge_id in boundary_ids.astype(str).unique()
        if is_paper_analysis_excluded_gauge_id(gauge_id)
    )
    excluded_df = pd.DataFrame(
        {
            "gauge_id": excluded,
            "gauge_id_length": [len(gauge_id) for gauge_id in excluded],
            "exclusion_rule": PAPER_ANALYSIS_EXCLUSION_LABEL,
        }
    )
    excluded_df.to_csv(out_dir / "paper_analysis_excluded_gauge_ids.csv", index=False)
    (out_dir / "paper_analysis_scope_note.md").write_text(PAPER_ANALYSIS_EXCLUSION_NOTE + "\n")
    return summary, excluded_df


def _convert_q_cms_to_mm_day(q_cms: pd.Series, area_km2: float) -> pd.Series:
    """Convert discharge from cubic metres per second to mm per day."""
    return q_cms * 86400 / (area_km2 * 1e6) * 1e3


def _build_strict_subset_trace(out_dir: Path, workers: int) -> pd.DataFrame:  # noqa: C901
    """Reproduce strict map-subset gauge IDs from local intermediate data when present."""
    geom_dir = ROOT / "data" / "CAMELS_RU" / "geometry"
    compound_dir = ROOT / "data" / "CAMELS_RU" / "HydroData" / "Compound"
    required_paths = [
        geom_dir / "camels_watersheds.gpkg",
        geom_dir / "camels_gauges.gpkg",
        compound_dir,
    ]
    if not all(path.exists() for path in required_paths):
        summary = pd.DataFrame(
            [
                {
                    "subset": "strict_completeness_main_text_maps",
                    "n": _parse_macro_int("nsigngaugesstrict"),
                    "derivation": "local intermediate geometry/Compound files unavailable",
                    "status": "macro_only_missing_intermediate_sources",
                },
                {
                    "subset": "half_flow_strict_main_text_maps",
                    "n": _parse_macro_int("nhalfflowstrict"),
                    "derivation": "local intermediate geometry/Compound files unavailable",
                    "status": "macro_only_missing_intermediate_sources",
                },
            ]
        )
        summary.to_csv(out_dir / "strict_subset_trace_summary.csv", index=False)
        return summary

    from src.hydro.parallel_metrics import calculate_metrics_parallel

    ws = gpd.read_file(geom_dir / "camels_watersheds.gpkg")
    ws["gauge_id"] = ws["gauge_id"].astype(str)
    ws = ws.set_index("gauge_id")
    gauge = gpd.read_file(geom_dir / "camels_gauges.gpkg")
    gauge["gauge_id"] = gauge["gauge_id"].astype(str)
    gauge = gauge.set_index("gauge_id")

    ws = filter_paper_analysis_index(ws)
    gauge = filter_paper_analysis_index(gauge)

    ws = ws.loc[ws["area_km2"] < 50_000]
    gauge = gauge.loc[gauge.index.intersection(ws.index)]

    discharge_data: dict[str, pd.Series] = {}
    for gauge_id in ws.index:
        csv_path = compound_dir / f"{gauge_id}.csv"
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
            if "q_cms" not in df.columns:
                continue
            area_km2 = float(ws.loc[gauge_id, "area_km2"])
            if area_km2 <= 0 or np.isnan(area_km2):
                continue
            q_series = df["q_cms"].dropna()
            q_mm_day = _convert_q_cms_to_mm_day(q_series, area_km2)
            if len(q_mm_day) > 365:
                discharge_data[gauge_id] = q_mm_day
        except Exception:  # noqa: BLE001, S112
            continue

    q_seasonal: dict[str, np.ndarray] = {}
    for gauge_id, ts in discharge_data.items():
        cycle = ts.groupby([ts.index.month, ts.index.day]).median()  # type: ignore[union-attr]
        if (2, 29) in cycle.index:
            cycle = cycle.drop((2, 29))
        if len(cycle) == 365:
            q_seasonal[gauge_id] = np.asarray(cycle)

    q_df = pd.DataFrame.from_dict(q_seasonal, orient="columns")
    q_df = q_df.loc[:, q_df.max() < 50]
    q_min = q_df.min()
    q_range = (q_df.max() - q_min).replace(0, np.nan)
    q_df_norm = ((q_df - q_min) / q_range).dropna(axis=1)
    q_clust = q_df_norm.T.copy()
    raw_lat = pd.Series(
        {gid: gauge.loc[gid, "geometry"].y for gid in q_clust.index if gid in gauge.index}
    )
    raw_lon = pd.Series(
        {gid: gauge.loc[gid, "geometry"].x for gid in q_clust.index if gid in gauge.index}
    )
    q_clust["lat"] = (raw_lat - raw_lat.min()) / (raw_lat.max() - raw_lat.min())
    q_clust["lon"] = (raw_lon - raw_lon.min()) / (raw_lon.max() - raw_lon.min())
    q_clust = q_clust.dropna()
    hydro_index = q_clust.index.astype(str)
    metric_discharge = {k: v for k, v in discharge_data.items() if k in hydro_index}

    all_metrics = calculate_metrics_parallel(
        discharge_data=metric_discharge,
        gauge_ids=hydro_index,
        n_workers=workers,
        period_type="hydrological",
        hydro_year_start_month=10,
        min_data_fraction=0.7,
        min_periods=5,
        aggregation="mean",
        show_progress=False,
    )
    metrics_df = pd.DataFrame.from_dict(all_metrics, orient="index").dropna(thresh=5)
    metrics_df.index = metrics_df.index.astype(str)

    trace = pd.DataFrame({"gauge_id": metrics_df.index})
    trace["has_half_flow_date"] = metrics_df["mean_half_flow_date"].notna().to_numpy()
    attrs = pd.read_csv(RELEASE / "camels_ru_attributes.csv", usecols=["gauge_id", DAM_PROXY_COL])
    attrs["gauge_id"] = attrs["gauge_id"].astype(str)
    trace = trace.merge(attrs, on="gauge_id", how="left")
    trace[DAM_PROXY_COL] = pd.to_numeric(trace[DAM_PROXY_COL], errors="coerce")
    trace["regulation_proxy_class"] = np.select(
        [trace[DAM_PROXY_COL].eq(0), trace[DAM_PROXY_COL].gt(0)],
        ["dam_excluded", "dam_regulated_proxy"],
        default="dam_proxy_unknown",
    )
    trace.to_csv(out_dir / "strict_signature_gauge_ids.csv", index=False, float_format="%.6g")
    trace.loc[trace["has_half_flow_date"]].to_csv(
        out_dir / "strict_half_flow_gauge_ids.csv", index=False, float_format="%.6g"
    )

    summary_rows = [
        {
            "subset": "strict_completeness_main_text_maps",
            "n": int(len(trace)),
            "derivation": "recomputed from data/CAMELS_RU geometry and Compound discharge files",
            "status": "intermediate_recomputed",
        },
        {
            "subset": "half_flow_strict_main_text_maps",
            "n": int(trace["has_half_flow_date"].sum()),
            "derivation": "strict map subset with non-null mean_half_flow_date",
            "status": "intermediate_recomputed",
        },
    ]
    for label, mask in {
        "strict_dam_excluded_overlap": trace["regulation_proxy_class"].eq("dam_excluded"),
        "strict_regulated_proxy_overlap": trace["regulation_proxy_class"].eq("dam_regulated_proxy"),
        "strict_unknown_regulation_overlap": trace["regulation_proxy_class"].eq("dam_proxy_unknown"),
    }.items():
        summary_rows.append(
            {
                "subset": label,
                "n": int(mask.sum()),
                "derivation": f"strict map subset cross-tabbed with {DAM_PROXY_COL}",
                "status": "intermediate_recomputed",
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out_dir / "strict_subset_trace_summary.csv", index=False)
    return summary


def _build_dam_excluded_analytics(
    data: dict[str, Any], out_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build HESS-facing summaries that exclude dam-regulated gauges by default.

    CAMELS-RU does not yet ship a manually verified natural-basin flag for discharge gauges.
    This audit therefore uses HydroATLAS ``dor_pc_pva`` as a conservative regulation proxy:
    broad hydrological conclusions use cleaned signature rows with ``dor_pc_pva == 0``.
    Rows with ``dor_pc_pva > 0`` and rows missing HydroATLAS regulation coverage are excluded
    from broad summaries. Lake/reservoir area (``lka_pc_use``) is reported as context, not a
    hard exclusion, because it mixes natural lakes and reservoirs.
    """
    sigs = data["sigs"].copy()
    attrs = data["attrs"].copy()
    attribute_cols = [
        "gauge_id",
        DAM_PROXY_COL,
        "lka_pc_use",
        "prm_pc_use",
        "snw_pc_uyr",
        "ari_ix_uav",
        "tmp_dc_uyr",
        "pre_mm_uyr",
        "pet_mm_uyr",
        "ele_mt_uav",
        "for_pc_use",
        "crp_pc_use",
        "urb_pc_use",
        "lat",
        "lon",
    ]
    available_attribute_cols = [c for c in attribute_cols if c in attrs.columns]
    merged = sigs.merge(attrs[available_attribute_cols], on="gauge_id", how="left")
    merged[DAM_PROXY_COL] = pd.to_numeric(merged[DAM_PROXY_COL], errors="coerce")

    clean = ~merged["is_anomalous"].astype(bool)
    dor_present = merged[DAM_PROXY_COL].notna()
    dam_free = clean & merged[DAM_PROXY_COL].eq(0)
    regulated = clean & merged[DAM_PROXY_COL].gt(0)
    unknown = clean & ~dor_present
    water_balance = clean & merged[["runoff_ratio", "aridity_index", "evaporative_index"]].notna().all(
        axis=1
    )
    half_flow = clean & merged["half_flow_date"].notna()

    def count_row(subset: str, mask: pd.Series, derivation: str) -> dict[str, Any]:
        n = int(mask.sum())
        return {
            "subset": subset,
            "n": n,
            "percent_of_cleaned_signatures": _pct(n, int(clean.sum())),
            "derivation": derivation,
        }

    counts = pd.DataFrame(
        [
            count_row(
                "signatures_clean_non_anomalous",
                clean,
                "camels_ru_signatures.csv rows with is_anomalous == False",
            ),
            count_row(
                "signatures_clean_hydroatlas_matched",
                clean & dor_present,
                "clean signatures with HydroATLAS dor_pc_pva available",
            ),
            count_row(
                "broad_analysis_dam_excluded",
                dam_free,
                "clean signatures with HydroATLAS degree-of-regulation proxy dor_pc_pva == 0",
            ),
            count_row(
                "dam_regulated_proxy",
                regulated,
                "clean signatures with dor_pc_pva > 0; excluded from broad hydrological summaries",
            ),
            count_row(
                "dam_proxy_unknown",
                unknown,
                "clean signatures without HydroATLAS dor_pc_pva; excluded from broad summaries",
            ),
            count_row(
                "water_balance_dam_excluded",
                water_balance & merged[DAM_PROXY_COL].eq(0),
                "dam-excluded cleaned signatures with runoff_ratio, aridity_index, evaporative_index",
            ),
            count_row(
                "half_flow_dam_excluded",
                half_flow & merged[DAM_PROXY_COL].eq(0),
                "dam-excluded cleaned signatures with non-null half_flow_date",
            ),
        ]
    )
    counts.to_csv(out_dir / "dam_filter_summary.csv", index=False, float_format="%.6g")

    subset_masks: dict[str, pd.Series] = {
        "all_cleaned_signatures": clean,
        "broad_analysis_dam_excluded": dam_free,
        "dam_regulated_proxy": regulated,
    }
    metrics = [
        "q_mean",
        "runoff_ratio",
        "baseflow_index",
        "half_flow_date",
        "fdc_slope",
        "flashiness_index",
        "q_cv",
        "q05",
        "q95",
        "aridity_index",
        "evaporative_index",
        "snw_pc_uyr",
        "prm_pc_use",
        "tmp_dc_uyr",
        "ari_ix_uav",
        "lka_pc_use",
        DAM_PROXY_COL,
    ]
    summary_rows: list[dict[str, Any]] = []
    for subset, mask in subset_masks.items():
        for metric in metrics:
            if metric not in merged.columns:
                continue
            values = pd.to_numeric(merged.loc[mask, metric], errors="coerce").dropna()
            if values.empty:
                continue
            summary_rows.append(
                {
                    "subset": subset,
                    "metric": metric,
                    "n": int(len(values)),
                    "mean": float(values.mean()),
                    "median": float(values.median()),
                    "p10": float(values.quantile(0.10)),
                    "p90": float(values.quantile(0.90)),
                    "min": float(values.min()),
                    "max": float(values.max()),
                }
            )
    signature_summary = pd.DataFrame(summary_rows)
    signature_summary.to_csv(
        out_dir / "dam_excluded_signature_summary.csv", index=False, float_format="%.6g"
    )

    gauge_cols = [
        "gauge_id",
        DAM_PROXY_COL,
        "lka_pc_use",
        "prm_pc_use",
        "snw_pc_uyr",
        "q_mean",
        "runoff_ratio",
        "baseflow_index",
        "half_flow_date",
        "aridity_index",
        "evaporative_index",
    ]
    merged.loc[dam_free, [c for c in gauge_cols if c in merged.columns]].to_csv(
        out_dir / "dam_excluded_gauge_ids.csv", index=False, float_format="%.6g"
    )

    strict_trace_path = out_dir / "strict_subset_trace_summary.csv"
    strict_topic_status = "pending_intermediate_reproduction"
    strict_topic_output = "pending gauge-ID evidence artefact"
    if strict_trace_path.exists():
        strict_trace = pd.read_csv(strict_trace_path)
        strict_rows = strict_trace.loc[
            strict_trace["subset"].isin(
                ["strict_completeness_main_text_maps", "half_flow_strict_main_text_maps"]
            )
        ]
        if not strict_rows.empty and strict_rows["status"].eq("intermediate_recomputed").all():
            strict_topic_status = "performed_with_local_intermediate_data"
            strict_topic_output = (
                "strict_subset_trace_summary.csv; strict_signature_gauge_ids.csv; "
                "strict_half_flow_gauge_ids.csv"
            )

    research_topics = pd.DataFrame(
        [
            {
                "topic": "dam_excluded_broad_signatures",
                "question": (
                    "Do headline hydrological signatures change when regulated gauges are excluded?"
                ),
                "data_used": ("camels_ru_signatures.csv + camels_ru_attributes.csv dor_pc_pva"),
                "output": (
                    "dam_filter_summary.csv; dam_excluded_signature_summary.csv; "
                    "dam_excluded_gauge_ids.csv"
                ),
                "status": "performed_with_existing_release_data",
                "manuscript_use": (
                    "Use dam-excluded subset for broad HESS hydrological statements; "
                    "keep regulated gauges as flagged data records."
                ),
            },
            {
                "topic": "cold_region_representativeness",
                "question": (
                    "How much of the dam-excluded broad subset samples snow/permafrost gradients?"
                ),
                "data_used": ("HydroATLAS snw_pc_uyr, prm_pc_use, tmp_dc_uyr merged to signatures"),
                "output": "dam_excluded_signature_summary.csv",
                "status": "performed_as_proxy_summary",
                "manuscript_use": (
                    "Supports HESS framing that CAMELS-RU expands CAMELS into "
                    "snow/permafrost regimes without causal permafrost overclaiming."
                ),
            },
            {
                "topic": "forcing_water_balance_sensitivity",
                "question": (
                    "How do precipitation products alter Q/P, Budyko-envelope and "
                    "AET-adequacy diagnostics?"
                ),
                "data_used": "existing meteo folders + discharge.nc + GLEAM PET/AET",
                "output": (
                    "budyko_aet_table.csv; budyko_per_gauge_product.csv; aet_per_gauge_product.csv"
                ),
                "status": "performed_in_hess_quality_audit",
                "manuscript_use": (
                    "Central HESS science spine: forcing choice controls apparent water-balance realism."
                ),
            },
            {
                "topic": "strict_subset_reproducibility",
                "question": (
                    "Can the 1,716 / 1,641 strict map subsets be regenerated from "
                    "intermediate processing artefacts?"
                ),
                "data_used": (
                    "intermediate signature/map processing outputs, not fully captured by release CSVs"
                ),
                "output": strict_topic_output,
                "status": strict_topic_status,
                "manuscript_use": (
                    "Needed before submission for complete traceability of map/sample-size claims."
                ),
            },
        ]
    )
    research_topics.to_csv(out_dir / "hess_research_topics.csv", index=False)

    notes = [
        "# Dam-excluded HESS analytics notes",
        "",
        (
            "Broad hydrological interpretation now treats HydroATLAS `dor_pc_pva > 0` "
            "as a regulation proxy and excludes those gauges by default."
        ),
        (
            "Missing HydroATLAS regulation values are also excluded from broad "
            "summaries until inspected manually."
        ),
        (
            "Lake/reservoir area (`lka_pc_use`) is retained as context because it "
            "mixes natural lakes and reservoirs."
        ),
        "",
        "## Key counts",
    ]
    for row in counts.to_dict(orient="records"):
        notes.append(
            f"- {row['subset']}: n={row['n']} "
            f"({row['percent_of_cleaned_signatures']:.1f}% of cleaned signatures)."
        )
    notes.extend(
        [
            "",
            "## Reviewer-facing caution",
            (
                "This is a proxy filter, not a verified natural-basin classification. "
                "It is appropriate for broad HESS summaries but should be labelled as "
                "dam/regulation-excluded rather than near-natural."
            ),
        ]
    )
    (out_dir / "dam_excluded_hess_notes.md").write_text("\n".join(notes) + "\n")
    return counts, signature_summary


def _build_forcing_tables(out_dir: Path) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    product_path = ROOT / "paper" / "tables" / "precip_dataset_comparison.csv"
    pair_path = ROOT / "paper" / "tables" / "precip_inter_dataset_corr.csv"
    product_df = pd.read_csv(product_path) if product_path.exists() else None
    pair_df = pd.read_csv(pair_path) if pair_path.exists() else None
    if product_df is not None:
        product_df.to_csv(out_dir / "forcing_product_summary.csv", index=False)
    if pair_df is not None:
        pair_df.to_csv(out_dir / "forcing_pairwise_summary.csv", index=False)
    return product_df, pair_df


def _build_budyko_aet(data: dict[str, Any], out_dir: Path, workers: int) -> pd.DataFrame:
    boundaries = data["boundaries"][["gauge_id", "area_km2"]].copy()
    boundaries["gauge_id"] = boundaries["gauge_id"].astype(str)
    area_lookup = dict(zip(boundaries["gauge_id"], boundaries["area_km2"], strict=False))
    anomaly_lookup = dict(
        zip(
            data["sigs"]["gauge_id"].astype(str),
            data["sigs"]["is_anomalous"].astype(bool),
            strict=False,
        )
    )

    with open_release_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        gauge_coord = "gauge_id" if "gauge_id" in ds.coords else "gauge"
        gauges = [str(g) for g in ds[gauge_coord].values]
        dates = ds["time"].values
        q = ds["discharge_mm"].values

    valid_idx = [
        i
        for i, gauge in enumerate(gauges)
        if not is_paper_analysis_excluded_gauge_id(gauge)
        and area_lookup.get(gauge, np.inf) < 50_000
        and np.isfinite(q[i]).sum() >= 365 * 5
    ]

    budyko_rows: list[dict[str, Any]] = []
    aet_rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as exe:
        futures = {
            exe.submit(_hydroclimate_worker, gauges[i], q[i], dates, str(ROOT)): gauges[i]
            for i in valid_idx
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="HESS hydroclimate audit"):
            b_rows, a_rows = fut.result()
            budyko_rows.extend(b_rows)
            aet_rows.extend(a_rows)

    budyko_df = pd.DataFrame(budyko_rows)
    aet_df = pd.DataFrame(aet_rows)
    if budyko_df.empty or aet_df.empty:
        raise SystemExit("No Budyko/AET rows produced; check source meteo folders")

    for df in [budyko_df, aet_df]:
        df["area_km2"] = df["gauge_id"].map(area_lookup)
        df["area_ge_50"] = df["area_km2"] >= 50.0
        df["is_release_anomalous"] = df["gauge_id"].map(anomaly_lookup).fillna(False).astype(bool)

    budyko_df.to_csv(out_dir / "budyko_per_gauge_product.csv", index=False, float_format="%.6g")
    aet_df.to_csv(out_dir / "aet_per_gauge_product.csv", index=False, float_format="%.6g")

    rows: list[dict[str, Any]] = []
    for product in PRODUCTS:
        b = budyko_df.loc[budyko_df["product"] == product].dropna(
            subset=["aridity_index", "evaporative_index"]
        )
        a = aet_df.loc[(aet_df["product"] == product) & (aet_df["area_km2"] >= 50.0)].dropna(
            subset=["aet_wb_mm_yr", "aet_gleam_mm_yr", "pet_gleam_mm_yr"]
        )
        a_release_clean = aet_df.loc[
            (aet_df["product"] == product) & (~aet_df["is_release_anomalous"])
        ].dropna(subset=["aet_wb_mm_yr", "aet_gleam_mm_yr", "pet_gleam_mm_yr"])

        energy = b["evaporative_index"] > b["aridity_index"]
        water = b["evaporative_index"] > 1.0
        envelope = b["evaporative_index"] > np.minimum(b["aridity_index"], 1.0)
        closure = b["evaporative_index"] < 0.0
        rows.append(
            {
                "product": product,
                "budyko_n_raw": int(len(b)),
                "budyko_n_release_clean": int((~b["is_release_anomalous"]).sum()),
                "budyko_n_area_ge_50": int(b["area_ge_50"].sum()),
                "median_aridity_index": float(b["aridity_index"].median()),
                "median_evaporative_index": float(b["evaporative_index"].median()),
                "energy_violation_n": int(energy.sum()),
                "energy_violation_pct": _pct(int(energy.sum()), len(b)),
                "water_limit_violation_n": int(water.sum()),
                "water_limit_violation_pct": _pct(int(water.sum()), len(b)),
                "combined_envelope_violation_n": int(envelope.sum()),
                "combined_envelope_violation_pct": _pct(int(envelope.sum()), len(b)),
                "closure_q_gt_p_n": int(closure.sum()),
                "closure_q_gt_p_pct": _pct(int(closure.sum()), len(b)),
                "aet_area_ge_50_n": int(len(a)),
                "aet_release_clean_n": int(len(a_release_clean)),
                "median_q_mm_yr": float(a["q_mm_yr"].median()),
                "median_p_mm_yr": float(a["p_mm_yr"].median()),
                "median_gleam_aet_mm_yr": float(a["aet_gleam_mm_yr"].median()),
                "median_gleam_pet_mm_yr": float(a["pet_gleam_mm_yr"].median()),
                "median_aet_wb_mm_yr": float(a["aet_wb_mm_yr"].median()),
                "median_aet_wb_minus_gleam_mm_yr": float(a["aet_wb_minus_gleam_mm_yr"].median()),
                "median_aet_wb_div_gleam": float(a["aet_wb_div_gleam"].median()),
                "aet_wb_gt_pet_n": int(a["aet_wb_gt_pet"].sum()),
                "aet_wb_gt_pet_pct": _pct(int(a["aet_wb_gt_pet"].sum()), len(a)),
                "aet_wb_lt_zero_n": int(a["aet_wb_lt_zero"].sum()),
                "aet_wb_lt_zero_pct": _pct(int(a["aet_wb_lt_zero"].sum()), len(a)),
            }
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "budyko_aet_table.csv", index=False, float_format="%.6g")
    return summary


def _write_latex_tables(out_dir: Path) -> None:
    for csv_name in [
        "subset_flow.csv",
        "budyko_aet_table.csv",
        "qc_summary.csv",
        "dam_filter_summary.csv",
        "dam_excluded_signature_summary.csv",
        "strict_subset_trace_summary.csv",
    ]:
        path = out_dir / csv_name
        if not path.exists():
            continue
        df = pd.read_csv(path)
        tex = df.to_latex(index=False, escape=True, float_format=lambda x: f"{x:.2f}")
        (out_dir / f"{Path(csv_name).stem}.tex").write_text(tex)


def _write_diagnostics(
    out_dir: Path,
    subset_flow: pd.DataFrame,
    release_integrity: pd.DataFrame,
    netcdf_schema: pd.DataFrame,
    qc_summary: pd.DataFrame,
    budyko_aet: pd.DataFrame,
    dam_filter_summary: pd.DataFrame,
    dam_signature_summary: pd.DataFrame,
    strict_trace_summary: pd.DataFrame,
    gauge_id_length_summary: pd.DataFrame,
    long_gauge_ids: pd.DataFrame,
    paper_analysis_scope: pd.DataFrame,
    paper_analysis_excluded_ids: pd.DataFrame,
    product_df: pd.DataFrame | None,
    pair_df: pd.DataFrame | None,
) -> None:
    manifested_sha_ok = release_integrity.loc[release_integrity["manifest_sha256"].notna(), "sha256_ok"]
    manifested_sha_ok = (
        manifested_sha_ok.astype(bool) if not manifested_sha_ok.empty else pd.Series(dtype=bool)
    )

    strict_rows = strict_trace_summary.loc[
        strict_trace_summary["subset"].isin(
            ["strict_completeness_main_text_maps", "half_flow_strict_main_text_maps"]
        )
    ]
    strict_recomputed = bool(
        not strict_rows.empty and strict_rows["status"].eq("intermediate_recomputed").all()
    )

    payload: dict[str, Any] = {
        "outputs_dir": str(out_dir.relative_to(ROOT)),
        "notes": [
            "Zenodo DOI stays local/pending; no upload or minting performed.",
            (
                "strict_completeness_main_text_maps was reproduced from local intermediate "
                "geometry and Compound discharge files."
                if strict_recomputed
                else (
                    "strict_completeness_main_text_maps remains macro-only; local "
                    "intermediate reproduction unavailable."
                )
            ),
            (
                "Budyko indices are paired hydrological-year ratios; "
                "AET adequacy uses long-term annual means."
            ),
            (
                "Broad hydrological analytics use a dam/regulation-excluded subset "
                "based on HydroATLAS dor_pc_pva == 0; this is a proxy, not a verified "
                "near-natural classification."
            ),
            PAPER_ANALYSIS_EXCLUSION_NOTE,
        ],
        "subset_flow": subset_flow.to_dict(orient="records"),
        "release_integrity": {
            "n_files": int(len(release_integrity)),
            "all_required_present": bool(
                set(REQUIRED_RELEASE_FILES).issubset(set(release_integrity["file"]))
            ),
            "sha256_all_manifested_ok": bool(manifested_sha_ok.all()),
            "total_bytes": int(release_integrity["size_bytes"].sum()),
            "total_gb_decimal": float(release_integrity["size_bytes"].sum() / 1e9),
            "total_gib_binary": float(release_integrity["size_bytes"].sum() / 1024**3),
        },
        "netcdf_variables": int(len(netcdf_schema)),
        "netcdf_required_attrs_ok": bool(netcdf_schema["required_attrs_ok"].astype(bool).all()),
        "netcdf_categorical_exceptions": netcdf_schema.loc[
            netcdf_schema["categorical_exception"].astype(bool),
            ["file", "variable", "missing_attrs"],
        ].to_dict(orient="records"),
        "qc_summary": qc_summary.to_dict(orient="records"),
        "budyko_aet_table": budyko_aet.to_dict(orient="records"),
        "dam_filter_summary": dam_filter_summary.to_dict(orient="records"),
        "dam_signature_summary_rows": int(len(dam_signature_summary)),
        "strict_trace_summary": strict_trace_summary.to_dict(orient="records"),
        "gauge_id_length_summary": gauge_id_length_summary.to_dict(orient="records"),
        "long_gauge_ids_rows": int(len(long_gauge_ids)),
        "paper_analysis_scope": paper_analysis_scope.to_dict(orient="records"),
        "paper_analysis_excluded_ids_rows": int(len(paper_analysis_excluded_ids)),
        "forcing_product_summary_available": product_df is not None,
        "forcing_pairwise_summary_available": pair_df is not None,
    }
    (out_dir / "diagnostics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> None:
    """Run the CAMELS-RU HESS quality audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    preflight_rows = _preflight()
    _write_preflight(preflight_rows, args.out_dir)

    data = _load_release()
    strict_trace_summary = _build_strict_subset_trace(args.out_dir, workers=args.workers)
    subset_flow = _build_subset_flow(data, args.out_dir, strict_trace_summary)
    release_integrity = _build_release_integrity(args.out_dir)
    netcdf_schema = _build_netcdf_schema(args.out_dir)
    qc_summary = _build_qc_summary(data, args.out_dir)
    dam_filter_summary, dam_signature_summary = _build_dam_excluded_analytics(data, args.out_dir)
    gauge_id_length_summary, long_gauge_ids = _build_gauge_id_length_audit(data, args.out_dir)
    paper_analysis_scope, paper_analysis_excluded_ids = _build_paper_analysis_scope(data, args.out_dir)
    product_df, pair_df = _build_forcing_tables(args.out_dir)
    budyko_aet = _build_budyko_aet(data, args.out_dir, workers=args.workers)
    _write_latex_tables(args.out_dir)
    _write_diagnostics(
        args.out_dir,
        subset_flow,
        release_integrity,
        netcdf_schema,
        qc_summary,
        budyko_aet,
        dam_filter_summary,
        dam_signature_summary,
        strict_trace_summary,
        gauge_id_length_summary,
        long_gauge_ids,
        paper_analysis_scope,
        paper_analysis_excluded_ids,
        product_df,
        pair_df,
    )

    print(f"Wrote HESS quality audit artefacts to {args.out_dir.relative_to(ROOT)}")
    print(f"Subset rows: {len(subset_flow)}")
    print(f"Long gauge IDs (len >= 7): {len(long_gauge_ids)}")
    print(f"Paper-analysis gauge-ID exclusions: {len(paper_analysis_excluded_ids)}")
    strict_row = strict_trace_summary.loc[
        strict_trace_summary["subset"] == "strict_completeness_main_text_maps"
    ].iloc[0]
    print(f"Strict map subset trace: {int(strict_row['n'])} ({strict_row['status']})")
    print(f"Budyko/AET products: {', '.join(budyko_aet['product'].astype(str))}")
    dam_free_row = dam_filter_summary.loc[
        dam_filter_summary["subset"] == "broad_analysis_dam_excluded"
    ].iloc[0]
    print(f"Dam-excluded broad signatures: {int(dam_free_row['n'])}")
    print("Zenodo DOI remains local/pending; no upload or DOI minting performed.")


if __name__ == "__main__":
    sys.path.append(str(ROOT))
    main()
