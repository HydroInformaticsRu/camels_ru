"""Draw two full-record hydrographs with released annual quality-grade bands.

Run: pixi run --as-is python scripts/plot_grading_examples.py
Add --write to copy the checked PDF into both manuscript image directories.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from utils.release_io import open_release_dataset

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release/CAMELS_RU_v1.0"
OUT = ROOT / "paper/previews/grading_examples"
NAME_SOURCE = ROOT / "data/CAMELS_RU/geometry/camels_gauges.gpkg"
GAUGES = ("19128", "75387")
# Same grade hues as scripts/plot_gauge_reliability.py; labels also encode grade.
COLORS = {"A": "#dfe318", "B": "#4ec36b", "C": "#21918c", "D": "#375a8c", "F": "#440154"}


def main():
    """Check source alignment, draw daily values unchanged, and export provenance."""
    names = ["camels_ru_year_grades.csv", "camels_ru_year_flags.csv", "camels_ru_gauge_summary.csv"]
    grades, flags, summaries = [
        pd.read_csv(RELEASE / name, dtype={"gauge_id": str}).set_index("gauge_id") for name in names
    ]
    metadata = gpd.read_file(NAME_SOURCE, ignore_geometry=True).set_index("gauge_id")
    metadata.index = metadata.index.astype(str)
    source_names = metadata.loc[list(GAUGES), "name_en"].str.strip()
    name_parts = source_names.str.extract(r"^r\. (.+?) - (?:pos|d)\. (.+?)$")
    np.testing.assert_equal(name_parts.notna().all().all(), True)
    panel_names = name_parts.agg(" at ".join, axis=1)
    plt.rcParams.update(
        {"font.family": "DejaVu Sans", "font.size": 8, "pdf.fonttype": 42, "path.simplify": False}
    )
    fig, axes = plt.subplots(2, 1, figsize=(160 / 25.4, 132 / 25.4), sharex=True)
    fig.subplots_adjust(left=0.10, right=0.90, top=0.89, bottom=0.23, hspace=0.45)
    dates = pd.date_range("2008-01-01", "2023-12-31", freq="D")
    hydro_years = dates.year + (dates.month >= 10)
    records, tables = [], []
    with (
        open_release_dataset(RELEASE / "camels_ru_discharge.nc") as qds,
        open_release_dataset(RELEASE / "camels_ru_forcing.nc") as pds,
    ):
        np.testing.assert_array_equal(qds.time.values, pds.time.values)
        np.testing.assert_array_equal(qds.time.values, dates.values)
        for i, (gid, ax) in enumerate(zip(GAUGES, axes, strict=True)):
            q = qds.sel(gauge_id=gid).discharge_mm.values
            quality = qds.sel(gauge_id=gid).quality_flag.values
            rain = pds.sel(gauge_id=gid).precip_mswep.values
            observed, filled, missing = quality == 0, quality == 1, quality == 3
            np.testing.assert_equal(np.all(observed | filled | missing), True)
            np.testing.assert_array_equal(np.isfinite(q), observed | filled)
            annual = grades.loc[gid].dropna()
            flag_rows = flags.loc[gid].set_index("hydro_year")
            if set(annual.index.astype(int)) != set(flag_rows.index):
                raise AssertionError("Annual grade and flag tables have different assessed years")
            for year, grade in annual.items():
                if grade not in COLORS or grade != flag_rows.loc[int(year), "grade"]:
                    raise AssertionError("Annual grade differs between released tables")
            strict_a = bool(annual.eq("A").all())
            np.testing.assert_equal(strict_a, summaries.loc[gid, "overall_grade"] == "A")
            day_grades = pd.Series(hydro_years.astype(str)).map(annual).fillna("").to_numpy()
            for year in sorted(set(hydro_years)):
                start = max(dates[0], pd.Timestamp(year=year - 1, month=10, day=1))
                end = min(dates[-1] + pd.Timedelta(days=1), pd.Timestamp(year=year, month=10, day=1))
                grade = annual.get(str(year))
                if pd.notna(grade):
                    ax.axvspan(start, end, color=COLORS[grade], alpha=0.20, lw=0, zorder=0)
                    ax.text(
                        start + (end - start) / 2,
                        1.02,
                        grade,
                        transform=ax.get_xaxis_transform(),
                        ha="center",
                        va="bottom",
                        fontsize=8,
                        zorder=6,
                        clip_on=False,
                    )
                else:
                    ax.axvspan(
                        start, end, facecolor=".95", edgecolor=".78", hatch="////", lw=0.4, zorder=0
                    )
            pax = ax.twinx()
            pax.bar(dates, rain, width=1, color="#437BA6", alpha=0.72, linewidth=0, zorder=1)
            # Separate display scales place rainfall above runoff without changing values.
            pax.set_ylim(float(np.nanmax(rain)) * 2.4, 0)
            pax.set_ylabel("Precipitation (mm d⁻¹) ↓", fontsize=8, color="#315A78", labelpad=5)
            pax.tick_params(axis="y", labelsize=8, colors="#315A78", length=2)
            pax.spines["top"].set_visible(False)
            ax.set_zorder(pax.get_zorder() + 1)
            ax.patch.set_visible(False)
            ax.plot(dates, np.where(observed, q, np.nan), color="black", lw=0.65, zorder=4)
            if filled.any():
                ax.scatter(
                    dates[filled],
                    q[filled],
                    s=8,
                    facecolors="white",
                    edgecolors="#D55E00",
                    linewidths=0.7,
                    zorder=5,
                )
            ax.set_ylim(0, float(np.nanmax(q)) * 1.45)
            ax.set_ylabel("Runoff depth (mm d⁻¹)", fontsize=8, labelpad=5)
            ax.set_xlim(dates[0], dates[-1] + pd.Timedelta(days=1))
            ax.set_title(
                f"({chr(97 + i)}) {gid} · {panel_names.loc[gid]}",
                loc="left",
                fontsize=9,
                weight="bold",
                pad=22,
            )
            ax.tick_params(axis="both", labelsize=8, length=2)
            ax.spines["top"].set_visible(False)
            counts = {
                "observed": int(observed.sum()),
                "filled": int(filled.sum()),
                "missing": int(missing.sum()),
                "precip_missing": int(np.isnan(rain).sum()),
            }
            records.append(
                {
                    "gauge_id": gid,
                    "gauge_grade": summaries.loc[gid, "overall_grade"],
                    "annual_grades": annual.to_dict(),
                    "strict_gauge_A": strict_a,
                    "unassessed_days": int((day_grades == "").sum()),
                    **counts,
                }
            )
            tables.append(
                pd.DataFrame(
                    {
                        "gauge_id": gid,
                        "date": dates,
                        "hydro_year": hydro_years,
                        "annual_grade": day_grades,
                        "discharge_mm": q,
                        "precip_mswep": rain,
                        "quality_flag": quality,
                    }
                )
            )
    axes[-1].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[-1].set_xlabel("Calendar date · annual grades cover October–September", fontsize=8)
    fig.legend(
        handles=[
            Line2D([], [], color="black", lw=0.9, label="Observed runoff"),
            Patch(facecolor="#437BA6", alpha=0.72, label="MSWEP precipitation (inverted)"),
        ],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.115),
        frameon=False,
        ncol=2,
        fontsize=8,
    )
    fig.legend(
        handles=[Patch(facecolor=COLORS[g], alpha=0.20, label=g) for g in COLORS]
        + [Patch(facecolor=".95", edgecolor=".78", hatch="////", label="Unassessed")],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.065),
        frameon=False,
        ncol=6,
        fontsize=8,
        handlelength=1.4,
        columnspacing=1.3,
    )
    fig.text(
        0.5,
        0.027,
        "Shading = recorded annual grade; letters repeat the grade independently of colour.",
        ha="center",
        fontsize=7.5,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT.with_suffix(".pdf"))
    fig.savefig(OUT.with_suffix(".png"), dpi=300)
    plt.close(fig)
    pd.concat(tables, ignore_index=True).to_csv(OUT.with_suffix(".csv"), index=False)
    paths = [RELEASE / name for name in names] + [
        RELEASE / "camels_ru_discharge.nc",
        RELEASE / "camels_ru_forcing.nc",
        Path(__file__),
        NAME_SOURCE,
    ]
    hashes = {}
    for path in paths:
        with path.open("rb") as source:
            hashes[str(path.relative_to(ROOT))] = hashlib.file_digest(source, "sha256").hexdigest()
    OUT.with_suffix(".json").write_text(
        json.dumps(
            {
                "source": str(RELEASE.relative_to(ROOT)),
                "selection": "Dissertation examples 19128 and 75387; full released span.",
                "source_names": source_names.to_dict(),
                "transformations": "Daily values unchanged; annual grades read from CSV.",
                "date_start": str(dates[0].date()),
                "date_end": str(dates[-1].date()),
                "records": records,
                "sha256": hashes,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Also update both manuscript PDF copies")
    args = parser.parse_args()
    main()
    if args.write:
        for directory in (ROOT / "paper/images", ROOT / "paper/overleaf/images"):
            shutil.copy2(OUT.with_suffix(".pdf"), directory / "fig_grading_examples.pdf")
