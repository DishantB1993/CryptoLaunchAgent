"""
Domain models for tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass
class Token:
    """Represents a token contract on BSC.

    Fields are deliberately minimal; extend as needed.
    """

    address: str
    name: Optional[str] = None
    symbol: Optional[str] = None
    decimals: Optional[int] = None
    metadata: Dict[str, str] | None = None
    created_at: datetime | None = None


__all__ = ["Token"]
