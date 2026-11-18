"""Logging setup shared by CLI and API entry points."""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once, idempotently."""
    global _CONFIGURED
    if _CONFIGURED:
        logging.getLogger().setLevel(level.upper())
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
