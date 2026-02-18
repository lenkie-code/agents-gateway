"""Protocol definitions for authentication providers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_gateway.auth.domain import AuthResult


@runtime_checkable
class AuthProvider(Protocol):
    """Contract for pluggable auth providers.

    Implementations must validate bearer tokens and manage their own resources.
    Satisfied structurally (duck typing) — no inheritance required.
    """

    async def authenticate(self, token: str) -> AuthResult:
        """Validate a bearer token and return an AuthResult."""
        ...

    async def close(self) -> None:
        """Release resources (HTTP clients, DB connections, etc.)."""
        ...
