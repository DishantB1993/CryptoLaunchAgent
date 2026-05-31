"""
Structured logging configuration for CryptoLaunchAgent.

This module provides a minimal JSON-formatted logger without external
runtime dependencies so logs are structured for easier parsing in
development and production environments.

The formatter is intentionally simple: it outputs a compact JSON object
containing timestamp, level, logger name, message, and optional exception
information. For heavy-duty production logging, replace this with a
library such as `python-json-logger` or route logs to a structured
log aggregator.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as compact JSON objects.

    Keep the payload small and deterministic to make grepping and
    ingestion by log collectors predictable.
    """

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - thin wrapper
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach exception info when present
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Include extra attributes (if provided via `extra=`)
        for key, val in getattr(record, "__dict__", {}).items():
            if key in ("msg", "args", "levelname", "levelno", "name", "pathname", "lineno", "exc_info"):
                continue
            if key.startswith("_"):
                continue
            try:
                json.dumps({key: val})  # quick-validate serializability
                payload[key] = val
            except Exception:
                payload[key] = repr(val)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str | int = "INFO") -> None:
    """Configure the root logger with the JSONFormatter.

    Args:
        level: Logging level name or numeric value. Defaults to "INFO".
    """
    root = logging.getLogger()
    # Clear existing handlers to avoid duplicate logs in long-running sessions
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root.addHandler(handler)
    numeric_level = level if isinstance(level, int) else logging.getLevelName(level)
    try:
        root.setLevel(numeric_level)
    except Exception:
        root.setLevel(logging.INFO)


__all__ = ["configure_logging", "JSONFormatter"]
