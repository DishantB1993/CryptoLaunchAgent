"""
Minimal PancakeSwap API client scaffolding.

This client is a placeholder to centralize calls to PancakeSwap-related
logic (factory, router). It intentionally does not perform network calls
at this stage — methods are designed as stubs to be implemented later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class PairInfo:
    address: str
    token0: str
    token1: str


class PancakeClient:
    """Scaffold client for PancakeSwap factory/router interactions."""

    def __init__(self, factory_address: Optional[str] = None, router_address: Optional[str] = None) -> None:
        self.factory_address = factory_address
        self.router_address = router_address

    def get_pair_address(self, token_a: str, token_b: str) -> Optional[str]:
        """Return the pair address for `token_a` and `token_b` if known.

        This is a stub to be implemented with on-chain calls to the factory.
        """
        return None

    def get_pair_info(self, pair_address: str) -> Optional[PairInfo]:
        """Return basic pair information (token0/token1) for a pair.

        Stub implementation.
        """
        return None


__all__ = ["PancakeClient", "PairInfo"]
