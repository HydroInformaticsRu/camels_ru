"""Gauge-ID based scope for CAMELS-RU manuscript analyses.

The release keeps every delineated catchment and NetCDF row.  The manuscript
analyses, however, exclude AIS GMVO hydropower/reservoir stations whose gauge
identifiers have seven or more characters.  This module centralises that rule so
figures, tables, and macro checks do not silently diverge.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

PAPER_ANALYSIS_EXCLUDED_MIN_ID_LENGTH = 7
PAPER_ANALYSIS_EXCLUSION_LABEL = "gauge_id_len_ge_7"
PAPER_ANALYSIS_EXCLUSION_NOTE = (
    "Gauges with gauge_id length >= 7 are retained in the CAMELS-RU release "
    "but excluded from manuscript analysis maps, tables, and summary numbers."
)


@dataclass(frozen=True)
class PaperAnalysisScopeSummary:
    """Counts for the gauge-ID based manuscript-analysis scope."""

    n_total: int
    n_included: int
    n_excluded: int
    excluded_min_id_length: int = PAPER_ANALYSIS_EXCLUDED_MIN_ID_LENGTH


def _as_string_index(gauge_ids: Iterable[object]) -> pd.Index:
    """Return gauge identifiers as a string index without changing order."""
    return pd.Index(gauge_ids).astype(str)


def paper_analysis_exclusion_mask(gauge_ids: Iterable[object]) -> pd.Series:
    """Return True for gauge IDs excluded from manuscript analyses."""
    ids = _as_string_index(gauge_ids)
    return pd.Series(ids.str.len() >= PAPER_ANALYSIS_EXCLUDED_MIN_ID_LENGTH, index=ids)


def paper_analysis_inclusion_mask(gauge_ids: Iterable[object]) -> pd.Series:
    """Return True for gauge IDs included in manuscript analyses."""
    excluded = paper_analysis_exclusion_mask(gauge_ids)
    return ~excluded


def is_paper_analysis_excluded_gauge_id(gauge_id: object) -> bool:
    """Return whether one gauge ID is excluded from manuscript analyses."""
    return len(str(gauge_id)) >= PAPER_ANALYSIS_EXCLUDED_MIN_ID_LENGTH


def paper_analysis_scope_summary(gauge_ids: Iterable[object]) -> PaperAnalysisScopeSummary:
    """Count included and excluded gauge IDs for a collection."""
    excluded = paper_analysis_exclusion_mask(gauge_ids)
    n_excluded = int(excluded.sum())
    n_total = int(len(excluded))
    return PaperAnalysisScopeSummary(
        n_total=n_total,
        n_included=n_total - n_excluded,
        n_excluded=n_excluded,
    )


def filter_paper_analysis_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Filter an index-keyed DataFrame/GeoDataFrame to manuscript-analysis gauges."""
    mask = paper_analysis_inclusion_mask(frame.index)
    return frame.loc[mask.to_numpy()].copy()


def filter_paper_analysis_column(frame: pd.DataFrame, gauge_id_col: str = "gauge_id") -> pd.DataFrame:
    """Filter a column-keyed DataFrame to manuscript-analysis gauges."""
    mask = paper_analysis_inclusion_mask(frame[gauge_id_col].astype(str))
    return frame.loc[mask.to_numpy()].copy()
