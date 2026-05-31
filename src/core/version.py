"""
Application version helper.

Provides a single source of truth for the application version. The
recommended workflow is to update the top-level `VERSION` file when
releasing a new version, and `get_version()` will read it.
"""
from __future__ import annotations

from pathlib import Path


def get_version() -> str:
    """Return the application version as a string.

    If the `VERSION` file is missing, return a sensible default.
    """
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return version_file.read_text(encoding="utf8").strip()
    except Exception:
        return "0.0.0"


__all__ = ["get_version"]
