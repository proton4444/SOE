"""Small, credential-safe logging helpers for the controlled beta."""

from __future__ import annotations

import logging
import os
import secrets
from logging.handlers import RotatingFileHandler
from pathlib import Path

from webapp.rooms import SERVER_DATA


LOGGER_NAME = "soe.beta"
LOG_FILE = Path(os.environ.get("SOE_LOG_FILE", str(SERVER_DATA / "beta.log")))
logger = logging.getLogger(LOGGER_NAME)
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            "%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(handler)


def request_id() -> str:
    """Generate an identifier that is safe to include in operator logs."""
    return secrets.token_hex(8)
