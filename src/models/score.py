"""
Token scoring result model.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass
class Score:
    """Represents a computed score for a token.

    `reasons` explains the major contributors to the score.
    """

    token_address: str
    score: float
    reasons: List[str]
    confidence: float = 0.0
    computed_at: datetime | None = None


__all__ = ["Score"]
