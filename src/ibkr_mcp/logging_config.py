"""
Structured logging setup using Python's standard library.

Uses ``logging.config.dictConfig`` so it's easy to override from a YAML
file if needed.  Outputs JSON in production (LOG_FORMAT=json) and a
human-readable format during development.
"""

import json
import logging
import logging.config
import os
import sys
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    """Configure application-wide logging.

    Parameters
    ----------
    level:
        Standard logging level name (``DEBUG``, ``INFO``, ``WARNING``, …).
    """
    log_format = os.environ.get("LOG_FORMAT", "text")
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for noisy in ("ib_async", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
