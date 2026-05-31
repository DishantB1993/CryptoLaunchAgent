"""
Exponential backoff utilities.

Provide a simple, dependency-free exponential backoff generator with
optional full-jitter. This is intentionally small and synchronous; callers
may `await asyncio.sleep(delay)` when used in async code.
"""
from __future__ import annotations

import random
from typing import Iterator


def exponential_backoff(initial: float = 1.0, factor: float = 2.0, max_delay: float = 60.0, jitter: float = 0.1) -> Iterator[float]:
    """Yield delays for exponential backoff with optional jitter.

    Args:
        initial: initial delay in seconds.
        factor: multiplicative factor applied each retry.
        max_delay: maximum delay to cap at.
        jitter: fractional jitter to apply (0.0 = no jitter, 0.1 = ±10%).

    Yields:
        Next delay in seconds.
    """
    delay = float(initial)
    while True:
        if jitter and jitter > 0:
            jitter_frac = random.uniform(-jitter, jitter)
            yield max(0.0, min(max_delay, delay * (1 + jitter_frac)))
        else:
            yield max(0.0, min(max_delay, delay))
        delay = min(max_delay, delay * factor)


__all__ = ["exponential_backoff"]
