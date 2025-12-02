from __future__ import annotations

import logging

import pandas as pd

_logger = logging.getLogger("app.analysis.classification")


def classify_series(
    df: pd.DataFrame,
    logger: logging.Logger | None = None,
) -> tuple[str, bool, bool, bool]:
    """Classify a CSV time series based on NaN distribution and coverage."""
    log = logger or _logger

    if df.empty:
        return ("empty", True, False, False)

    num_df = df.select_dtypes(include=["number"])  # type: ignore[arg-type]
    if num_df.shape[1] == 0:
        return ("empty", True, False, False)

    series = num_df.iloc[:, -1]
    has_data = series.notna().sum() > 0
    if not has_data:
        return ("empty", True, False, False)

    has_nans = bool(series.isna().any())
    status = "partial"

    datetime_col = None
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            datetime_col = df[col]
            break
        if isinstance(df[col].iloc[0] if len(df[col]) else None, str):
            try:
                datetime_col = pd.to_datetime(df[col], errors="raise")
                break
            except Exception as exc:  # noqa: PERF203
                log.debug(
                    "Failed to parse column %s as datetime: %s", col, exc
                )
                continue

    if datetime_col is not None:
        try:
            temp_df = pd.DataFrame(
                {"datetime": pd.to_datetime(datetime_col), "value": series}
            ).dropna(subset=["datetime"])

            if not temp_df.empty:
                start_date = pd.Timestamp("2008-01-01")
                end_date = pd.Timestamp("2023-12-31")

                period_mask = (temp_df["datetime"] >= start_date) & (
                    temp_df["datetime"] <= end_date
                )
                period_data = temp_df[period_mask]

                if not period_data.empty:
                    data_start = period_data["datetime"].min()
                    data_end = period_data["datetime"].max()

                    if (
                        data_start == pd.Timestamp("2008-01-01")
                        and data_end >= pd.Timestamp("2023-12-31")
                        and period_data["value"].notna().all()
                    ):
                        status = "full"
        except Exception as exc:  # noqa: PERF203
            log.debug(
                "Failed to parse datetime for full gauge classification: %s",
                exc,
            )
            status = "partial" if has_nans else "full"
    else:
        status = "partial" if has_nans else "full"

    return (status, False, bool(has_nans), bool(has_data))
