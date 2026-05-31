"""
Scaffolding for launch detection scanner.

The scanner will be responsible for discovering new pairs and liquidity
adds. This module currently provides a minimal `Scanner` interface and
no active scanning logic (scaffold only).
"""
from __future__ import annotations

import logging
from typing import Optional

from src.blockchain.provider import HTTPProvider
from src.api_clients.pancake import PancakeClient


LOGGER = logging.getLogger(__name__)


class Scanner:
    """Scanner for new token launches and liquidity events.

    The scanner is constructed with a blockchain provider and API clients
    but does not start any network activity until `start()` is called.
    """

    def __init__(self, provider: HTTPProvider, pancake: PancakeClient) -> None:
        self.provider = provider
        self.pancake = pancake
        self._running = False

    def start(self) -> None:
        """Start the scanner (non-blocking)."""
        LOGGER.info("Scanner start requested")
        self._running = True

    def stop(self) -> None:
        """Stop the scanner and release resources."""
        LOGGER.info("Scanner stop requested")
        self._running = False

    def scan_once(self) -> None:
        """Run a single scan iteration (synchronous stub)."""
        LOGGER.debug("Scanner scan_once called — stub implementation")
        # TODO: implement pair discovery and liquidity detection
        return None


__all__ = ["Scanner"]
