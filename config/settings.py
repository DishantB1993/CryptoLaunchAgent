"""
config/settings.py

Typed configuration and environment-loading helpers for CryptoLaunchAgent.

This module provides a dataclass `AppConfig` that is populated from
environment variables (and optionally a local `.env` file during
development). It also provides a small `validate()` method to check for
obvious misconfiguration during startup.

Rules:
- Do NOT store secrets in this file. Use environment variables or a
  secrets manager for production deployments.
- This module intentionally contains no network or blockchain logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

# Local development convenience: load a .env file if present. This is
# optional in production where environment variables are supplied by
# the runtime environment (containers, systemd, CI, etc.).
try:
	from dotenv import load_dotenv

	load_dotenv()
except Exception:
	# If python-dotenv is not installed, skip local .env loading. The
	# `requirements.txt` includes `python-dotenv` for local development.
	pass


@dataclass
class AppConfig:
	"""Typed application configuration.

	Attributes correspond to commonly-used runtime options. Use the
	`from_env()` constructor to create an instance from environment
	variables.
	"""

	env: str = os.getenv("ENV", "development")
	log_level: str = os.getenv("LOG_LEVEL", "INFO")
	bsc_rpc_url: Optional[str] = os.getenv("BSC_RPC_URL")
	paper_trading: bool = os.getenv("PAPER_TRADING", "true").lower() in (
		"1",
		"true",
		"yes",
	)
	data_dir: str = os.getenv("DATA_DIR", "data")
	logs_dir: str = os.getenv("LOGS_DIR", "logs")
	app_version: str = os.getenv("APP_VERSION", "0.0.0")

	@classmethod
	def from_env(cls) -> "AppConfig":
		"""Create an `AppConfig` populated from environment variables.

		Use this during application startup to centralize configuration
		handling for the app.
		"""

		return cls()

	def validate(self) -> None:
		"""Validate basic invariants and raise ValueError on failure.

		This helps catch obvious misconfiguration early during startup
		(for example, invalid environment names or log levels).
		"""

		if self.env not in ("development", "production"):
			raise ValueError("ENV must be 'development' or 'production'")

		allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
		if self.log_level.upper() not in allowed_levels:
			raise ValueError("LOG_LEVEL must be one of: " + ", ".join(sorted(allowed_levels)))


__all__ = ["AppConfig"]
