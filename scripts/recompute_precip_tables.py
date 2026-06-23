#!/usr/bin/env python3
"""Recompute the two manuscript precipitation tables on the corrected ERA5-Land precip.

The original tables were produced by ``notebooks/03_ForcingsFinal.py`` from the
over-accumulated ERA5-Land copy (``CamelsRU/era5_land``); this standalone script
reproduces the notebook's exact definitions but reads the corrected,
de-accumulated source (``CamelsRU/era5land_tp_new``) and writes both tables
without running the (heavy, figure-producing) notebook:

- ``paper/tables/precip_dataset_comparison.csv`` (Table 1: spatial mean / std /
  mean-CV of mean-annual precip per product)
- ``paper/tables/precip_inter_dataset_corr.csv`` (Table 2: daily inter-dataset
  Pearson r + bias per product pair)

Two deliberate conventions (see manuscript correction notes):

* Table 1 uses a single unified analysis end (2023-12-31) for all three
  products, matching ``scripts/recompute_forcing_numbers.py``. The notebook's
  ``PERIOD_END_GPCP=2021-09-30`` was a stale GPCP-coverage assumption; GPCP v3.3
  has real coverage to 2023-12-31.
* Table 2 keeps the notebook's ``COMMON_END=2021-09-30`` so the MSWEP-vs-GPCP
  daily correlation (which does not involve ERA5) reproduces identically and
  serves as a validation anchor; only the ERA5-involving pairs move, isolating
  the de-accumulation effect from any window change.

Usage:
    pixi run python scripts/recompute_precip_tables.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.paper_analysis_scope import paper_analysis_inclusion_mask  # noqa: E402

# ── Periods ───────────────────────────────────────────────────────────────────
PERIOD_START = "2008-01-01"
# Table 1: unified end for every product (GPCP v3.3 has real coverage to 2023).
ANNUAL_END = "2023-12-31"
# Table 2: notebook's GPCP-limited common window, kept so MSWEP-vs-GPCP is an anchor.
CORR_END = "2021-09-30"

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA = ROOT / "data"
PARSED_METEO = DATA / "CAMELS_RU" / "parsed_meteo"
# Corrected de-accumulated ERA5-Land precip; era5_land over-accumulated tp (~1.5x).
ERA5_DIR = DATA / "Russia" / "MeteoData" / "CamelsRU" / "era5land_tp_new"
MSWEP_DIR = PARSED_METEO / "mswep"
GPCP_DIR = PARSED_METEO / "gpcp"
GEOM_GAUGES = DATA / "CAMELS_RU" / "geometry" / "camels_gauges.gpkg"
TABLE_DIR = ROOT / "paper" / "tables"

PRECIP_COL = {"era5": "prcp", "mswep": "precipitation", "gpcp": "precip"}
PRODUCT_LABEL = {"era5": "ERA5-Land", "mswep": "MSWEP", "gpcp": "GPCP"}
PAIRS = [
    ("era5", "mswep", "ERA5-Land vs MSWEP"),
    ("era5", "gpcp", "ERA5-Land vs GPCP"),
    ("mswep", "gpcp", "MSWEP vs GPCP"),
]


def load_csv_series(path: Path, value_col: str, date_col: str = "date") -> pd.Series | None:
    """Load a single daily series from CSV, or None if missing/unreadable/no column."""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, index_col=date_col, parse_dates=True)
    except Exception:  # noqa: BLE001
        return None
    if value_col not in df.columns:
        return None
    return pd.Series(df[value_col])


def annual_mean_precip(series: pd.Series, end_date: str) -> float:
    """Mean of calendar-year precip totals (mm/yr); NaN if < 365 daily records."""
    sub = series.loc[PERIOD_START:end_date]
    if len(sub) < 365:
        return np.nan
    return float(sub.resample("YE").sum().mean())


def annual_cv_precip(series: pd.Series, end_date: str) -> float:
    """CV of calendar-year precip totals; NaN if < 365 records or zero mean."""
    sub = series.loc[PERIOD_START:end_date]
    if len(sub) < 365:
        return np.nan
    annual = sub.resample("YE").sum()
    return float(annual.std() / annual.mean()) if annual.mean() > 0 else np.nan


def load_paper_gauge_ids() -> list[str]:
    """Return the paper-analysis gauge universe (ID length < 7) from camels_gauges.gpkg."""
    gdf = gpd.read_file(GEOM_GAUGES).set_index("gauge_id")
    gdf.index = gdf.index.astype(str)
    mask = paper_analysis_inclusion_mask(gdf.index)
    return gdf.index[mask.to_numpy()].tolist()


def load_precip(gauge_ids: list[str]) -> dict[str, dict[str, pd.Series]]:
    """Load ERA5/MSWEP/GPCP daily series per gauge (available products only)."""
    dirs = {"era5": ERA5_DIR, "mswep": MSWEP_DIR, "gpcp": GPCP_DIR}
    out: dict[str, dict[str, pd.Series]] = {}
    for gid in gauge_ids:
        out[gid] = {}
        for product, base in dirs.items():
            s = load_csv_series(base / f"{gid}.csv", PRECIP_COL[product])
            if s is not None:
                out[gid][product] = s
    return out


def build_table1(precip: dict[str, dict[str, pd.Series]], n_total: int) -> pd.DataFrame:
    """Table 1: spatial mean / std / mean-CV of mean-annual precip per product."""
    rows: list[dict[str, object]] = []
    for product in ("era5", "mswep", "gpcp"):
        means: list[float] = []
        cvs: list[float] = []
        n_avail = 0
        for products in precip.values():
            if product not in products:
                continue
            n_avail += 1
            m = annual_mean_precip(products[product], ANNUAL_END)
            c = annual_cv_precip(products[product], ANNUAL_END)
            if not np.isnan(m):
                means.append(m)
            if not np.isnan(c):
                cvs.append(c)
        ann = pd.Series(means, dtype=float)
        cv = pd.Series(cvs, dtype=float)
        rows.append(
            {
                "Dataset": PRODUCT_LABEL[product],
                "N gauges": n_avail,
                "Coverage (%)": f"{100 * n_avail / n_total:.1f}",
                "Mean annual P (mm/yr)": f"{ann.mean():.0f}" if len(ann) else "—",
                "Std annual P (mm/yr)": f"{ann.std():.0f}" if len(ann) else "—",
                "Mean CV": f"{cv.mean():.2f}" if len(cv) else "—",
            }
        )
    return pd.DataFrame(rows)


def build_table2(precip: dict[str, dict[str, pd.Series]]) -> pd.DataFrame:
    """Table 2: daily inter-dataset Pearson r + bias per product pair (to CORR_END)."""
    per_pair: dict[str, dict[str, list[float]]] = {label: {"r": [], "bias": []} for _, _, label in PAIRS}
    for products in precip.values():
        for ds_a, ds_b, label in PAIRS:
            if ds_a not in products or ds_b not in products:
                continue
            a = products[ds_a].loc[PERIOD_START:CORR_END]
            b = products[ds_b].loc[PERIOD_START:CORR_END]
            common = a.index.intersection(b.index)
            if len(common) < 365:
                continue
            per_pair[label]["r"].append(float(a.loc[common].corr(b.loc[common])))
            per_pair[label]["bias"].append(float(a.loc[common].mean() - b.loc[common].mean()))

    rows: list[dict[str, object]] = []
    for _, _, label in PAIRS:
        r_vals = pd.Series(per_pair[label]["r"], dtype=float)
        bias_vals = pd.Series(per_pair[label]["bias"], dtype=float)
        rows.append(
            {
                "Comparison": label,
                "N gauges": int(len(r_vals)),
                "Mean r": f"{r_vals.mean():.3f}" if len(r_vals) else "—",
                "Median r": f"{r_vals.median():.3f}" if len(r_vals) else "—",
                "Std r": f"{r_vals.std():.3f}" if len(r_vals) else "—",
                "Mean bias (mm/day)": f"{bias_vals.mean():.3f}" if len(bias_vals) else "—",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    """Recompute both precip tables on corrected ERA5 and write them to paper/tables/."""
    gauge_ids = load_paper_gauge_ids()
    precip = load_precip(gauge_ids)
    n_total = len(gauge_ids)
    print(f"Paper-analysis gauge universe: {n_total}")

    table1 = build_table1(precip, n_total)
    table2 = build_table2(precip)

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    out1 = TABLE_DIR / "precip_dataset_comparison.csv"
    out2 = TABLE_DIR / "precip_inter_dataset_corr.csv"
    table1.to_csv(out1, index=False)
    table2.to_csv(out2, index=False)

    print(f"\nTable 1: Precipitation Dataset Comparison (annual to {ANNUAL_END})")
    print(table1.to_string(index=False))
    print(f"\nTable 2: Inter-Dataset Correlations (daily, {PERIOD_START}..{CORR_END})")
    print(table2.to_string(index=False))
    print(f"\nWrote {out1.relative_to(ROOT)}")
    print(f"Wrote {out2.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
