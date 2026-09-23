"""Where the ERA5-Land minus MSWEP precipitation offset falls, by phase (Sect. 6.3).

Sect. 6.5 reports a +96 mm/yr basin-mean excess of ERA5-Land over MSWEP and selects
MSWEP partly on the grounds that it assimilates gauge observations. In a cold region
that argument needs care. Gauges undercatch solid precipitation, and although MSWEP v2
does correct systematic terrestrial bias, it infers that correction from river discharge
(Beck et al., 2019), which constrains the catchment total and not its rain/snow
partition. This script locates the offset in temperature space so the manuscript can say
which phase carries it.

Splitting the daily series at 0 degC using the released ERA5-Land air temperature shows
roughly half the annual offset landing on sub-freezing days that carry only about a
quarter of the MSWEP annual total -- a snowfall disagreement, not a uniform bias.

Writes ``paper/tables/precip_phase_partition.csv`` for verify_macros.py.

Run: ``pixi run python scripts/precip_phase_partition.py``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from utils.release_io import open_release_dataset

REPO = Path(__file__).resolve().parents[1]
RELEASE = REPO / "release" / "CAMELS_RU_v1.0"
OUT = REPO / "paper" / "tables" / "precip_phase_partition.csv"

DAYS_PER_YEAR = 365.25


def main() -> None:
    """Partition each precipitation product by air-temperature phase and write the table."""
    with open_release_dataset(RELEASE / "camels_ru_forcing.nc") as ds:
        temp = ds["temp_mean"].values
        products = {name: ds[f"precip_{name}"].values for name in ("mswep", "era5")}
        n_days = ds.sizes["time"]

    years = n_days / DAYS_PER_YEAR
    phases = {"sub_freezing": temp < 0, "above_freezing": temp >= 0}

    rows = []
    for name, precip in products.items():
        for phase, mask in phases.items():
            # nansum over the phase, then average across catchments: a per-catchment
            # annual total, not a total of averages.
            total = np.nanmean(np.nansum(np.where(mask, precip, 0.0), axis=1)) / years
            rows.append({"product": name, "phase": phase, "mm_per_year": total})
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    piv = df.pivot(index="product", columns="phase", values="mm_per_year")
    delta = piv.loc["era5"] - piv.loc["mswep"]
    mswep_total = piv.loc["mswep"].sum()
    print(piv.round(1).to_string())
    print(f"\nERA5-Land minus MSWEP, sub-freezing  : {delta['sub_freezing']:+.1f} mm/yr")
    print(f"ERA5-Land minus MSWEP, above-freezing: {delta['above_freezing']:+.1f} mm/yr")
    sub_share = 100 * piv.loc["mswep", "sub_freezing"] / mswep_total
    print(f"sub-freezing share of MSWEP total    : {sub_share:.0f}%")
    print(
        f"share of total offset that is sub-freezing: {100 * delta['sub_freezing'] / delta.sum():.0f}%"
    )
    print(f"\nwrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
