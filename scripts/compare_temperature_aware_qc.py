#!/usr/bin/env python3
"""Compare current QC grades against temperature-aware response QC.

The current release QC uses direct precipitation-discharge response flags.
This script reruns the discharge quality assessment with the optional
temperature-aware response path, which checks discharge against rain plus a
simple degree-day snowmelt proxy, then compares the resulting yearly and
overall grades with the release CSVs.

Usage:
    pixi run python scripts/compare_temperature_aware_qc.py
"""

# ruff: noqa: D103

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

import pandas as pd
from tqdm.auto import tqdm

sys.path.append(str(Path(__file__).parent.parent / "src"))

from quality import assess_gauge_quality

GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
YEAR_START_MONTH = 10
MIN_YEARS = 3


def load_precipitation(path: Path) -> pd.Series | None:
    if not path.exists():
        return None
    data = pd.read_csv(path, index_col="date", parse_dates=True)
    return data["precipitation"] if "precipitation" in data.columns else None


def load_temperature(path: Path) -> pd.Series | None:
    if not path.exists():
        return None
    data = pd.read_csv(path, index_col="date", parse_dates=True)
    return data["t_mean"] if "t_mean" in data.columns else None


def grade_tier(grade: str | float | None) -> str:
    if grade in {"A", "B", "C"}:
        return "decent"
    if grade in {"D", "F"}:
        return "poor"
    return "ungraded"


def compare_grade(old: str, new: str) -> str:
    if old == new:
        return "unchanged"
    if GRADE_ORDER[new] < GRADE_ORDER[old]:
        return "improved"
    return "worsened"


def summarize_counts(grades: list[str]) -> dict[str, int]:
    counts = Counter(grades)
    return {f"n_{grade}": counts.get(grade, 0) for grade in ["A", "B", "C", "D", "F"]}


def run_temperature_aware_qc(
    release_dir: Path,
    plot_bundle_dir: Path,
    output_dir: Path,
    limit: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    current_summary = pd.read_csv(release_dir / "camels_ru_gauge_summary.csv")
    current_year_grades = pd.read_csv(release_dir / "camels_ru_year_grades.csv")
    current_year_grades["gauge_id"] = current_year_grades["gauge_id"].astype(str)
    current_year_grades = current_year_grades.set_index("gauge_id")

    hydro_dir = plot_bundle_dir / "HydroData" / "Compound"
    precip_dir = plot_bundle_dir / "parsed_meteo" / "mswep"
    temp_dir = plot_bundle_dir / "parsed_meteo" / "era5_land"

    gauges = current_summary["gauge_id"].astype(str).tolist()
    if limit is not None:
        gauges = gauges[:limit]

    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict] = []
    year_rows: list[dict] = []
    missing_precip = 0
    missing_temp = 0

    for gauge_id in tqdm(gauges, desc="Temperature-aware QC"):
        compound_path = hydro_dir / f"{gauge_id}.csv"
        if not compound_path.exists():
            continue

        compound = pd.read_csv(compound_path, index_col="date", parse_dates=True)
        if "q_mm_day" not in compound.columns:
            continue

        discharge = compound["q_mm_day"].dropna()
        if len(discharge) < 365 * MIN_YEARS:
            continue

        precipitation = load_precipitation(precip_dir / f"{gauge_id}.csv")
        temperature = load_temperature(temp_dir / f"{gauge_id}.csv")
        if precipitation is None:
            missing_precip += 1
        if temperature is None:
            missing_temp += 1

        year_results, summary = assess_gauge_quality(
            discharge=discharge,
            precipitation=precipitation,
            temperature=temperature,
            gauge_id=gauge_id,
            hydro_year_start_month=YEAR_START_MONTH,
            min_years=MIN_YEARS,
            use_temperature_aware_response=True,
        )
        if not year_results:
            continue

        grades = [result.grade.value for result in year_results]
        counts = summarize_counts(grades)
        summary_rows.append(
            {
                "gauge_id": gauge_id,
                "overall_grade_temp_aware": summary.overall_grade.value,
                "recommendation_temp_aware": summary.recommendation,
                "n_years": len(year_results),
                **counts,
            }
        )

        for result in year_results:
            year_rows.append(
                {
                    "gauge_id": gauge_id,
                    "hydro_year": result.year,
                    "grade_temp_aware": result.grade.value,
                    "flags_temp_aware": ",".join(flag.value for flag in result.flags),
                    "n_flags_temp_aware": len(result.flags),
                    "n_critical_temp_aware": result.to_dict()["n_critical_flags"],
                    "n_major_temp_aware": result.to_dict()["n_major_flags"],
                    "data_completeness": result.data_completeness,
                    "peak_ratio": result.peak_ratio,
                    "event_response_rate_temp_aware": result.event_response_rate,
                    "max_input_q_correlation_temp_aware": result.max_pq_correlation,
                }
            )

    temp_summary = pd.DataFrame(summary_rows).sort_values("gauge_id")
    temp_year_long = pd.DataFrame(year_rows).sort_values(["gauge_id", "hydro_year"])

    old_summary = current_summary.copy()
    old_summary["gauge_id"] = old_summary["gauge_id"].astype(str)
    comparison = old_summary.merge(
        temp_summary,
        on="gauge_id",
        how="inner",
        suffixes=("_current", "_temp_aware"),
    )
    comparison["current_tier"] = comparison["overall_grade"].map(grade_tier)
    comparison["temp_aware_tier"] = comparison["overall_grade_temp_aware"].map(grade_tier)
    comparison["grade_change"] = comparison.apply(
        lambda row: compare_grade(row["overall_grade"], row["overall_grade_temp_aware"]),
        axis=1,
    )
    comparison["tier_change"] = comparison["current_tier"] + " -> " + comparison["temp_aware_tier"]

    current_year_long = current_year_grades.reset_index().melt(
        id_vars="gauge_id",
        var_name="hydro_year",
        value_name="grade_current",
    )
    current_year_long = current_year_long.dropna(subset=["grade_current"])
    current_year_long["hydro_year"] = current_year_long["hydro_year"].astype(int)
    year_comparison = current_year_long.merge(temp_year_long, on=["gauge_id", "hydro_year"], how="inner")
    year_comparison["grade_change"] = year_comparison.apply(
        lambda row: compare_grade(row["grade_current"], row["grade_temp_aware"]),
        axis=1,
    )

    temp_summary.to_csv(output_dir / "temperature_aware_gauge_summary.csv", index=False)
    temp_year_long.to_csv(output_dir / "temperature_aware_year_results.csv", index=False)
    comparison.to_csv(output_dir / "temperature_aware_gauge_comparison.csv", index=False)
    year_comparison.to_csv(output_dir / "temperature_aware_year_comparison.csv", index=False)

    write_report(
        output_dir=output_dir,
        comparison=comparison,
        year_comparison=year_comparison,
        missing_precip=missing_precip,
        missing_temp=missing_temp,
    )
    return temp_summary, temp_year_long, comparison, year_comparison


def markdown_table_from_series(series: pd.Series, header_a: str, header_b: str) -> str:
    lines = [f"| {header_a} | {header_b} |", "|---|---:|"]
    for index, value in series.items():
        lines.append(f"| `{index}` | {int(value)} |")
    return "\n".join(lines)


def markdown_table_from_frame(frame: pd.DataFrame) -> str:
    if frame.empty:
        return ""
    headers = [str(column) for column in frame.columns]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in frame.columns) + " |")
    return "\n".join(lines)


def write_report(
    output_dir: Path,
    comparison: pd.DataFrame,
    year_comparison: pd.DataFrame,
    missing_precip: int,
    missing_temp: int,
) -> None:
    current_dist = (
        comparison["overall_grade"]
        .value_counts()
        .reindex(["A", "B", "C", "D", "F"], fill_value=0)
    )
    temp_dist = comparison["overall_grade_temp_aware"].value_counts().reindex(
        ["A", "B", "C", "D", "F"], fill_value=0
    )
    grade_changes = comparison["grade_change"].value_counts().reindex(
        ["unchanged", "improved", "worsened"], fill_value=0
    )
    tier_changes = comparison["tier_change"].value_counts().sort_index()
    year_changes = year_comparison["grade_change"].value_counts().reindex(
        ["unchanged", "improved", "worsened"], fill_value=0
    )

    changed_gauges = comparison[comparison["grade_change"] != "unchanged"].copy()
    changed_years = year_comparison[year_comparison["grade_change"] != "unchanged"].copy()
    worsened_years = changed_years[changed_years["grade_change"] == "worsened"].copy()

    lines = [
        "# Temperature-aware QC comparison",
        "",
        "This report compares the current release grades against a rerun using the temperature-aware",
        "meteorological response path. The temperature-aware path replaces direct raw precipitation",
        "response flags with response to effective water input: rain at Tmean > 0 C plus a simple",
        "degree-day snowmelt proxy from cold-season precipitation.",
        "",
        "The comparison keeps all other QC components unchanged: completeness, flat seasonal signal,",
        "climatology flags, anomaly flags, and post-level aggregation rules.",
        "",
        "## Coverage",
        "",
        f"- Compared gauges: `{len(comparison):,}`",
        f"- Compared gauge-years: `{len(year_comparison):,}`",
        f"- Gauges missing MSWEP precipitation in rerun: `{missing_precip:,}`",
        f"- Gauges missing ERA5-Land Tmean in rerun: `{missing_temp:,}`",
        "",
        "## Overall-grade distribution",
        "",
        "Current release:",
        "",
        markdown_table_from_series(current_dist, "Grade", "Count"),
        "",
        "Temperature-aware rerun:",
        "",
        markdown_table_from_series(temp_dist, "Grade", "Count"),
        "",
        "## Overall-grade changes",
        "",
        markdown_table_from_series(grade_changes, "Change", "Gauge count"),
        "",
        "Tier changes:",
        "",
        markdown_table_from_series(tier_changes, "Tier transition", "Gauge count"),
        "",
        "## Year-grade changes",
        "",
        markdown_table_from_series(year_changes, "Change", "Gauge-year count"),
        "",
        "## Changed-gauge examples",
        "",
    ]

    if changed_gauges.empty:
        lines.append("No gauge-level grade changes.")
    else:
        examples = changed_gauges[
            [
                "gauge_id",
                "overall_grade",
                "overall_grade_temp_aware",
                "grade_change",
                "current_tier",
                "temp_aware_tier",
                "n_A_temp_aware",
                "n_B_temp_aware",
                "n_C_temp_aware",
                "n_D_temp_aware",
                "n_F_temp_aware",
            ]
        ].head(20)
        lines.append(markdown_table_from_frame(examples))

    lines.extend(["", "## Changed-year examples", ""])
    if changed_years.empty:
        lines.append("No year-level grade changes.")
    else:
        examples = changed_years[
            [
                "gauge_id",
                "hydro_year",
                "grade_current",
                "grade_temp_aware",
                "grade_change",
                "flags_temp_aware",
                "data_completeness",
                "peak_ratio",
            ]
        ].head(30)
        lines.append(markdown_table_from_frame(examples))

    lines.extend(["", "## Worsened-year examples", ""])
    if worsened_years.empty:
        lines.append("No year-level worsening.")
    else:
        examples = worsened_years[
            [
                "gauge_id",
                "hydro_year",
                "grade_current",
                "grade_temp_aware",
                "flags_temp_aware",
                "event_response_rate_temp_aware",
                "max_input_q_correlation_temp_aware",
                "peak_ratio",
            ]
        ].head(10)
        lines.append(markdown_table_from_frame(examples))

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A grade improvement usually means direct precipitation-response minor flags were removed",
            "or replaced by fewer effective-water response flags. A worsening usually means the",
            "effective rain-plus-melt input exposes weak hydrological response that raw precipitation",
            "did not capture.",
            "",
            "The temperature-aware response check is still a screening heuristic. It uses a simple",
            "degree-day snowpack proxy rather than a calibrated snow model, so it should be reviewed",
            "before becoming the default release QC.",
            "",
        ]
    )

    (output_dir / "temperature_aware_comparison.md").write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=Path("release/CAMELS_RU_v1.0"))
    parser.add_argument(
        "--plot-bundle-dir",
        type=Path,
        default=Path("release/plot_bundle/data/CAMELS_RU"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/data_quality_grading_share/temperature_aware_comparison"),
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run_temperature_aware_qc(
        release_dir=args.release_dir,
        plot_bundle_dir=args.plot_bundle_dir,
        output_dir=args.output_dir,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
