"""
Provider abstractions for blockchain connectivity.

This module implements simple provider wrappers around `web3` providers
to perform JSON-RPC calls and lightweight websocket subscriptions.

The implementations are minimal but functional: `HTTPProvider` exposes
`connect()`, `disconnect()`, and `call()` using `web3`. `WSProvider` is
provided as a thin wrapper for future extension.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

from web3 import Web3
from web3.exceptions import Web3Exception
from web3.providers import HTTPProvider as W3HTTPProvider, WebsocketProvider as W3WebsocketProvider


LOGGER = logging.getLogger(__name__)


class ProviderError(Exception):
    """Generic provider error."""


class Provider:
    """Base provider abstraction exposing a `call` method backed by Web3."""

    w3: Optional[Web3]

    def connect(self) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def call(self, method: str, params: list[Any] | None = None, timeout: float | None = None) -> Any:
        raise NotImplementedError


class HTTPProvider(Provider):
    """HTTP JSON-RPC provider backed by `web3`.

    This provider performs synchronous JSON-RPC calls via Web3's
    `manager.request_blocking` and exposes a `w3` instance for higher
    level helpers (contract calls, encoding).
    """

    def __init__(self, rpc_url: str, timeout: float = 10.0) -> None:
        self.rpc_url = rpc_url
        self.timeout = timeout
        self.w3: Optional[Web3] = None

    def connect(self) -> None:
        try:
            provider = W3HTTPProvider(self.rpc_url, request_kwargs={"timeout": int(self.timeout)})
            self.w3 = Web3(provider)
            # Simple connectivity assertion
            if not self.w3.is_connected():
                raise ProviderError(f"Unable to connect to RPC at {self.rpc_url}")
        except Web3Exception as exc:
            raise ProviderError(str(exc)) from exc

    def disconnect(self) -> None:
        # HTTP provider uses short-lived connections; nothing to do
        self.w3 = None

    def call(self, method: str, params: list[Any] | None = None, timeout: float | None = None) -> Any:
        if not self.w3:
            raise ProviderError("Provider is not connected")
        try:
            # web3 manager.request_blocking performs the JSON-RPC call
            return self.w3.manager.request_blocking(method, params or [])
        except Web3Exception as exc:
            raise ProviderError(str(exc)) from exc


class WSProvider(Provider):
    """WebSocket provider wrapper using `web3`'s WebsocketProvider.

    Note: this is a minimal wrapper. For subscription handling and
    async iteration a higher-level async implementation will be added
    in later phases.
    """

    def __init__(self, ws_url: str, timeout: float = 10.0) -> None:
        self.ws_url = ws_url
        self.timeout = timeout
        self.w3: Optional[Web3] = None

    def connect(self) -> None:
        try:
            provider = W3WebsocketProvider(self.ws_url)
            self.w3 = Web3(provider)
            if not self.w3.is_connected():
                raise ProviderError(f"Unable to connect to WS at {self.ws_url}")
        except Web3Exception as exc:
            raise ProviderError(str(exc)) from exc

    def disconnect(self) -> None:
        # web3 websocket provider does not expose explicit close API in all transports
        self.w3 = None

    def call(self, method: str, params: list[Any] | None = None, timeout: float | None = None) -> Any:
        if not self.w3:
            raise ProviderError("WSProvider is not connected")
        try:
            return self.w3.manager.request_blocking(method, params or [])
        except Web3Exception as exc:
            raise ProviderError(str(exc)) from exc

    def subscribe(self) -> AsyncIterator[Any]:  # pragma: no cover - scaffold
        raise ProviderError("WSProvider.subscribe is not yet implemented")


__all__ = ["Provider", "HTTPProvider", "WSProvider", "ProviderError"]
