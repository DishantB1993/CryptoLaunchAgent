"""
Provider abstractions for blockchain connectivity.

This module defines interfaces for HTTP RPC and WebSocket providers. The
implementations are intentionally minimal stubs (scaffolding) that will be
extended in later phases. No network calls are made at this time.
"""
from __future__ import annotations

import abc
from typing import Any, AsyncIterator, Optional


class ProviderError(Exception):
    """Generic provider error."""


class Provider(abc.ABC):
    """Abstract provider interface for blockchain connections.

    Implementations should provide safe, non-blocking connect()/disconnect()
    methods and lightweight `call` for JSON-RPC requests.
    """

    @abc.abstractmethod
    def connect(self) -> None:
        """Establish any necessary connections. Non-blocking where possible."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Tear down connections and free resources."""

    @abc.abstractmethod
    def call(self, method: str, params: list[Any] | None = None, timeout: float | None = None) -> Any:
        """Perform a JSON-RPC call and return the parsed result.

        This method should raise `ProviderError` on failure.
        """


class HTTPProvider(Provider):
    """HTTP JSON-RPC provider interface (scaffold).

    Concrete implementations will perform `eth_chainId`, `eth_blockNumber`,
    and other read-only methods.
    """

    def __init__(self, rpc_url: str, timeout: float = 10.0) -> None:
        self.rpc_url = rpc_url
        self.timeout = timeout

    def connect(self) -> None:
        """HTTP provider requires no persistent connection by default."""
        return None

    def disconnect(self) -> None:
        return None

    def call(self, method: str, params: list[Any] | None = None, timeout: float | None = None) -> Any:
        raise ProviderError("HTTPProvider.call not implemented — this is a scaffold")


class WSProvider(Provider):
    """WebSocket provider interface (scaffold).

    Implementations will manage connection lifecycle and subscription
    streams.
    """

    def __init__(self, ws_url: str, timeout: float = 10.0) -> None:
        self.ws_url = ws_url
        self.timeout = timeout

    def connect(self) -> None:
        raise ProviderError("WSProvider.connect not implemented — this is a scaffold")

    def disconnect(self) -> None:
        raise ProviderError("WSProvider.disconnect not implemented — this is a scaffold")

    def call(self, method: str, params: list[Any] | None = None, timeout: float | None = None) -> Any:
        raise ProviderError("WSProvider.call not implemented — this is a scaffold")

    def subscribe(self) -> AsyncIterator[Any]:  # pragma: no cover - interface
        """Return an async iterator of subscription events."""
        raise ProviderError("WSProvider.subscribe not implemented — this is a scaffold")


__all__ = ["Provider", "HTTPProvider", "WSProvider", "ProviderError"]
