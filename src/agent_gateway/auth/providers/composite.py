"""Composite authentication provider — chains multiple providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_gateway.auth.domain import AuthResult

if TYPE_CHECKING:
    from agent_gateway.auth.protocols import AuthProvider


class CompositeProvider:
    """Tries multiple auth providers in order. First authenticated result wins.

    A 401 (authentication failure) triggers fallback to the next provider.
    Scopes are checked downstream, not by the provider.
    """

    def __init__(self, providers: list[AuthProvider]) -> None:
        self._providers = providers

    async def authenticate(self, token: str) -> AuthResult:
        last_error = "No auth providers configured"
        for provider in self._providers:
            result = await provider.authenticate(token)
            if result.authenticated:
                return result
            last_error = result.error or last_error
        return AuthResult.denied(last_error)

    async def close(self) -> None:
        for provider in self._providers:
            await provider.close()
