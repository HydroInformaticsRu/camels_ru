"""Stage--discharge rank consistency for the dual-record gauges (Sect. 6.4).

The water-level records carry no A--F grade and no external reference, so they are
the least validated part of the release. This script supplies the one internal check
that is available: at a river gauge, stage and discharge are two measurements of the
same flow, related through the rating curve. That relation is monotonic, so a high
Spearman rank correlation between the two released series confirms that they were
transcribed onto the same gauge and the same days, and a low one localises a
transcription or pairing fault.

The check is deliberately weak on purpose -- it tests *ingestion consistency*, not
observational accuracy, exactly as the GRDC comparison of Sect. 6.1 does for
discharge. It cannot detect an error shared by both series at source.

Two conventions matter:

* Only days where *both* variables carry ``quality_flag == 0`` are used, so the
  gap fills and the 156 897 replaced zero-stage readings never enter the statistic.
* Under ice, backwater raises stage at a given discharge and the rating relation
  shifts seasonally, so the open-water months (May to October) are reported
  separately from the all-year figure. The open-water number is the headline.

Writes ``paper/tables/stage_discharge.csv`` as the provenance CSV that
``verify_macros.py`` reads.

Run: ``pixi run python scripts/stage_discharge_consistency.py``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import xarray as xr

from utils.release_io import open_release_dataset

REPO = Path(__file__).resolve().parent.parent
RELEASE = REPO / "release" / "CAMELS_RU_v1.0"
OUT = REPO / "paper" / "tables" / "stage_discharge.csv"
FLAG_OUT = REPO / "data" / "CAMELS_RU" / "HydroData" / "stage_discharge_screen.nc"

OPEN_WATER_MONTHS = (5, 6, 7, 8, 9, 10)
MIN_PAIRED_DAYS = 365  # one full year of jointly observed days
STRONG = 0.9  # rho at or above this is an unambiguous rating relation
WEAK = 0.5  # rho below this warrants inspection


def load_pairs() -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray, np.ndarray]:
    """Return observed-only discharge and stage matrices plus the gauge and month axes."""
    with open_release_dataset(RELEASE / "camels_ru_discharge.nc") as dq:
        q = dq["discharge_m3s"].values.astype(float)
        q_obs = dq["quality_flag"].values == 0
        gauge_id = [str(g) for g in dq["gauge_id"].values]
        months = pd.DatetimeIndex(dq["time"].values).month.to_numpy()
    with open_release_dataset(RELEASE / "camels_ru_water_level.nc") as dh:
        h = dh["water_level_cm"].values.astype(float)
        h_obs = dh["quality_flag"].values == 0
        gauge_type = dh["gauge_type"].values

    # Mask everything that is not a genuine observation in BOTH series.
    paired = q_obs & h_obs & np.isfinite(q) & np.isfinite(h)
    return q, h, gauge_id, months, paired, gauge_type


def rho_for(q_row: np.ndarray, h_row: np.ndarray, mask: np.ndarray) -> tuple[float, int]:
    """Spearman rho between stage and discharge over the masked days."""
    n = int(mask.sum())
    if n < MIN_PAIRED_DAYS:
        return (np.nan, n)
    # A constant series makes Spearman undefined; report NaN rather than a spurious 0.
    if np.ptp(q_row[mask]) == 0 or np.ptp(h_row[mask]) == 0:
        return (np.nan, n)
    return (float(spearmanr(q_row[mask], h_row[mask]).statistic), n)


def write_flag(df: pd.DataFrame, gauge_id: list[str]) -> None:
    """Write the per-gauge release flag consumed by ``package_dataset.package_water_level``.

    Encodes the open-water rank correlation as a three-class screen rather than
    shipping rho itself, so the variable stays a usage screen and not a statistic
    users are tempted to interpret as an accuracy measure:

    -1 not assessed (fewer than one year of jointly observed days, or no record)
     0 consistent   (rho >= WEAK: stage rises with discharge, as the rating requires)
     1 inconsistent (rho < WEAK, including the inverted gauges)
    """
    rho = df.set_index("gauge_id")["rho_open_water"]
    flag = np.full(len(gauge_id), -1, dtype=np.int8)
    for i, gid in enumerate(gauge_id):
        value = rho.get(gid, np.nan)
        if np.isfinite(value):
            flag[i] = 0 if value >= WEAK else 1
    xr.DataArray(
        flag, dims=["gauge_id"], coords={"gauge_id": gauge_id}, name="stage_discharge_screen"
    ).to_dataset().to_netcdf(FLAG_OUT)
    print(f"flag: {int((flag == 1).sum())} inconsistent, {int((flag == 0).sum())} consistent")
    print(f"wrote {FLAG_OUT}")


def main() -> None:
    """Compute per-gauge stage--discharge rank correlations and write the provenance CSV."""
    q, h, gauge_id, months, paired, gauge_type = load_pairs()
    open_water = np.isin(months, OPEN_WATER_MONTHS)

    rows = []
    for i, gid in enumerate(gauge_id):
        if not paired[i].any():
            continue
        rho_all, n_all = rho_for(q[i], h[i], paired[i])
        rho_ow, n_ow = rho_for(q[i], h[i], paired[i] & open_water)
        rows.append(
            {
                "gauge_id": gid,
                "gauge_type": int(gauge_type[i]),
                "n_paired": n_all,
                "rho_all": rho_all,
                "n_paired_open_water": n_ow,
                "rho_open_water": rho_ow,
            }
        )
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    write_flag(df, gauge_id)

    river = df[df["gauge_type"] == 0]
    ow = river["rho_open_water"].dropna()
    allyr = river["rho_all"].dropna()
    print(f"dual-record gauges with >= {MIN_PAIRED_DAYS} paired observed days: {len(ow)}")
    print(f"  open-water median rho {ow.median():.3f}   all-year median rho {allyr.median():.3f}")
    print(f"  open-water rho >= {STRONG}: {100 * (ow >= STRONG).mean():.1f}%")
    print(f"  open-water rho >= 0.8   : {100 * (ow >= 0.8).mean():.1f}%")
    print(f"  open-water rho <  {WEAK} : {(ow < WEAK).sum()} gauges")
    print(f"  reservoir/hydropower gauges excluded: {(df['gauge_type'] == 1).sum()}")
    weak = river.loc[river["rho_open_water"] < WEAK, ["gauge_id", "rho_open_water", "n_paired"]]
    if not weak.empty:
        print("\nweakest gauges (inspect):")
        print(weak.sort_values("rho_open_water").head(15).to_string(index=False))
    print(f"\nwrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
