from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
from typing import Any

import pandas as pd

_logger = logging.getLogger("app.review.metrics")


@lru_cache(maxsize=1)
def _load_metrics(metrics_path: Path) -> pd.DataFrame:
    if not metrics_path.exists():
        raise FileNotFoundError(metrics_path)
    df = pd.read_csv(metrics_path)
    df = df.set_index(df.columns[0])
    df.index = df.index.astype(str)
    return df


def fetch_metrics(
    metrics_path: Path,
    gauge_id: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any] | None:
    log = logger or _logger

    try:
        df = _load_metrics(metrics_path)
    except FileNotFoundError:
        log.warning("Metrics file not found: %s", metrics_path)
        return None
    except Exception:  # noqa: BLE001
        log.exception("Failed to load metrics from %s", metrics_path)
        return None

    key = str(gauge_id)
    if key not in df.index:
        log.debug("No metrics entry for gauge %s", key)
        return None

    row = df.loc[key]
    return {
        "NSE": float(row.get("NSE")) if "NSE" in row else None,
        "KGE": float(row.get("KGE")) if "KGE" in row else None,
        "r": float(row.get("r")) if "r" in row else None,
        "RMSE": float(row.get("RMSE")) if "RMSE" in row else None,
    }


def clear_metrics_cache() -> None:
    _load_metrics.cache_clear()
