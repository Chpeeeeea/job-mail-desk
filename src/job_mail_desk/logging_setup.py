from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOG_DIR, ensure_directories


def configure_logging() -> None:
    ensure_directories()
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    file_handler = RotatingFileHandler(
        LOG_DIR / "jobmaildesk.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

