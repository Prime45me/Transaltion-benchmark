"""
Structured logging configuration for the Twi Translation Benchmark Lab.

Provides consistent, sanitized, and actionable logging for dataset validation,
configuration loading, and future translation experiments.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

# Regex pattern to identify and redact sensitive tokens (API keys, bearer tokens)
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|bearer|secret|password|token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{8,})['\"]?"
)


class SanitizedFormatter(logging.Formatter):
    """Logging formatter that redacts accidentally exposed credentials."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return _SECRET_PATTERN.sub(r"\1: [REDACTED]", original)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    stream: Optional[object] = None,
) -> logging.Logger:
    """
    Configures and returns the root application logger for twi_lab.

    Args:
        level: Logging level name ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
        log_file: Optional path to write persistent log output.
        stream: Output stream for console logging (defaults to sys.stderr).

    Returns:
        Configured logging.Logger instance for 'twi_lab'.
    """
    logger = logging.getLogger("twi_lab")
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    logger.handlers.clear()

    formatter = SanitizedFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(stream or sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
