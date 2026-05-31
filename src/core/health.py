"""
Health check utilities for CryptoLaunchAgent.

Expose a small, deterministic health-check function used by the CLI and
(soon) by HTTP health endpoints. The function is intentionally side-effect
free and validates only configuration-level health (not external systems).
"""
from __future__ import annotations

from dataclasses import asdict
import json
import logging
from typing import Any

from config.settings import AppConfig


LOGGER = logging.getLogger(__name__)


def health_check(config: AppConfig) -> dict[str, Any]:
    """Return a serializable health dict for the current application state.

    This does not perform external I/O; it only verifies internal state
    such as configuration validity and application version availability.
    """
    try:
        # Validate configuration; this raises on failure
        config.validate()
        status = "ok"
    except Exception as exc:  # pragma: no cover - trivial wrapper
        LOGGER.exception("Startup validation failed during health check")
        status = "unhealthy"

    result = {
        "status": status,
        "config": {"env": config.env, "paper_trading": config.paper_trading},
        "version": config.app_version,
    }

    # Ensure result is JSON serializable
    json.dumps(result)
    return result


__all__ = ["health_check"]
