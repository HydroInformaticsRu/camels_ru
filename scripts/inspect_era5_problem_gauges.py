"""Identify the 17 ERA5 problem gauges not in the handoff's list of 7.

Emit NaN fraction, geographic bounds (from release boundaries), and suspected root cause.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

KNOWN_7 = {"1508", "2241", "11674", "81602", "81748", "2155", "9194"}

aud = pd.read_csv(".tmp/coverage_audit.csv")
era5_bad = aud[(aud["source"] == "ERA5") & (aud["bucket"] == "nan_over_5pct")]
era5_bad = era5_bad.sort_values("nan_frac", ascending=False)
era5_bad["gauge_id"] = era5_bad["gauge_id"].astype(str)
print(f"Total ERA5 nan>5% gauges: {len(era5_bad)}")
print(f"Of which known-7: {era5_bad['gauge_id'].isin(KNOWN_7).sum()}")
print(f"Unknown extras:    {(~era5_bad['gauge_id'].isin(KNOWN_7)).sum()}\n")

ws = gpd.read_file("release/CAMELS_RU_v1.0/camels_ru_boundaries.gpkg")
ws["gauge_id"] = ws["gauge_id"].astype(str)
# Representative point + centroid bounds
ws_area = ws.to_crs("EPSG:3857")
ws["centroid_lon"] = ws.geometry.centroid.x
ws["centroid_lat"] = ws.geometry.centroid.y
ws["min_lon"] = ws.geometry.bounds["minx"]
ws["max_lon"] = ws.geometry.bounds["maxx"]
ws["min_lat"] = ws.geometry.bounds["miny"]
ws["max_lat"] = ws.geometry.bounds["maxy"]

print("All 24 ERA5 problem gauges with geo + temporal profile:\n")
print(
    f"{'gauge_id':>10s}  {'nan_frac':>8s}  {'area_km2':>9s}  "
    f"{'c_lon':>7s}  {'c_lat':>6s}  {'lon_bounds':>17s}  {'known?':>6s}"
)
print("-" * 90)
for _, row in era5_bad.iterrows():
    gid = row["gauge_id"]
    w = ws[ws["gauge_id"] == gid]
    if w.empty:
        print(f"{gid:>10s}  {row['nan_frac']:.4f}   (not in boundaries)")
        continue
    w0 = w.iloc[0]
    known = "✓" if gid in KNOWN_7 else "NEW"
    print(
        f"{gid:>10s}  {row['nan_frac']:8.4f}  {w0['area_km2']:9.1f}  "
        f"{w0['centroid_lon']:7.2f}  {w0['centroid_lat']:6.2f}  "
        f"{w0['min_lon']:6.2f}–{w0['max_lon']:6.2f}   {known:>6s}"
    )

# Check which months of which years are NaN — to identify if it's 2023 or something else
print("\n=== Per-year NaN breakdown for NEW problem gauges ===")
for gid in era5_bad["gauge_id"]:
    if gid in KNOWN_7:
        continue
    csv = Path("data/Russia/MeteoData/CamelsRU/era5_land") / f"{gid}.csv"
    if not csv.exists():
        continue
    df = pd.read_csv(csv, index_col="date", parse_dates=True)
    df = df.loc["2008-01-01":"2023-12-31"]
    by_year = df["t_mean"].isna().groupby(df.index.year).mean()
    bad_years = {y: float(v) for y, v in by_year.items() if v > 0.01}
    print(f"  {gid}: bad years = {bad_years}")
