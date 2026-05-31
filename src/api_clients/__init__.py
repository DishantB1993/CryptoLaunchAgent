"""
API clients for third-party services.

Clients are lightweight wrappers around HTTP endpoints and should avoid
holding API keys in code. They can be extended to add retries/backoff.
"""

__all__ = ["pancake"]
