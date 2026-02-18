"""Null auth provider for when authentication is disabled.

Same interface as real providers, but always authenticates.
"""

from __future__ import annotations

from agent_gateway.auth.domain import AuthResult


class NullAuthProvider:
    """No-op auth provider — used when auth is disabled."""

    async def authenticate(self, token: str) -> AuthResult:
        return AuthResult.ok(subject="anonymous", scopes=["*"], method="none")

    async def close(self) -> None:
        pass
