"""
PancakeSwap API client using on-chain contract calls via a Provider.

This client uses the provided `HTTPProvider` (which wraps Web3) to
interact with the PancakeSwap factory contract and fetch pair addresses
and basic pair info via contract calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.blockchain.provider import HTTPProvider, ProviderError

# Minimal ABI fragment for Pancake factory's `getPair(address,address)`
FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]


@dataclass
class PairInfo:
    address: str
    token0: str
    token1: str


class PancakeClient:
    """Client to interact with PancakeSwap factory/router via a provider.

    The client requires an `HTTPProvider` instance that is already
    connected (i.e. `provider.connect()` has been called).
    """

    def __init__(self, provider: HTTPProvider, factory_address: Optional[str] = None, router_address: Optional[str] = None) -> None:
        if not provider:
            raise ValueError("provider is required")
        self.provider = provider
        self.factory_address = factory_address
        self.router_address = router_address

    def get_pair_address(self, token_a: str, token_b: str) -> Optional[str]:
        """Return the pair address for `token_a` and `token_b` using the factory.

        This method uses Web3 contract call via the provider. Returns the
        zero address or `None` if not found or on error.
        """
        if not self.factory_address:
            raise ValueError("factory_address is not configured")
        if not getattr(self.provider, "w3", None):
            raise ProviderError("Provider does not have an active Web3 instance")

        try:
            contract = self.provider.w3.eth.contract(address=self.factory_address, abi=FACTORY_ABI)
            pair_addr = contract.functions.getPair(token_a, token_b).call()
            if not pair_addr or int(pair_addr, 16) == 0:
                return None
            return self.provider.w3.to_checksum_address(pair_addr)
        except Exception as exc:
            raise ProviderError(f"Failed to get pair address: {exc}") from exc

    def get_pair_info(self, pair_address: str) -> Optional[PairInfo]:
        """Return basic pair information (token0/token1) for a pair.

        This method uses the pair contract's basic `token0`/`token1` calls.
        For now we perform a lightweight, best-effort query.
        """
        if not getattr(self.provider, "w3", None):
            raise ProviderError("Provider does not have an active Web3 instance")

        try:
            # Minimal ABI for token0/token1
            PAIR_ABI = [
                {"inputs": [], "name": "token0", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
                {"inputs": [], "name": "token1", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
            ]
            contract = self.provider.w3.eth.contract(address=pair_address, abi=PAIR_ABI)
            t0 = contract.functions.token0().call()
            t1 = contract.functions.token1().call()
            return PairInfo(address=pair_address, token0=self.provider.w3.to_checksum_address(t0), token1=self.provider.w3.to_checksum_address(t1))
        except Exception:
            return None

    def get_all_pairs_length(self) -> Optional[int]:
        """Return the total number of pairs (`allPairsLength`) from the factory.

        Returns `None` on error.
        """
        if not self.factory_address:
            raise ValueError("factory_address is not configured")
        if not getattr(self.provider, "w3", None):
            raise ProviderError("Provider does not have an active Web3 instance")

        try:
            FACTORY_ABI_LEN = [
                {"inputs": [], "name": "allPairsLength", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}
            ]
            contract = self.provider.w3.eth.contract(address=self.factory_address, abi=FACTORY_ABI_LEN)
            length = contract.functions.allPairsLength().call()
            return int(length)
        except Exception:
            return None


__all__ = ["PancakeClient", "PairInfo"]
