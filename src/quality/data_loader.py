"""Data loader utilities for grade-filtered discharge data.

This module provides easy access to the reorganized discharge data
filtered by quality grade for use in analyses and paper figures.
"""

import json
from pathlib import Path
from typing import Literal

import pandas as pd

GradeType = Literal["A", "B", "C", "D", "F", "all"]


class GradedDischargeLoader:
    """Load discharge data filtered by quality grade.

    Example usage:
        loader = GradedDischargeLoader("data/HydroFiles/DischargeNew")

        # Get all A-grade gauge IDs
        a_gauges = loader.get_gauge_ids("A")

        # Load single gauge
        df = loader.load_gauge("10006")

        # Load all A+B grade gauges
        data = loader.load_gauges_by_grade(["A", "B"])

        # Get summary statistics
        stats = loader.get_grade_statistics()
    """

    def __init__(self, base_dir: str | Path):
        """Initialize loader with base directory.

        Args:
            base_dir: Path to DischargeNew directory containing
                      by_grade/, all/, and grade_mapping.json
        """
        self.base_dir = Path(base_dir)
        self._grade_mapping: dict | None = None
        self._assessment_summary: pd.DataFrame | None = None

    @property
    def grade_mapping(self) -> dict[str, list[str]]:
        """Load and cache grade mapping."""
        if self._grade_mapping is None:
            mapping_path = self.base_dir / "grade_mapping.json"
            if not mapping_path.exists():
                raise FileNotFoundError(f"Grade mapping not found: {mapping_path}")
            with open(mapping_path) as f:
                self._grade_mapping = json.load(f)
        return self._grade_mapping

    @property
    def assessment_summary(self) -> pd.DataFrame:
        """Load and cache assessment summary."""
        if self._assessment_summary is None:
            summary_path = self.base_dir / "assessment_summary.csv"
            if not summary_path.exists():
                raise FileNotFoundError(f"Assessment summary not found: {summary_path}")
            self._assessment_summary = pd.read_csv(summary_path)
        return self._assessment_summary

    def get_gauge_ids(self, grade: GradeType | list[GradeType] = "all") -> list[str]:
        """Get list of gauge IDs for specified grade(s).

        Args:
            grade: Single grade ("A", "B", etc.) or list of grades,
                   or "all" for all gauges.

        Returns:
            List of gauge IDs matching the specified grade(s).
        """
        if grade == "all":
            return sorted(
                [gid for grades in self.grade_mapping.values() for gid in grades]
            )

        if isinstance(grade, str):
            grades = [grade]
        else:
            grades = grade

        gauge_ids = []
        for g in grades:
            if g in self.grade_mapping:
                gauge_ids.extend(self.grade_mapping[g])

        return sorted(set(gauge_ids))

    def get_usable_gauge_ids(self) -> list[str]:
        """Get gauge IDs with usable quality (A, B, or C grade).

        Returns:
            List of gauge IDs with grade A, B, or C.
        """
        return self.get_gauge_ids(["A", "B", "C"])

    def get_high_quality_gauge_ids(self) -> list[str]:
        """Get gauge IDs with high quality (A or B grade).

        Returns:
            List of gauge IDs with grade A or B.
        """
        return self.get_gauge_ids(["A", "B"])

    def load_gauge(
        self,
        gauge_id: str,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Load data for a single gauge.

        Args:
            gauge_id: Gauge identifier.
            columns: Optional list of columns to load. If None, loads all.

        Returns:
            DataFrame with date index and requested columns.
        """
        # Use symlink in all/ folder for simplicity
        file_path = self.base_dir / "all" / f"{gauge_id}.csv"

        if not file_path.exists():
            raise FileNotFoundError(f"Gauge data not found: {file_path}")

        df = pd.read_csv(file_path, parse_dates=["date"], index_col="date")

        if columns:
            available = [c for c in columns if c in df.columns]
            df = df[available]

        return df

    def load_gauges_by_grade(
        self,
        grades: list[GradeType],
        columns: list[str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Load data for all gauges matching specified grades.

        Args:
            grades: List of grades to include.
            columns: Optional list of columns to load.

        Returns:
            Dictionary mapping gauge_id to DataFrame.
        """
        gauge_ids = self.get_gauge_ids(grades)
        data = {}

        for gid in gauge_ids:
            try:
                data[gid] = self.load_gauge(gid, columns)
            except FileNotFoundError:
                continue

        return data

    def load_discharge_series(
        self,
        gauge_id: str,
        unit: Literal["mm_day", "cms"] = "mm_day",
        filter_by_year_grade: list[str] | None = None,
    ) -> pd.Series:
        """Load discharge time series for a gauge.

        Args:
            gauge_id: Gauge identifier.
            unit: Discharge unit - "mm_day" or "cms".
            filter_by_year_grade: Optional list of grades to keep.
                If provided, only data from years with these grades
                will be returned (others set to NaN).

        Returns:
            Discharge series with datetime index.
        """
        df = self.load_gauge(gauge_id)

        col = "q_mm_day" if unit == "mm_day" else "q_cms"
        if col not in df.columns:
            raise ValueError(f"Column {col} not found in gauge {gauge_id}")

        series = df[col].copy()

        if filter_by_year_grade:
            # Mask data from years not matching the grade filter
            mask = df["grade"].isin(filter_by_year_grade)
            series = series.where(mask)

        return series

    def get_grade_statistics(self) -> pd.DataFrame:
        """Get summary statistics by grade.

        Returns:
            DataFrame with grade as index and statistics as columns.
        """
        stats = []
        for grade, gauge_ids in self.grade_mapping.items():
            stats.append({
                "grade": grade,
                "n_gauges": len(gauge_ids),
                "pct_total": 100 * len(gauge_ids) / sum(
                    len(v) for v in self.grade_mapping.values()
                ),
            })

        df = pd.DataFrame(stats)
        df = df.set_index("grade")

        # Reorder to A, B, C, D, F, ungraded
        order = ["A", "B", "C", "D", "F", "ungraded"]
        df = df.reindex([g for g in order if g in df.index])

        return df

    def get_year_grade_distribution(self, gauge_id: str) -> pd.Series:
        """Get grade distribution across years for a gauge.

        Args:
            gauge_id: Gauge identifier.

        Returns:
            Series with year as index and grade as value.
        """
        df = self.load_gauge(gauge_id, columns=["grade"])

        # Extract hydrological year (assuming October start)
        df = df[df["grade"].notna()]
        df["hydro_year"] = df.index.year
        df.loc[df.index.month >= 10, "hydro_year"] += 1

        # Get first grade per year (should all be same within year)
        year_grades = df.groupby("hydro_year")["grade"].first()

        return year_grades

    def filter_by_year_quality(
        self,
        df: pd.DataFrame,
        min_grade: str = "C",
    ) -> pd.DataFrame:
        """Filter DataFrame to keep only rows from years meeting quality threshold.

        Args:
            df: DataFrame with 'grade' column and datetime index.
            min_grade: Minimum grade to keep (A >= B >= C >= D >= F).

        Returns:
            Filtered DataFrame with only rows from qualifying years.
        """
        grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        min_score = grade_order.get(min_grade, 0)

        if "grade" not in df.columns:
            return df

        # Keep rows where grade meets threshold
        mask = df["grade"].map(lambda g: grade_order.get(g, 0) >= min_score)
        return df[mask]


def load_graded_discharge(
    base_dir: str | Path = "data/HydroFiles/DischargeNew",
) -> GradedDischargeLoader:
    """Convenience function to create a GradedDischargeLoader.

    Args:
        base_dir: Path to DischargeNew directory.

    Returns:
        Configured GradedDischargeLoader instance.
    """
    return GradedDischargeLoader(base_dir)
