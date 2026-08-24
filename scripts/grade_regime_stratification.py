"""Grade composition by climate band (Sect. 4.1.2 grade--regime confound).

The A--F grade is built from flag frequency and completeness, and neither is
climatically neutral: flag base rates differ systematically by hydrological
regime. This script quantifies that, so the manuscript can state the bias
instead of leaving readers to discover it after filtering to grade A.

Two mechanisms show up separately in the output:

* near-continuous permafrost loses grade A to *completeness* (the winter-gap
  pattern of Sect. 4.1.1 -- mass moves into D and F);
* the dry, low-snow steppe loses it to *minor* flags, chiefly weak
  precipitation--discharge coupling (mass moves into B, not D or F).

Writes ``paper/tables/grade_regime.csv`` as the provenance CSV that
``verify_macros.py`` reads.

Run: ``pixi run python scripts/grade_regime_stratification.py``
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parent.parent
RELEASE = REPO / "release" / "CAMELS_RU_v1.0"
OUT = REPO / "paper" / "tables" / "grade_regime.csv"

# Bands are chosen to be interpretable, not tuned: permafrost-free / sporadic /
# discontinuous / near-continuous, and the snow-cover quartile-ish breaks.
BANDS: dict[str, tuple[str, list[float], list[str]]] = {
    "snow": (
        "snw_pc_uyr",
        [-0.001, 20, 35, 50, 100],
        ["< 20", "20 to 35", "35 to 50", r"$\geq$ 50"],
    ),
    "permafrost": (
        "prm_pc_use",
        [-0.001, 0, 20, 80, 100],
        ["0", "0 to 20", "20 to 80", r"$\geq$ 80"],
    ),
}

# Sect. 4.1.1 winter-gap definition: summer well observed, winter largely absent.
SUMMER_MONTHS = (6, 7, 8, 9)
WINTER_MONTHS = (12, 1, 2, 3)
SUMMER_MIN = 0.8
WINTER_MAX = 0.5


def winter_gap_flags() -> pd.DataFrame:
    """Recompute the Sect. 4.1.1 winter-gap gauges from the released discharge file."""
    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        present = ds["discharge_mm"].notnull().values
        months = pd.DatetimeIndex(ds["time"].values).month
        gauge_id = [str(g) for g in ds["gauge_id"].values]
    summer = present[:, np.isin(months, SUMMER_MONTHS)].mean(axis=1)
    winter = present[:, np.isin(months, WINTER_MONTHS)].mean(axis=1)
    return pd.DataFrame(
        {"gauge_id": gauge_id, "winter_gap": (summer > SUMMER_MIN) & (winter < WINTER_MAX)}
    )


def load() -> pd.DataFrame:
    """Join the graded gauges to their HydroATLAS climate attributes and winter-gap flag."""
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    summary["gauge_id"] = summary["gauge_id"].astype(str)
    attrs = pd.read_csv(RELEASE / "camels_ru_attributes.csv")
    attrs["gauge_id"] = attrs["gauge_id"].astype(str)
    df = summary.merge(attrs[["gauge_id", "snw_pc_uyr", "prm_pc_use"]], on="gauge_id", how="left")
    # Area-weighted HydroATLAS percentages overshoot 100 by a float ulp; clip so the
    # top band keeps its member instead of pd.cut dropping it as NaN.
    df["prm_pc_use"] = df["prm_pc_use"].clip(0, 100)
    return df.merge(winter_gap_flags(), on="gauge_id", how="left")


def main() -> None:
    """Tabulate grade composition per climate band and write the provenance CSV."""
    df = load()
    rows = []
    for name, (col, edges, labels) in BANDS.items():
        band = pd.cut(df[col], bins=edges, include_lowest=True, labels=labels)
        for label, grp in df.groupby(band, observed=True):
            rows.append(
                {
                    "gradient": name,
                    "band": label,
                    "n": len(grp),
                    "pct_A": 100 * (grp["overall_grade"] == "A").mean(),
                    "pct_B": 100 * (grp["overall_grade"] == "B").mean(),
                    "pct_DF": 100 * grp["overall_grade"].isin(["D", "F"]).mean(),
                    "pct_winter_gap": 100 * grp["winter_gap"].mean(),
                }
            )
    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)

    covered = out["n"].sum() // 2  # each gauge appears once per gradient
    print(out.round(1).to_string(index=False))
    print(f"\ncovered {covered} of {len(df)} graded gauges ({len(df) - covered} lack attributes)")
    print(f"network grade-A share {100 * (df['overall_grade'] == 'A').mean():.1f}%")
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
