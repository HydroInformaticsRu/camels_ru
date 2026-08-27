#!/usr/bin/env python3
"""Generate the Budyko consistency-check figure and the forcing water-balance table (Sect. 6.3).

Computes the aridity index (PET/P) and evaporative index ((P-Q)/P) for every
non-anomalous signature gauge under each of the three released precipitation
products (ERA5-Land, MSWEP v2.8, GPCP), with the same paired-day, valid-year
convention as scripts/create_paper_signatures.py, so the MSWEP panel reproduces
the released aridity_index / evaporative_index columns exactly.

Outputs:
- paper/images/fig_budyko.pdf (+ paper/overleaf/images/fig_budyko.pdf when present)
- paper/tables/forcing_water_balance.csv (Table 7 columns; locked by scripts/verify_macros.py)

Inputs (release files only):
- release/CAMELS_RU_v1.0/camels_ru_discharge.nc   (discharge_mm)
- release/CAMELS_RU_v1.0/camels_ru_forcing.nc     (precip_era5, precip_mswep, precip_gpcp, pet)
- release/CAMELS_RU_v1.0/camels_ru_signatures.csv (gauge set: rows with is_anomalous == False)
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import shutil
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from tqdm.auto import tqdm
import xarray as xr

sys.path.append(str(Path(__file__).parent.parent))
from scripts.create_paper_signatures import (  # noqa: E402
    HYDRO_YEAR_WINDOW,
    _water_balance_ratios,
)
from src.utils.logger import setup_logger  # noqa: E402

log = setup_logger("BudykoFigure", log_file="logs/budyko_figure.log")

ROOT = Path(__file__).parent.parent
RELEASE = ROOT / "release/CAMELS_RU_v1.0"
PRODUCTS = {"ERA5-Land": "precip_era5", "MSWEP": "precip_mswep", "GPCP": "precip_gpcp"}
# Vector PDF (scatter figure, journal prefers vector for line art); CreationDate
# stripped so reruns are byte-identical and git-clean.
OUT_PNG = ROOT / "paper/images/fig_budyko.pdf"
OVERLEAF_OUT_PNG = ROOT / "paper/overleaf/images/fig_budyko.pdf"
OUT_TABLE = ROOT / "paper/tables/forcing_water_balance.csv"


def _gauge_record(
    gauge_id: str,
    discharge_values: np.ndarray,
    precip: dict[str, np.ndarray],
    pet_values: np.ndarray,
    dates: pd.DatetimeIndex,
) -> list[dict]:
    """Compute runoff ratio and Budyko indices for one gauge under all P products."""
    rows: list[dict] = []
    try:
        q = pd.Series(np.asarray(discharge_values, dtype=np.float64), index=dates)
        q = q[HYDRO_YEAR_WINDOW[0] : HYDRO_YEAR_WINDOW[1]]
        pet = pd.Series(np.asarray(pet_values, dtype=np.float64), index=dates)
        for product, values in precip.items():
            p = pd.Series(np.asarray(values, dtype=np.float64), index=dates)
            runoff_ratio, aridity, evaporative = _water_balance_ratios(q, p, pet)
            rows.append(
                {
                    "gauge_id": gauge_id,
                    "product": product,
                    "runoff_ratio": runoff_ratio,
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
    # ESSD editor pre-review font floor: this figure prints at \textwidth from a 13.5in-wide
    # source (~0.52x shrink), so text must start at >=16pt to clear 7pt in the final PDF.
    fs = 16
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), sharey=True, constrained_layout=True)

    # Theoretical bounds in Budyko coordinates
    #   Water  limit: AET <= P     -> evap_index <= 1            (horizontal at y=1;
    #                                 this is the y>=1 branch of the envelope below,
    #                                 so it is not drawn again as its own line)
    #   Energy limit: AET <= PET   -> evap_index <= aridity      (45-degree y=x for x<1)
    #   Combined physical envelope: evap_index <= min(1, aridity)
    x = np.linspace(0.01, 5.0, 400)
    envelope_line = np.minimum(x, 1.0)
    budyko = _budyko_curve(x)

    for ax, panel, product in zip(axes, "abc", products, strict=True):
        sub = df[df["product"] == product].dropna(subset=["aridity_index", "evaporative_index"])
        ax.plot(
            x,
            envelope_line,
            color="#AA2222",
            linestyle="--",
            linewidth=1.0,
            label="Physical envelope",
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
        ax.set_title(f"({panel}) {product} (n={len(sub)})", fontsize=fs, loc="left")
        ax.set_xlabel("Aridity index  PET / P", fontsize=fs)
        ax.set_xlim(0, 3.5)
        ax.set_ylim(-0.3, 1.5)
        ax.axhline(0, color="#888888", linewidth=0.5)
        ax.axvline(1, color="#888888", linewidth=0.5, linestyle=":")
        # Anchored away from the x=1 divider (not centered on fixed x positions) so the
        # two labels cannot collide once the font floor bump widens them; the humid zone
        # is only 1 aridity-unit wide, too narrow at floor size for a qualifier that
        # duplicates the x-axis label and the dotted divider, so it is dropped here.
        ax.text(0.95, 1.38, "HUMID", fontsize=fs, color="#555555", ha="right")
        ax.text(1.05, 1.38, "ARID", fontsize=fs, color="#555555", ha="left")
        ax.grid(alpha=0.2, linestyle="--")
        ax.tick_params(labelsize=fs)

    axes[0].set_ylabel("Evaporative index  (P − Q) / P", fontsize=fs, labelpad=10)
    axes[0].text(0.04, 1.06, "above water limit (Q < 0)", fontsize=fs, color="#AA2222")
    axes[0].text(0.04, -0.24, "below zero (Q > P)", fontsize=fs, color="#AA2222")
    # A within-panel legend wide enough to clear the font floor also spans most of this
    # narrow (3-panel) panel width, so any in-panel corner collides with one of the two
    # boundary annotations. Placed outside the axes instead (as in the gauge-network
    # figure's Koppen legend), which constrained_layout reserves dedicated space for.
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=2, fontsize=fs, framealpha=0.9)

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    # Save once and copy: two savefig(bbox_inches="tight") calls crop differently,
    # so the two image directories would never agree byte-for-byte.
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight", metadata={"CreationDate": None})
    if OVERLEAF_OUT_PNG.parent.exists():
        shutil.copy2(OUT_PNG, OVERLEAF_OUT_PNG)
    plt.close(fig)
    log.info(f"Saved {OUT_PNG}")
    if OVERLEAF_OUT_PNG.exists():
        log.info(f"Saved {OVERLEAF_OUT_PNG}")


def _summary_table(df: pd.DataFrame) -> None:
    """Write Table 7 (paper/tables/forcing_water_balance.csv) and log the violation rates.

    Budyko energy limit:  evap_index <= aridity_index  (AET <= PET)
    Budyko water limit:   evap_index <= 1              (AET <= P)
    Combined envelope:    evap_index <= min(1, aridity_index)
    """
    log.info("Budyko summary by P product:")
    log.info(
        "  energy limit = AET<=PET (evap > aridity in humid regime); water limit = AET<=P (evap > 1)"
    )
    table_rows: list[dict] = []
    for product in PRODUCTS:
        sub = df[df["product"] == product].dropna(subset=["aridity_index", "evaporative_index"])
        if sub.empty:
            continue
        n = len(sub)
        # Signed departure from the Budyko curve: negative = below (less evaporation than
        # the curve predicts for that aridity). Reported as a bulk fit metric alongside
        # the tail exceedances, so the table does not describe the distribution by its
        # extremes alone.
        departure = sub["evaporative_index"] - _budyko_curve(sub["aridity_index"].to_numpy())
        table_rows.append(
            {
                "product": product,
                "n_gauges": n,
                "median_runoff_ratio": float(sub["runoff_ratio"].median()),
                "runoff_ratio_gt_1_pct": float(100.0 * (sub["runoff_ratio"] > 1.0).mean()),
                "aet_wb_gt_pet_pct": float(
                    100.0 * (sub["evaporative_index"] > sub["aridity_index"]).mean()
                ),
                "below_budyko_pct": float(100.0 * (departure < 0.0).mean()),
                "median_budyko_departure": float(departure.median()),
            }
        )
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
    OUT_TABLE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(table_rows).to_csv(OUT_TABLE, index=False, float_format="%.6g")
    log.info(f"Saved {OUT_TABLE}")


def main() -> None:
    """CLI entry point."""
    ds = xr.open_dataset(RELEASE / "camels_ru_discharge.nc")
    gauge_coord = "gauge_id" if "gauge_id" in ds.coords else "gauge"
    gauges = [str(g) for g in ds[gauge_coord].values]
    dates = pd.DatetimeIndex(ds["time"].values)
    discharge = ds["discharge_mm"].values
    forcing = xr.open_dataset(RELEASE / "camels_ru_forcing.nc").reindex(gauge_id=gauges, time=dates)
    precip = {product: forcing[var].values for product, var in PRODUCTS.items()}
    pet_values = forcing["pet"].values

    sigs = pd.read_csv(RELEASE / "camels_ru_signatures.csv", dtype={"gauge_id": str})
    keep = set(sigs.loc[~sigs["is_anomalous"].astype(bool), "gauge_id"])
    valid_idx = [i for i, g in enumerate(gauges) if g in keep]
    log.info(f"{len(valid_idx)} non-anomalous signature gauges")

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=12) as exe:
        futures = {
            exe.submit(
                _gauge_record,
                gauges[i],
                discharge[i],
                {k: v[i] for k, v in precip.items()},
                pet_values[i],
                dates,
            ): gauges[i]
            for i in valid_idx
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
