from __future__ import annotations

import logging

import pandas as pd
import plotly.graph_objs as go
import plotly.io as pio

from app.src.analysis.classification import classify_series

_logger = logging.getLogger("app.plots.series_plot")

_PLOT_START = pd.Timestamp("2008-01-01 00:00:00", tz="UTC")
_PLOT_END = pd.Timestamp("2023-12-31 23:59:59", tz="UTC")


def _extract_datetime_series(df: pd.DataFrame) -> pd.Series:
    datetime_cols = [
        col
        for col in df.columns
        if pd.api.types.is_datetime64_any_dtype(df[col])
    ]
    if datetime_cols:
        return pd.to_datetime(df[datetime_cols[0]], utc=True, errors="coerce")

    object_cols = [col for col in df.columns if df[col].dtype == object]
    for col in object_cols:
        parsed = pd.to_datetime(df[col], utc=True, errors="coerce")
        if parsed.notna().any():
            return parsed

    if df.empty:
        return pd.Series(pd.DatetimeIndex([], tz="UTC"))

    periods = len(df)
    generated = pd.date_range(
        start=_PLOT_START, end=_PLOT_END, periods=periods, tz="UTC"
    )
    return pd.Series(generated)


def _background_color(
    df: pd.DataFrame, y: pd.Series, logger: logging.Logger
) -> str:
    if not y.empty and (y < 0).any():
        return "#fecaca"

    try:
        gauge_status, *_rest = classify_series(df, logger=logger)
    except Exception:  # noqa: BLE001
        gauge_status = "partial"

    return "#d1fae5" if gauge_status == "full" else "white"


def plot_series_html(
    df: pd.DataFrame,
    title: str,
    logger: logging.Logger | None = None,
) -> str:
    """Create an HTML snippet with a Plotly line plot for the gauge series."""
    active_logger = logger or _logger
    active_logger.debug("Rendering series plot with %d rows", len(df))

    num_df = df.select_dtypes(include=["number"])  # type: ignore[arg-type]
    y = num_df.iloc[:, -1] if not num_df.empty else pd.Series(dtype=float)

    x = _extract_datetime_series(df)

    if not y.empty and x.empty:
        x = pd.Series(
            pd.date_range(
                start=_PLOT_START, periods=len(y), freq="D", tz="UTC"
            )
        )

    x = x.reset_index(drop=True)
    y = y.reset_index(drop=True)

    fig = go.Figure()

    if not y.empty and not x.empty:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines+markers",
                name="series",
                showlegend=False,
                marker={"size": 5, "color": "#111827", "opacity": 0.9},
                line={"width": 1.5, "color": "#111827"},
                hovertemplate="%{x|%Y-%m}<br>Value: %{y:.2f}<extra></extra>",
            )
        )

    background_color = _background_color(df, y, active_logger)

    fig.update_layout(
        showlegend=False,
        title=None,
        xaxis_title="Time",
        yaxis_title="Value",
        autosize=True,
        margin={"t": 20, "r": 20, "b": 50, "l": 50},
        paper_bgcolor=background_color,
        plot_bgcolor=background_color,
        height=600,
        dragmode="zoom",
        xaxis={
            "type": "date",
            "autorange": False,
            "range": [
                _PLOT_START.to_pydatetime(),
                _PLOT_END.to_pydatetime(),
            ],
            "tick0": _PLOT_START.to_pydatetime(),
            "tickformat": "%Y-%m",
            "dtick": "M3",
            "tickangle": -45,
            "showgrid": True,
            "gridcolor": "rgba(0,0,0,0.12)",
            "gridwidth": 1,
        },
        yaxis={
            "autorange": True,
            "showgrid": True,
            "gridcolor": "rgba(0,0,0,0.12)",
            "gridwidth": 1,
        },
        annotations=[
            {
                "xref": "paper",
                "yref": "paper",
                "x": 0.01,
                "y": 0.98,
                "text": title,
                "showarrow": False,
                "font": {"size": 11, "color": "#6b7280"},
                "bgcolor": "rgba(255,255,255,0.0)",
                "bordercolor": "rgba(0,0,0,0)",
            }
        ],
    )

    return pio.to_html(
        fig,
        include_plotlyjs=True,
        full_html=False,
        default_width="100%",
        default_height="600px",
        config={
            "responsive": True,
            "doubleClick": "reset",
            "scrollZoom": True,
            "displayModeBar": True,
        },
    )
