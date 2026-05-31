"""
Model for paper-trading positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Position:
    """Represents an open or closed position in the simulated portfolio."""

    token_address: str
    amount: float
    entry_price: float
    pnl: float = 0.0
    opened_at: datetime | None = None
    closed_at: Optional[datetime] = None


__all__ = ["Position"]
