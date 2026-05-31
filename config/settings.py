"""
config/settings.py

Configuration placeholders for CryptoLaunchAgent (Phase 1).

This file should contain environment-agnostic defaults. Sensitive values
(e.g., private keys, API secrets) should be provided via environment
variables or a secrets manager in production — do NOT commit secrets.

No network/trading settings are active in Phase 1.
"""

from __future__ import annotations

# Example configuration values. Replace or extend in later phases.
ENV: str = "development"  # change to "production" in deployment
LOG_LEVEL: str = "INFO"

# BSC RPC placeholder — do NOT store secrets here.
BSC_RPC_URL: str | None = None  # set via environment in real deployments

# Paper-trading toggles (placeholder; no trading implemented here)
PAPER_TRADING: bool = True

# Data paths
DATA_DIR: str = "data"
LOGS_DIR: str = "logs"
