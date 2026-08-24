"""Quantify the two-branch forcing aggregation (Sect. 4.2): weighted vs touched-cell mean.

Catchments below ``SMALL_WATERSHED_THRESHOLD_KM2`` (150 km²) are aggregated with
fractional-area weights; larger ones with an unweighted mean over every 0.1° cell that
touches the boundary. This script re-aggregates one calendar year of MSWEP precipitation
and ERA5-Land air temperature for a random sample of Analysis-set catchments in three area
bands with BOTH branches and reports the difference, so the manuscript can state the size of
the edge effect instead of asserting that it is negligible.

Writes ``paper/tables/aggregation_sensitivity.csv`` (one row per band), which
``scripts/verify_macros.py`` locks to the manuscript macros.

Run: pixi run python scripts/aggregation_sensitivity.py [--year 2015] [--n 100] [--seed 1996]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.meteo.aggregation import aggregate_watershed  # noqa: E402
from src.utils.paper_analysis_scope import paper_analysis_inclusion_mask  # noqa: E402

GEOM = ROOT / "data" / "CAMELS_RU" / "geometry" / "camels_watersheds.gpkg"
GRIDS = ROOT / "data" / "Russia" / "MeteoData" / "ParsedMonthly"
OUT = ROOT / "paper" / "tables" / "aggregation_sensitivity.csv"
# The top band is open-ended: 1391 catchments (41.5 % of the network) exceed 5000 km2,
# and that is where the unweighted touched-cell mean is most exposed, since a basin
# spanning many degrees of latitude has the widest spread of true cell areas.
BANDS = [(5, 150), (150, 500), (500, 1000), (1000, 5000), (5000, float("inf"))]
PRODUCTS = {"mswep": ("mswep", "precipitation"), "era5_land": ("era5_land", "t_mean")}


def _annual(gid: str, geom, product: str, var: str, year: int, weighted: bool) -> float:
    """Annual mean of ``var`` for one catchment with the chosen branch."""
    # small_ws_threshold means "catchments SMALLER than this use fractional weights", so
    # inf forces the weighted branch and 0 forces the touched-cell mean. The unweighted
    # case must be 0, not 150: with 150 every catchment in the 5-150 band would fall
    # below the threshold and be weighted, making both arms of the comparison identical.
    threshold = float("inf") if weighted else 0.0
    parts = []
    for month in range(1, 13):
        df = aggregate_watershed(
            GRIDS / product / f"{year}_{month:02d}.nc",
            geom,
            gid,
            product,
            small_ws_threshold=threshold,
            variables=[var],
        )
        parts.append(df[var])
    return float(pd.concat(parts).mean())


def main() -> None:
    """Sample catchments per band, aggregate both ways, write the summary table."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2015)
    ap.add_argument("--n", type=int, default=60, help="catchments per band")
    ap.add_argument("--seed", type=int, default=1996)
    args = ap.parse_args()

    ws = gpd.read_file(GEOM)
    ws["gauge_id"] = ws["gauge_id"].astype(str)
    ws = ws[paper_analysis_inclusion_mask(ws["gauge_id"]).to_numpy()]
    rng = np.random.default_rng(args.seed)
    rows = []
    for lo, hi in BANDS:
        band = ws[(ws["area_km2"] >= lo) & (ws["area_km2"] < hi)]
        sample = band.sample(min(args.n, len(band)), random_state=int(rng.integers(1 << 31)))
        label = f"{lo}+" if hi == float("inf") else f"{lo}-{hi}"
        rec = {"band_km2": label, "n_band": len(band), "n_sample": len(sample)}
        for key, (product, var) in PRODUCTS.items():
            w, u = [], []
            for gid, geom in zip(sample["gauge_id"], sample["geometry"], strict=True):
                w.append(_annual(gid, geom, product, var, args.year, weighted=True))
                u.append(_annual(gid, geom, product, var, args.year, weighted=False))
            w, u = np.array(w), np.array(u)
            if key == "mswep":
                rel = 100.0 * (u - w) / w
                rec["p_median_abs_rel_pct"] = float(np.median(np.abs(rel)))
                rec["p_p90_abs_rel_pct"] = float(np.percentile(np.abs(rel), 90))
                rec["p_median_rel_pct"] = float(np.median(rel))
            else:
                d = u - w
                rec["t_median_abs_degc"] = float(np.median(np.abs(d)))
                rec["t_p90_abs_degc"] = float(np.percentile(np.abs(d), 90))
                rec["t_median_degc"] = float(np.median(d))
        rows.append(rec)
        print(rec)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
