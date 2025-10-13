from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from app.src.storage.directories import ensure_review_dirs

_logger = logging.getLogger("app.review.counts")


def _collect_files(paths: Iterable[Path], logger: logging.Logger) -> set[str]:
    names: set[str] = set()
    for directory in paths:
        try:
            if directory.exists():
                for child in directory.iterdir():
                    if child.is_file():
                        names.add(child.name)
        except Exception:
            logger.debug("Failed to enumerate %s", directory, exc_info=True)
    return names


def compute_review_counts(
    update_dir: Path,
    logger: logging.Logger | None = None,
) -> dict[str, int]:
    """Count reviewed files across the various category folders."""
    log = logger or _logger

    ensure_review_dirs(update_dir, logger=log)

    full_dirs = [update_dir / "full" / quality for quality in ("poor", "decent")]
    partial_dirs = [update_dir / "partial" / quality for quality in ("poor", "decent")]
    shifted_dirs = [update_dir / "shifted"]
    negatives_dirs = [update_dir / "negatives" / quality for quality in ("poor", "decent")]
    freezing_dirs = [update_dir / "freezing" / quality for quality in ("poor", "decent")]
    poor_dirs = [
        update_dir / "full" / "poor",
        update_dir / "partial" / "poor",
        update_dir / "negatives" / "poor",
        update_dir / "freezing" / "poor",
    ]

    full = _collect_files(full_dirs, log)
    partial = _collect_files(partial_dirs, log)
    shifted = _collect_files(shifted_dirs, log)
    negatives = _collect_files(negatives_dirs, log)
    freezing = _collect_files(freezing_dirs, log)
    poor = _collect_files(poor_dirs, log)

    return {
        "full": len(full),
        "partial": len(partial),
        "shifted": len(shifted),
        "negatives": len(negatives),
        "freezing": len(freezing),
        "poor": len(poor),
    }
