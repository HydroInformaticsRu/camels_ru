#!/usr/bin/env python3
"""Generate the Budyko consistency-check figure for §4.1.3.

Computes aridity index (PET/P) and evaporative index ((P-Q)/P) for every
eligible gauge under each of the three precipitation products
(ERA5-Land, MSWEP v2.8, GPCP v3.3), then plots each product
in its own Budyko panel with the water-limit, energy-limit, and Budyko
(1974) theoretical curves overlaid.

Output: paper/images/fig_budyko.png and, when present, paper/overleaf/images/fig_budyko.png

Inputs:
- release/CAMELS_RU_v1.0/camels_ru_discharge.nc  (Q, mm/d)
- data/CAMELS_RU/parsed_meteo/gleam/*.csv        (potential_evaporation, mm/d)
- data/CAMELS_RU/parsed_meteo/era5_land/*.csv    (prcp, mm/d)
- data/CAMELS_RU/parsed_meteo/mswep/*.csv        (precipitation, mm/d)
- data/CAMELS_RU/parsed_meteo/gpcp/*.csv         (precip, mm/d)
- release/CAMELS_RU_v1.0/camels_ru_boundaries.gpkg  (area filter < 50,000 km²)
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm.auto import tqdm
import xarray as xr

sys.path.append(str(Path(__file__).parent.parent))
from src.hydro.period_based_metrics import split_by_period  # noqa: E402
from src.utils.logger import setup_logger  # noqa: E402
from src.utils.paper_analysis_scope import (  # noqa: E402
    PAPER_ANALYSIS_EXCLUSION_NOTE,
    is_paper_analysis_excluded_gauge_id,
    paper_analysis_scope_summary,
)

log = setup_logger("BudykoFigure", log_file="logs/budyko_figure.log")

ROOT = Path(__file__).parent.parent

PRODUCTS = {
    # Corrected de-accumulated ERA5-Land precip; the era5_land copy over-accumulated
    # tp (~1.5x), inflating basin P.
    "ERA5-Land": {"dir": ROOT / "data/Russia/MeteoData/CamelsRU/era5land_tp_new", "col": "prcp"},
    "MSWEP": {"dir": ROOT / "data/CAMELS_RU/parsed_meteo/mswep", "col": "precipitation"},
    "GPCP": {"dir": ROOT / "data/CAMELS_RU/parsed_meteo/gpcp", "col": "precip"},
}
PET_DIR = ROOT / "data/CAMELS_RU/parsed_meteo/gleam"
PET_COL = "potential_evaporation"
OUT_PNG = ROOT / "paper/images/fig_budyko.png"
OVERLEAF_OUT_PNG = ROOT / "paper/overleaf/images/fig_budyko.png"


def _annual_ratios(
    discharge: pd.Series,
    precipitation: pd.Series,
    pet: pd.Series,
    min_periods: int = 5,
) -> tuple[float, float]:
    """Return (aridity, evaporative) as means of per-hydro-year ratios."""
    q_per = split_by_period(discharge, "hydrological", 10)
    p_per = split_by_period(precipitation, "hydrological", 10)
    pet_per = split_by_period(pet, "hydrological", 10)

    common = set(q_per) & set(p_per) & set(pet_per)
    if len(common) < min_periods:
        return np.nan, np.nan

    a, e = [], []
    for year in sorted(common):
        q = float(np.nansum(q_per[year]))
        p = float(np.nansum(p_per[year]))
        pe = float(np.nansum(pet_per[year]))
        if p > 0:
            a.append(pe / p)
            e.append((p - q) / p)

    if len(a) < min_periods:
        return np.nan, np.nan
    return float(np.nanmean(a)), float(np.nanmean(e))


def _gauge_record(
    gauge_id: str,
    discharge_values: np.ndarray,
    dates: pd.DatetimeIndex,
) -> list[dict]:
    """Compute Budyko indices for one gauge under all P products. Returns list of rows."""
    rows: list[dict] = []
    try:
        q = pd.Series(np.asarray(discharge_values, dtype=np.float64), index=dates, name="q").dropna()
        if len(q) < 365 * 5:
            return rows

        pet_path = PET_DIR / f"{gauge_id}.csv"
        if not pet_path.exists():
            return rows
        pet = (
            pd.read_csv(pet_path, index_col="date", parse_dates=True, usecols=["date", PET_COL])[PET_COL]
            .reindex(dates)
            .dropna()
        )
        if pet.empty:
            return rows

        for product, meta in PRODUCTS.items():
            p_path = Path(meta["dir"]) / f"{gauge_id}.csv"
            if not p_path.exists():
                continue
            p = (
                pd.read_csv(p_path, index_col="date", parse_dates=True, usecols=["date", meta["col"]])[
                    meta["col"]
                ]
                .reindex(dates)
                .dropna()
            )
            if p.empty:
                continue
            aridity, evaporative = _annual_ratios(q, p, pet)
            rows.append(
                {
                    "gauge_id": gauge_id,
                    "product": product,
                    "aridity_index": aridity,
                    "evaporative_index": evaporative,
                }
            )
    except Exception as exc:
        log.error(f"gauge {gauge_id}: {exc!r}")
    return rows


def _budyko_curve(aridity: np.ndarray) -> np.ndarray:
    """Budyko (1974) heuristic curve: E/P = sqrt(PET/P * tanh(P/PET) * (1 - exp(-PET/P)))."""
    with np.errstate(divide="ignore", invalid="ignore"):
        val = aridity * np.tanh(1.0 / aridity) * (1.0 - np.exp(-aridity))
    return np.sqrt(np.clip(val, 0.0, None))


def _plot(df: pd.DataFrame) -> None:
    """Render the Budyko check as one panel per precipitation product."""
    colors = {"ERA5-Land": "#EE6677", "MSWEP": "#4477AA", "GPCP": "#228833"}
    products = ["ERA5-Land", "MSWEP", "GPCP"]
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), sharey=True, constrained_layout=True)

    # Theoretical bounds in Budyko coordinates
    #   Water  limit: AET <= P     -> evap_index <= 1            (horizontal at y=1)
    #   Energy limit: AET <= PET   -> evap_index <= aridity      (45-degree y=x for x<1)
    #   Combined physical envelope: evap_index <= min(1, aridity)
    x = np.linspace(0.01, 5.0, 400)
    envelope_line = np.minimum(x, 1.0)
    water_line = np.ones_like(x)
    budyko = _budyko_curve(x)

    for ax, panel, product in zip(axes, "abc", products, strict=True):
        sub = df[df["product"] == product].dropna(subset=["aridity_index", "evaporative_index"])
        ax.plot(
            x,
            envelope_line,
            color="#AA2222",
            linestyle="--",
            linewidth=1.0,
            label="Physical envelope (AET ≤ min(PET, P))",
        )
        ax.plot(
            x, water_line, color="#333333", linestyle=":", linewidth=1.0, label="Water limit (AET ≤ P)"
        )
        ax.plot(x, budyko, color="#222222", linestyle="-", linewidth=1.2, label="Budyko (1974) curve")
        ax.scatter(
            sub["aridity_index"],
            sub["evaporative_index"],
            s=6,
            c=colors[product],
            alpha=0.5,
            edgecolors="none",
            zorder=2,
        )
        ax.set_title(f"({panel}) {product} (n={len(sub)})", fontsize=11, loc="left")
        ax.set_xlabel("Aridity index  PET / P", fontsize=11)
        ax.set_xlim(0, 3.5)
        ax.set_ylim(-0.3, 1.5)
        ax.axhline(0, color="#888888", linewidth=0.5)
        ax.axvline(1, color="#888888", linewidth=0.5, linestyle=":")
        ax.text(0.5, 1.38, "HUMID  (PET < P)", fontsize=7, color="#555555", ha="center")
        ax.text(2.2, 1.38, "ARID  (PET > P)", fontsize=7, color="#555555", ha="center")
        ax.grid(alpha=0.2, linestyle="--")

    axes[0].set_ylabel("Evaporative index  (P − Q) / P", fontsize=11)
    axes[0].text(0.04, 1.06, "above water limit (Q < 0)", fontsize=7, color="#AA2222")
    axes[0].text(0.04, -0.24, "below zero (Q > P)", fontsize=7, color="#AA2222")
    # Lower-right corner (very arid, low evaporative index) is empty for this humid domain.
    axes[0].legend(loc="lower right", fontsize=7, framealpha=0.9)

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    if OVERLEAF_OUT_PNG.parent.exists():
        fig.savefig(OVERLEAF_OUT_PNG, dpi=300, bbox_inches="tight")
    plt.close(fig)
    log.info(f"Saved {OUT_PNG}")
    if OVERLEAF_OUT_PNG.exists():
        log.info(f"Saved {OVERLEAF_OUT_PNG}")


def _summary_table(df: pd.DataFrame) -> None:
    """Log median indices and physical-limit violation rates per product.

    Budyko energy limit:  evap_index <= aridity_index  (AET <= PET)
    Budyko water limit:   evap_index <= 1              (AET <= P)
    Combined envelope:    evap_index <= min(1, aridity_index)
    """
    log.info("Budyko summary by P product:")
    log.info(
        "  energy limit = AET<=PET (evap > aridity in humid regime); water limit = AET<=P (evap > 1)"
    )
    for product in PRODUCTS:
        sub = df[df["product"] == product].dropna(subset=["aridity_index", "evaporative_index"])
        if sub.empty:
            continue
        n = len(sub)
        ai_med = sub["aridity_index"].median()
        ei_med = sub["evaporative_index"].median()
        # Energy limit: AET > PET, i.e. evap > aridity (relevant primarily in humid regime)
        above_energy = (sub["evaporative_index"] > sub["aridity_index"]).sum()
        # Water limit: evap > 1 (Q < 0; only ever true when discharge processing has issues)
        above_water = (sub["evaporative_index"] > 1.0).sum()
        # Combined envelope violation: above min(1, aridity)
        above_envelope = (sub["evaporative_index"] > np.minimum(sub["aridity_index"], 1.0)).sum()
        # Negative evaporative-index closure: mean annual (P-Q)/P < 0.
        closure_viol = (sub["evaporative_index"] < 0.0).sum()
        log.info(f"  {product:10s}  n={n:5d}  median PET/P={ai_med:.3f}  median (P-Q)/P={ei_med:.3f}")
        log.info(
            f"             energy>PET (AET>PET): {above_energy:4d} ({100 * above_energy / n:5.1f}%)  "
            f"water>P (AET>P): {above_water:4d} ({100 * above_water / n:5.1f}%)  "
            f"envelope: {above_envelope:4d} ({100 * above_envelope / n:5.1f}%)  "
            f"negative (P-Q)/P: {closure_viol:4d} ({100 * closure_viol / n:5.1f}%)"
        )


def main() -> None:
    """CLI entry point."""
    disch_path = ROOT / "release/CAMELS_RU_v1.0/camels_ru_discharge.nc"
    boundaries = ROOT / "release/CAMELS_RU_v1.0/camels_ru_boundaries.gpkg"

    log.info(f"Loading discharge from {disch_path}")
    ds = xr.open_dataset(disch_path)
    dvar = "discharge_mm"
    gauge_coord = "gauge_id" if "gauge_id" in ds.coords else "gauge"
    gauges = [str(g) for g in ds[gauge_coord].values]
    dates = pd.DatetimeIndex(ds["time"].values)
    discharge = ds[dvar].values

    ws = gpd.read_file(boundaries)[["gauge_id", "area_km2"]]
    ws["gauge_id"] = ws["gauge_id"].astype(str)
    small = set(ws.loc[ws["area_km2"] < 50_000, "gauge_id"])

    scope = paper_analysis_scope_summary(gauges)
    log.info(
        f"Paper-analysis gauge-ID scope: include {scope.n_included}, "
        f"exclude {scope.n_excluded} (ID length >= {scope.excluded_min_id_length})"
    )
    log.info(PAPER_ANALYSIS_EXCLUSION_NOTE)

    valid_idx = [
        i
        for i, g in enumerate(gauges)
        if not is_paper_analysis_excluded_gauge_id(g)
        and g in small
        and np.isfinite(discharge[i]).sum() >= 365 * 5
    ]
    log.info(f"{len(valid_idx)} gauges pass gauge-ID, area, and discharge-length filters")

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=12) as exe:
        futures = {
            exe.submit(_gauge_record, gauges[i], discharge[i], dates): gauges[i] for i in valid_idx
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Budyko"):
            results.extend(fut.result())

    df = pd.DataFrame(results)
    if df.empty:
        log.error("No rows produced — aborting")
        sys.exit(1)

    _summary_table(df)
    _plot(df)


if __name__ == "__main__":
    main()
