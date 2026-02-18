"""Pluggable authentication for the Agent Gateway."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent_gateway.auth.domain import AuthResult
from agent_gateway.auth.protocols import AuthProvider

__all__ = ["AuthProvider", "AuthResult", "CallableAuthProvider"]


class CallableAuthProvider:
    """Adapter that wraps an async callable as an AuthProvider."""

    def __init__(self, fn: Callable[..., Awaitable[Any]]) -> None:
        self._fn = fn

    async def authenticate(self, token: str) -> AuthResult:
        result: object = await self._fn(token)
        if isinstance(result, AuthResult):
            return result
        return AuthResult.denied("Custom auth returned non-AuthResult")

    async def close(self) -> None:
        pass
