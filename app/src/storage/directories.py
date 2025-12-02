from __future__ import annotations

from collections.abc import Iterable
import logging
from pathlib import Path

_logger = logging.getLogger("app.storage.directories")


def ensure_review_dirs(
    update_dir: Path, logger: logging.Logger | None = None
) -> None:
    """Ensure the expected update/ directory structure exists."""
    log = logger or _logger

    update_dir.mkdir(parents=True, exist_ok=True)

    structured_categories = ("full", "partial", "negatives", "freezing")
    for category in structured_categories:
        category_root = update_dir / category
        category_root.mkdir(parents=True, exist_ok=True)
        for quality in ("poor", "decent"):
            (category_root / quality).mkdir(parents=True, exist_ok=True)

    shifted_root = update_dir / "shifted"
    shifted_root.mkdir(parents=True, exist_ok=True)

    log.debug("Ensured review directories under %s", update_dir)


def remove_existing_copies(
    update_dir: Path,
    filename: str,
    logger: logging.Logger | None = None,
) -> None:
    """Remove prior review copies before reclassifying a gauge."""
    log = logger or _logger

    ensure_review_dirs(update_dir, logger=log)

    candidate_dirs: list[Path] = []

    def add_dirs(paths: Iterable[Path]) -> None:
        for path in paths:
            candidate_dirs.append(path)

    for category in ("full", "partial", "negatives", "freezing"):
        for quality in ("poor", "decent"):
            add_dirs([update_dir / category / quality])

    add_dirs([update_dir / "shifted"])

    for directory in candidate_dirs:
        target = directory / filename
        try:
            if target.exists():
                target.unlink()
                log.debug("Removed previous copy: %s", target)
        except Exception:
            log.warning(
                "Failed to remove previous copy: %s", target, exc_info=True
            )
