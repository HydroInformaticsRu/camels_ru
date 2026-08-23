"""Renormalise HydroATLAS attributes that were scaled by ``area_fraction_used``.

Until 2026-08-23 ``HydroAtlasReader`` weighted polygon attributes by
intersection_area / catchment_area without renormalising, so every HydroATLAS
column equalled the true area-weighted mean times ``area_fraction_used``
(science-review Domain Expert CRITICAL-1). Because the weighted sum and the unit
corrections are linear, dividing each HydroATLAS column by ``area_fraction_used``
reproduces the fixed extraction exactly for polygons without no-data values.
The seven CAMELS-RU-derived columns are untouched.

Idempotence guard: the file is only rewritten while the soil-texture fraction sum
still correlates with ``area_fraction_used``; a renormalised file passes through unchanged.

Run: ``pixi run python scripts/renormalize_hydroatlas_attributes.py``
"""

from pathlib import Path
import shutil

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "data" / "CAMELS_RU" / "attributes" / "hydro_atlas_cis_camels.csv"
RELEASE = ROOT / "release" / "CAMELS_RU_v1.0" / "camels_ru_attributes.csv"
DERIVED = {
    "gauge_id",
    "ws_area",
    "acc",
    "height_bs",
    "lat",
    "lon",
    "area_fraction_used",
    "n_hydroatlas_polygons",
}
SOIL = ["cly_pc_uav", "slt_pc_uav", "snd_pc_uav"]


def renormalize(df: pd.DataFrame) -> pd.DataFrame:
    """Divide every HydroATLAS column by ``area_fraction_used``."""
    out = df.copy()
    cols = [c for c in df.columns if c not in DERIVED]
    out[cols] = df[cols].div(df["area_fraction_used"], axis=0)
    return out


def already_renormalized(df: pd.DataFrame) -> bool:
    """True when the soil-fraction sum no longer tracks coverage (r was 0.98 before the fix)."""
    soil_sum = df[SOIL].sum(axis=1)
    r = np.corrcoef(soil_sum, df["area_fraction_used"])[0, 1]
    return bool(abs(r) < 0.3)


def main() -> None:
    """Rewrite the upstream attribute CSV and its release copy."""
    df = pd.read_csv(UPSTREAM, dtype={"gauge_id": str})
    if already_renormalized(df):
        print("already renormalised; nothing to do")
        return
    backup = UPSTREAM.with_suffix(".pre_renorm_2026-08-23.csv")
    if not backup.exists():
        shutil.copy2(UPSTREAM, backup)
        print(f"backup -> {backup.name}")
    fixed = renormalize(df)
    before = df[SOIL].sum(axis=1)
    after = fixed[SOIL].sum(axis=1)
    print(f"soil-fraction sum: median {before.median():.2f} -> {after.median():.2f}")
    print(f"soil-fraction sum: min {before.min():.1f} -> {after.min():.1f}")
    frac = df["area_fraction_used"]
    n1, n5, n10 = (frac < 0.99).sum(), (frac < 0.95).sum(), (frac < 0.90).sum()
    print(f"rows rescaled by >1%: {n1}, >5%: {n5}, >10%: {n10}")
    assert already_renormalized(fixed)
    fixed.to_csv(UPSTREAM, index=False)
    fixed.to_csv(RELEASE, index=False)
    print(f"wrote {UPSTREAM.relative_to(ROOT)} and {RELEASE.relative_to(ROOT)} ({len(fixed)} rows)")


if __name__ == "__main__":
    main()
