"""Minimal project logger helpers.

Provides two helpers used across the app: get_logger and setup_logger.
This module is intentionally small and dependency-free so linters are
happy and it can be imported early during app startup.
"""

from __future__ import annotations

from collections.abc import MutableMapping
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from typing import Any

_DEFAULT_LOGGER_NAME = "hydro_logs"
_DEFAULT_LOG_DIR = "logs"
_DEFAULT_LOG_FILENAME = "hydro_logs.log"
_ROTATE_MAX_BYTES = 10 * 1024 * 1024
_ROTATE_BACKUP_COUNT = 5

_LEVEL_EMOJIS: dict[int, str] = {
    logging.DEBUG: "🐞    ",
    logging.INFO: "ℹ️    ",
    logging.WARNING: "⚠️    ",
    logging.ERROR: "❌    ",
    logging.CRITICAL: "🚨    ",
}

_LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG: "\x1b[38;5;244m",
    logging.INFO: "\x1b[38;5;39m",
    logging.WARNING: "\x1b[38;5;214m",
    logging.ERROR: "\x1b[38;5;196m",
    logging.CRITICAL: "\x1b[48;5;196;38;5;231m",
}
_RESET_COLOR = "\x1b[0m"


class EmojiFormatter(logging.Formatter):
    """Formatter that injects emoji and optional color into messages."""

    def __init__(self, *, use_color: bool = True) -> None:
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(func_ctx)s | %(emoji)s %(message)s"
        super().__init__(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "func_ctx"):
            record.func_ctx = "-"  # type: ignore[attr-defined]

        if record.args:
            try:
                _ = record.msg % record.args
            except Exception:
                record.msg = " ".join(
                    [str(record.msg), *(str(a) for a in record.args)]
                )
                record.args = ()

        record.emoji = _LEVEL_EMOJIS.get(record.levelno, "➡️")
        formatted = super().format(record)
        if self.use_color and (color := _LEVEL_COLORS.get(record.levelno)):
            return f"{color}{formatted}{_RESET_COLOR}"
        return formatted


def _determine_log_level(explicit_level: int | str | None) -> int:
    level_str = str(
        explicit_level or os.getenv("HYDRO_LOGS_LOG_LEVEL", "INFO")
    ).upper()
    return getattr(logging, level_str, logging.INFO)


def get_logger(
    name: str = _DEFAULT_LOGGER_NAME, *, level: int | str | None = None
) -> logging.Logger:
    """Return a configured logger for the given name.

    The function is idempotent: subsequent calls return the same logger
    instance. If ``level`` is provided the logger level is updated.
    """
    logger = logging.getLogger(name)
    log_level = _determine_log_level(level)
    if getattr(logger, "_hydro_logs_configured", False):
        if level is not None:
            logger.setLevel(log_level)
        return logger

    logger.setLevel(log_level)
    logger.propagate = False
    use_color = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
    formatter = EmojiFormatter(use_color=use_color)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    logger._hydro_logs_configured = True  # type: ignore[attr-defined]
    logger.debug(
        "Logger '%s' initialized at level %s.",
        name,
        logging.getLevelName(log_level),
    )
    return logger


class _FunctionContextAdapter(logging.LoggerAdapter):
    def process(
        self,
        msg: str,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[str, MutableMapping[str, Any]]:
        kwargs.setdefault("extra", {})["func_ctx"] = self.extra.get(
            "func_ctx", "-"
        )
        return msg, kwargs


def setup_logger(
    function_name: str,
    *,
    level: int | str | None = None,
    logger_name: str = _DEFAULT_LOGGER_NAME,
    log_file: str | Path | None = None,
    rotate: bool = True,
    max_bytes: int = _ROTATE_MAX_BYTES,
    backup_count: int = _ROTATE_BACKUP_COUNT,
) -> logging.LoggerAdapter:
    """Create or update a logger and optionally add a rotating file handler.

    Returns a LoggerAdapter that automatically injects function context.
    """
    base_logger = get_logger(logger_name, level=level)
    effective_log_file = (
        log_file
        or os.getenv("HYDRO_LOGS_LOG_FILE")
        or Path(_DEFAULT_LOG_DIR) / _DEFAULT_LOG_FILENAME
    )
    try:
        Path(effective_log_file).parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - OS depends
        base_logger.error(
            "Failed to create log dir for %s: %s", effective_log_file, exc
        )
        rotate = False

    if rotate:
        abs_log_path = str(Path(effective_log_file).resolve())
        handler_exists = any(
            isinstance(h, RotatingFileHandler)
            and getattr(h, "baseFilename", None) == abs_log_path
            for h in base_logger.handlers
        )
        if not handler_exists:
            try:
                rfh = RotatingFileHandler(
                    abs_log_path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
                rfh.setFormatter(EmojiFormatter(use_color=False))
                base_logger.addHandler(rfh)
                base_logger.debug(
                    "Added rotating file handler for %s (max=%d bytes, backups=%d)",
                    abs_log_path,
                    max_bytes,
                    backup_count,
                )
            except OSError as exc:  # pragma: no cover - OS depends
                base_logger.error(
                    "Could not add rotating file handler for %s: %s",
                    abs_log_path,
                    exc,
                )

    return _FunctionContextAdapter(base_logger, {"func_ctx": function_name})


__all__ = ["get_logger", "setup_logger"]
