"""
Model for simulated trades (paper trading).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Trade:
    """Represents a simulated trade event.

    No signing or private-key operations are performed in Phase 3.
    """

    trade_id: str
    token_address: str
    side: str  # 'buy' or 'sell'
    amount: float
    price: float
    simulated: bool = True
    timestamp: datetime | None = None


__all__ = ["Trade"]
