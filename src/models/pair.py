"""
Domain model for token pairs / liquidity pools.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Pair:
    """Represents a liquidity pair (e.g., PancakeSwap pair).

    Keep fields minimal to serve launch detection and liquidity checks.
    """

    address: str
    token0: str
    token1: str
    liquidity: Optional[float] = None
    created_at: datetime | None = None


__all__ = ["Pair"]
