"""Sensitivity of the two fixed ice-season windows to a temperature-derived variant.

Two release conventions use a fixed calendar window across 32 degrees of latitude:

* the ``constant_value`` exemption treats runs of identical observations as the
  under-ice reporting convention when >= 80 % of the run falls in November-April
  (``src/quality/anomaly_detection.py``);
* the stage--discharge screen reports its headline rank correlation over the
  May-October open-water months (``scripts/stage_discharge_consistency.py``).

This script quantifies both choices against per-gauge alternatives derived from
the released ``temp_mean`` (Sect. 4.1.1 and Sect. 6.3 of the manuscript): the
constant-run exemption under a per-gauge freezing climatology, and the screen
under a stricter June-September window. Writes the provenance CSV
``paper/tables/ice_window_sensitivity.csv`` that ``verify_macros.py`` gates.

Run: ``pixi run python scripts/ice_window_sensitivity.py``
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import xarray as xr

REPO = Path(__file__).resolve().parent.parent
RELEASE = REPO / "release" / "CAMELS_RU_v1.0"
OUT = REPO / "paper" / "tables" / "ice_window_sensitivity.csv"

CONST_MIN_RUN = 30
CONST_TOLERANCE = 1e-6
ICE_RUN_FRACTION = 0.8
MIN_PAIRED_DAYS = 365
WEAK_RHO = 0.5


def _constant_runs(x: np.ndarray) -> list[slice]:
    """Calendar-index spans of runs of >= CONST_MIN_RUN identical observations."""
    obs_idx = np.where(~np.isnan(x))[0]
    if len(obs_idx) < CONST_MIN_RUN:
        return []
    same = np.abs(np.diff(x[obs_idx])) <= CONST_TOLERANCE
    spans = []
    j = 0
    while j < len(same):
        if not same[j]:
            j += 1
            continue
        k = j
        while k < len(same) and same[k]:
            k += 1
        if k - j + 1 >= CONST_MIN_RUN:
            spans.append(slice(obs_idx[j], obs_idx[k] + 1))
        j = k
    return spans


def constant_run_sensitivity() -> dict[str, int]:
    """Constant-value exemption: fixed Nov-Apr window vs per-gauge freezing window."""
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        q = ds["discharge_mm"].transpose("gauge_id", "time").values
        times = pd.DatetimeIndex(ds["time"].values)
    with xr.open_dataset(RELEASE / "camels_ru_forcing.nc") as fx:
        t = fx["temp_mean"].transpose("gauge_id", "time").values

    doy = times.dayofyear.to_numpy()
    fixed_ice = np.isin(times.month.to_numpy(), (11, 12, 1, 2, 3, 4))

    n_g = q.shape[0]
    frz_doy = np.zeros((n_g, 367), dtype=bool)
    for d in range(1, 367):
        m = doy == d
        if m.any():
            with np.errstate(invalid="ignore"):
                frz_doy[:, d] = np.nanmean(t[:, m], axis=1) < 0.0
    derived_ice = frz_doy[:, doy]

    flagged_fixed: set[int] = set()
    flagged_derived: set[int] = set()
    for i in range(n_g):
        for span in _constant_runs(q[i]):
            if fixed_ice[span].mean() < ICE_RUN_FRACTION:
                flagged_fixed.add(i)
            if derived_ice[i, span].mean() < ICE_RUN_FRACTION:
                flagged_derived.add(i)
    return {
        "n_const_flagged_fixed": len(flagged_fixed),
        "n_const_exempt_derived": len(flagged_fixed - flagged_derived),
        "n_const_new_derived": len(flagged_derived - flagged_fixed),
    }


def stage_window_sensitivity() -> dict[str, int]:
    """Stage--discharge screen: weak-gauge count under May-Oct vs June-September."""
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as dq:
        q = dq["discharge_m3s"].values.astype(float)
        q_obs = dq["quality_flag"].values == 0
        months = pd.DatetimeIndex(dq["time"].values).month.to_numpy()
    with xr.open_dataset(RELEASE / "camels_ru_water_level.nc") as dh:
        h = dh["water_level_cm"].values.astype(float)
        h_obs = dh["quality_flag"].values == 0
        gtype = dh["gauge_type"].values

    paired = q_obs & h_obs & np.isfinite(q) & np.isfinite(h)
    windows = {
        "may_oct": np.isin(months, (5, 6, 7, 8, 9, 10)),
        "jun_sep": np.isin(months, (6, 7, 8, 9)),
    }
    weak = dict.fromkeys(windows, 0)
    for i in range(q.shape[0]):
        if gtype[i] != 0:
            continue
        for key, win in windows.items():
            m = paired[i] & win
            if int(m.sum()) < MIN_PAIRED_DAYS or np.ptp(q[i][m]) == 0 or np.ptp(h[i][m]) == 0:
                continue
            if float(spearmanr(q[i][m], h[i][m]).statistic) < WEAK_RHO:
                weak[key] += 1
    return {"n_stage_weak_may_oct": weak["may_oct"], "n_stage_weak_jun_sep": weak["jun_sep"]}


def main() -> None:
    """Compute both sensitivities and write the provenance CSV."""
    row = constant_run_sensitivity() | stage_window_sensitivity()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(OUT, index=False)
    for k, v in row.items():
        print(f"{k}: {v}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
