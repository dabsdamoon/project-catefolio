"""Logging configuration for the Catefolio application."""

from __future__ import annotations

import logging
import sys
from typing import Any


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger("catefolio")

    if logger.handlers:
        return logger

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger


def get_logger(name: str = "catefolio") -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)


class LogContext:
    """Context manager for structured logging with additional context."""

    def __init__(self, logger: logging.Logger, operation: str, **context: Any) -> None:
        self.logger = logger
        self.operation = operation
        self.context = context

    def __enter__(self) -> "LogContext":
        self.logger.info(f"Starting {self.operation}", extra=self.context)
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any) -> bool:
        if exc_type is not None:
            self.logger.error(
                f"Failed {self.operation}: {exc_val}",
                extra=self.context,
                exc_info=True,
            )
        else:
            self.logger.info(f"Completed {self.operation}", extra=self.context)
        return False


# Initialize default logger
logger = setup_logging()
