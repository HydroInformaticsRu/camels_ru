from __future__ import annotations

from pathlib import Path
import logging

import pandas as pd

from app.src.storage.directories import ensure_review_dirs

_logger = logging.getLogger("app.state.persistence")


def load_state(
    state_path: Path,
    update_dir: Path,
    logger: logging.Logger | None = None,
) -> dict:
    """Load persistent review state from disk."""

    log = logger or _logger

    ensure_review_dirs(update_dir, logger=log)
    if state_path.exists():
        try:
            return pd.read_json(state_path).to_dict(orient="records")[0]  # type: ignore[index]
        except Exception:
            log.exception("Failed to read review state; resetting", exc_info=True)
    return {"reviewed": [], "last_file": None}


def save_state(
    state_path: Path,
    update_dir: Path,
    state: dict,
    logger: logging.Logger | None = None,
) -> None:
    """Persist review state to disk."""

    log = logger or _logger

    ensure_review_dirs(update_dir, logger=log)
    df = pd.DataFrame([state])
    state_path.write_text(df.to_json(orient="records"))
    log.debug("Saved review state to %s: %s", state_path, state)
