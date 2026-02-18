"""Plain domain dataclasses for authentication — zero framework dependencies.

These types are the public interface for all auth operations.
They are always importable from the core package without any optional extras.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AuthResult:
    """Outcome of an authentication attempt."""

    authenticated: bool
    subject: str = ""
    scopes: list[str] = field(default_factory=list)
    auth_method: str = ""  # "api_key", "oauth2", "custom"
    claims: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @classmethod
    def ok(
        cls,
        subject: str,
        scopes: list[str],
        method: str,
        **claims: Any,
    ) -> AuthResult:
        """Create a successful auth result."""
        return cls(
            authenticated=True,
            subject=subject,
            scopes=scopes,
            auth_method=method,
            claims=claims,
        )

    @classmethod
    def denied(cls, error: str = "Access denied") -> AuthResult:
        """Create a failed auth result."""
        return cls(authenticated=False, error=error)


@dataclass
class ApiKeyRecord:
    """Stored API key (hashed, never plaintext)."""

    id: str
    name: str
    key_hash: str  # SHA-256 hex digest
    scopes: list[str] = field(default_factory=lambda: ["*"])
    expires_at: datetime | None = None
    revoked: bool = False
