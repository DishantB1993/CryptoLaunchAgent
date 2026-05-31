#!/usr/bin/env python3
"""
CryptoLaunchAgent CLI and startup wiring (Phase 2 infrastructure).

This module provides a small CLI with subcommands for:
- `health` - run an internal health check and emit JSON
- `version` - print the application version
- `check-config` - validate configuration and report issues

It also performs startup validation, config loading from the environment,
and structured logging initialization.

This file intentionally implements no trading, blockchain, websocket,
database, or UI logic (per Phase 2 rules).
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from typing import Any

from config.settings import AppConfig
from src.core.logging_config import configure_logging
from src.core.version import get_version
from src.core.health import health_check


MIN_PY = (3, 12)


def _install_signal_handlers(stop_event: dict[str, bool]) -> None:
    """Install signal handlers that set `stop_event['stop'] = True`.

    This is a minimal graceful-shutdown helper useful for future long-
    running services. For CLI commands that complete quickly it's a no-op
    but it documents the intended pattern.
    """

    def _handler(signum, frame):  # pragma: no cover - signal wiring
        logging.getLogger(__name__).info("Received signal %s, shutting down", signum)
        stop_event["stop"] = True

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def run_health(config: AppConfig) -> int:
    """Run health check and print JSON result to stdout.

    Returns an OS exit code (0 == healthy, 2 == unhealthy).
    """
    result = health_check(config)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "ok" else 2


def run_version() -> int:
    """Print the application version and exit."""
    print(get_version())
    return 0


def run_check_config(config: AppConfig) -> int:
    """Validate configuration and report issues on stderr; return exit code."""
    try:
        config.validate()
        print("OK: configuration validated")
        return 0
    except Exception as exc:
        logging.getLogger(__name__).exception("Configuration validation failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CryptoLaunchAgent CLI (Phase 2)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("health", help="Run internal health checks and output JSON")
    sub.add_parser("version", help="Print application version")
    sub.add_parser("check-config", help="Validate application configuration")

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if sys.version_info < MIN_PY:
        sys.exit(f"Python {MIN_PY[0]}.{MIN_PY[1]}+ is required. You are running {sys.version_info.major}.{sys.version_info.minor}.")

    # Load configuration from env and initialize structured logging
    config = AppConfig.from_env()
    configure_logging(config.log_level)

    parser = _build_parser()
    args = parser.parse_args(argv)

    # Install graceful shutdown handlers
    stop_event: dict[str, bool] = {"stop": False}
    _install_signal_handlers(stop_event)

    try:
        if args.command == "health":
            return run_health(config)
        if args.command == "version":
            return run_version()
        if args.command == "check-config":
            return run_check_config(config)

        # Default behaviour: show help
        parser.print_help()
        return 0
    except Exception as exc:  # pragma: no cover - top-level safety net
        logging.getLogger(__name__).exception("Unhandled error during CLI execution")
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
