"""Nested mass-balance consistency check (Sect. 6.5).

Where one gauge sits inside another gauge's catchment, the downstream record must carry
at least as much water as the upstream one over any period both observe. This is the only
validation available to CAMELS-RU that is independent of any external archive, and it
covers far more gauges than the GRDC cross-check of Sect. 6.1.

Original claim (2026-08-24 domain review): joining gauge coordinates into catchment
polygons yields ~6805 nested gauge pairs with >=2000 common observed days, and the
downstream total volume exceeds the upstream total in 99.4 % of them.

Nesting is established geometrically (upstream gauge point inside the downstream
polygon, downstream area strictly larger), and the comparison uses discharge_m3s on
days observed at BOTH gauges, so a gap at either end never creates a false violation.
"""

from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
RELEASE = REPO / "release" / "CAMELS_RU_v1.0"
PAIRS_CSV = REPO / "paper" / "tables" / "nested_mass_balance.csv"
STRAT_CSV = REPO / "paper" / "tables" / "nested_stratification.csv"
STRAT_TEX = REPO / "paper" / "overleaf" / "tables" / "nested_stratification.tex"
MIN_COMMON_DAYS = 2000
RATIO_BANDS = [(0.0, 2.0, r"$\le 2$"), (2.0, 5.0, "2 to 5"), (5.0, np.inf, "$> 5$")]

TABLE_HEADER = r"""\begin{table}[t]
\centering
\caption{Nested mass-balance check stratified by the downstream-to-upstream area ratio,
over the \nnestedpairs{} pairs with at least 2000 jointly observed days. The check's power
falls as the ratio grows, because a much larger downstream catchment exceeds the upstream
volume almost by construction; the near-nested pairs in the first row are where a
violation is easiest to produce. Shares are rounded independently and need not sum to
100. Per-pair results ship in \texttt{paper/tables/nested\_mass\_balance.csv}.}
\label{tab:nested_stratification}
\small
\begin{tabular}{@{}lrrrr@{}}
\toprule
Area ratio $A_{dn}/A_{up}$ & Pairs & Share & Violations & Failure rate \\
\midrule
"""

TABLE_FOOTER = r"""\bottomrule
\end{tabular}
\end{table}
"""


def write_stratified(df: pd.DataFrame) -> None:
    """Write the area-ratio stratification (CSV + generated LaTeX table).

    Generated rather than typed for the same reason as the grade-regime table:
    hand-transcribed cells drift.
    """
    fail = df["v_ratio"] <= 1
    rows = []
    for lo, hi, label in RATIO_BANDS:
        m = (df["area_ratio"] > lo) & (df["area_ratio"] <= hi)
        rows.append(
            {
                "band": label,
                "n_pairs": int(m.sum()),
                "share_pct": 100.0 * m.mean(),
                "n_violations": int(fail[m].sum()),
                "fail_pct": 100.0 * fail[m].mean(),
            }
        )
    rows.append(
        {
            "band": "All",
            "n_pairs": len(df),
            "share_pct": 100.0,
            "n_violations": int(fail.sum()),
            "fail_pct": 100.0 * fail.mean(),
        }
    )
    out = pd.DataFrame(rows)
    out.to_csv(STRAT_CSV, index=False, float_format="%.6g")
    print(f"wrote {STRAT_CSV.relative_to(REPO)}")

    lines = [TABLE_HEADER]
    for _, r in out.iterrows():
        lines.append(
            f"{r['band']} & {r['n_pairs']} & {r['share_pct']:.1f}\\% & "
            f"{r['n_violations']} & {r['fail_pct']:.1f}\\% \\\\\n"
        )
    lines.append(TABLE_FOOTER)
    STRAT_TEX.write_text("".join(lines))
    print(f"wrote {STRAT_TEX.relative_to(REPO)}")


def main() -> None:
    """Reproduce the nested-pair count and the downstream-exceeds-upstream share."""
    poly = gpd.read_file(RELEASE / "camels_ru_boundaries.gpkg")[["gauge_id", "area_km2", "geometry"]]
    poly["gauge_id"] = poly["gauge_id"].astype(str)
    print(f"polygons {len(poly)}  crs {poly.crs}")

    with xr.open_dataset(RELEASE / "camels_ru_discharge.nc") as ds:
        ids = [str(g) for g in ds["gauge_id"].values]
        q = ds["discharge_m3s"].values
    has_q = np.isfinite(q).any(axis=1)
    keep = {g for g, h in zip(ids, has_q, strict=True) if h}
    pos = {g: i for i, g in enumerate(ids)}
    print(f"gauges with discharge {len(keep)}")

    # Gauge locations: the attribute table carries lat/lon per gauge.
    attrs = pd.read_csv(RELEASE / "camels_ru_attributes.csv", usecols=["gauge_id", "lat", "lon"])
    attrs["gauge_id"] = attrs["gauge_id"].astype(str)
    attrs = attrs[attrs["gauge_id"].isin(keep)]
    pts = gpd.GeoDataFrame(
        attrs,
        geometry=gpd.points_from_xy(attrs["lon"], attrs["lat"]),
        crs=poly.crs,  # same CRS as the polygons -- do not assume, take it
    )
    print(f"gauge points {len(pts)}  crs {pts.crs}")

    joined = gpd.sjoin(pts, poly, predicate="within", how="inner")
    joined = joined.rename(columns={"gauge_id_left": "up", "gauge_id_right": "down"})
    pairs = joined[joined["up"] != joined["down"]][["up", "down", "area_km2"]]
    up_area = poly.set_index("gauge_id")["area_km2"]
    pairs = pairs.assign(area_up=pairs["up"].map(up_area))
    pairs = pairs[pairs["area_km2"] > pairs["area_up"]]  # strictly larger downstream
    pairs = pairs[pairs["down"].isin(keep)]
    print(f"nested pairs (both gauged, downstream larger): {len(pairs)}")

    rows = []
    for up, down, a_dn, a_up in pairs.itertuples(index=False):
        qu, qd = q[pos[up]], q[pos[down]]
        both = np.isfinite(qu) & np.isfinite(qd)
        n = int(both.sum())
        if n < MIN_COMMON_DAYS:
            continue
        v_up, v_dn = float(qu[both].sum()), float(qd[both].sum())
        rows.append(
            {
                "up": up,
                "down": down,
                "n_common": n,
                "area_up": a_up,
                "area_dn": a_dn,
                "area_ratio": a_dn / a_up,
                "v_ratio": v_dn / v_up if v_up > 0 else np.nan,
            }
        )
    df = pd.DataFrame(rows)
    print(f"\npairs with >= {MIN_COMMON_DAYS} common observed days: {len(df)}")
    ok = df["v_ratio"] > 1
    print(f"downstream volume exceeds upstream: {ok.sum()} ({100 * ok.mean():.2f} %)")
    print(f"violations: {(~ok).sum()}")

    bad = df[~ok].sort_values("v_ratio")
    print(f"  of which area ratio > 2 (not explainable by noise): {(bad['area_ratio'] > 2).sum()}")
    summary = pd.read_csv(RELEASE / "camels_ru_gauge_summary.csv")
    summary["gauge_id"] = summary["gauge_id"].astype(str)
    grade = summary.set_index("gauge_id")["overall_grade"]
    bad = bad.assign(grade_up=bad["up"].map(grade))
    print(f"  upstream gauge graded A: {(bad['grade_up'] == 'A').sum()}")
    print(f"  upstream gauge graded A or B: {bad['grade_up'].isin(['A', 'B']).sum()}")
    print("\nworst 12 violations:")
    print(bad.head(12).round(3).to_string(index=False))
    df.to_csv(PAIRS_CSV, index=False)
    write_stratified(df)


if __name__ == "__main__":
    if "--table-only" in sys.argv:
        # Regenerate the stratification from the shipped per-pair CSV without
        # re-reading the 852 MB boundaries file.
        write_stratified(pd.read_csv(PAIRS_CSV, dtype={"up": str, "down": str}))
    else:
        main()
