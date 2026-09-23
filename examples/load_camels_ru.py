"""Load CAMELS-RU v1.0 or a local v1.1 candidate with explicit reuse masks.

Shows the three conventions a user needs: keep ``gauge_id`` as a string, mask
gap-filled days with ``quality_flag``, and drop hydrological years graded D or F.
Attribute metadata excludes invalid category means; retained fields still require
their documented spatial-support and unit qualifications.

Run: ``pixi run python examples/load_camels_ru.py [release_dir]``
"""

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import xarray as xr

from utils.release_io import open_release_dataset

RELEASE = Path(sys.argv[1] if len(sys.argv) > 1 else "release/CAMELS_RU_v1.0")


def load_attributes() -> pd.DataFrame:
    """Exclude fields marked unsuitable; use tracked metadata for frozen v1.0."""
    attributes = pd.read_csv(RELEASE / "camels_ru_attributes.csv", dtype={"gauge_id": str})
    metadata_path = RELEASE / "hydroatlas_metadata.json"
    if not metadata_path.exists():
        metadata_path = Path(__file__).resolve().parents[1] / "paper/metadata/hydroatlas_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    fields = metadata["variables"]
    if metadata["schema_version"] != 1 or {v["name"] for v in fields} != set(attributes) - {"gauge_id"}:
        raise ValueError("Attribute metadata schema/columns do not match this release")
    keep = [v["name"] for v in fields if v["recommended_for_analysis"]]
    return attributes[["gauge_id", *keep]]


def load_discharge(observed_only: bool = True) -> xr.Dataset:
    """Discharge with gap-filled days (quality_flag == 1) masked when requested."""
    ds = open_release_dataset(RELEASE / "camels_ru_discharge.nc")
    ds = ds.assign_coords(gauge_id=ds["gauge_id"].astype(str))  # never an integer key
    if observed_only:
        keep = ds["quality_flag"] == 0
        ds["discharge_mm"] = ds["discharge_mm"].where(keep)
        ds["discharge_m3s"] = ds["discharge_m3s"].where(keep)
    return ds


def drop_low_grade_years(q: xr.DataArray, bad_grades: tuple[str, ...] = ("D", "F")) -> xr.DataArray:
    """Set every day of a hydrological year graded D or F to NaN (hydro-year N = Oct N-1 .. Sep N)."""
    grades = pd.read_csv(RELEASE / "camels_ru_year_grades.csv", dtype={"gauge_id": str}).set_index(
        "gauge_id"
    )
    time = pd.DatetimeIndex(q["time"].values)
    hydro_year = np.where(time.month >= 10, time.year + 1, time.year)
    mask = np.ones(q.shape, dtype=bool)
    gauges = list(q["gauge_id"].values)
    for year in grades.columns:
        bad = grades.index[grades[year].isin(bad_grades)]
        rows = [gauges.index(g) for g in bad if g in gauges]
        mask[np.ix_(rows, hydro_year == int(year))] = False
    return q.where(xr.DataArray(mask, coords=q.coords))


def main() -> None:
    """Print a small summary so the example is self-checking."""
    ds = load_discharge()
    q = drop_low_grade_years(ds["discharge_mm"])
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv", dtype={"gauge_id": str})
    grade_a = summary.loc[summary["overall_grade"] == "A", "gauge_id"]
    mean_q = q.sel(gauge_id=grade_a.values).mean("time").to_pandas()
    n_obs = int(ds["discharge_mm"].notnull().any("time").sum())
    print(f"gauges with any observed discharge: {n_obs}")  # noqa: T201
    print(f"grade A gauges: {len(grade_a)}; median mean daily runoff: {mean_q.median():.2f} mm/d")  # noqa: T201
    filled = ds["discharge_mm"].where(ds["quality_flag"] == 1)
    assert filled.isnull().all(), "gap-filled days must be masked"  # noqa: S101
    attributes = load_attributes()
    assert not any(c.endswith("_smj") for c in attributes), "invalid category means excluded"  # noqa: S101
    assert len(attributes.columns) == 278, "gauge_id plus 277 qualified/derived values"  # noqa: S101
    print(f"attribute rows: {len(attributes)}; retained value fields: {len(attributes.columns) - 1}")  # noqa: T201


if __name__ == "__main__":
    main()
