"""API key authentication provider."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from agent_gateway.auth.domain import ApiKeyRecord, AuthResult


def hash_api_key(raw: str) -> str:
    """Hash an API key using SHA-256. Returns hex digest."""
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiKeyProvider:
    """Validates Bearer tokens against hashed API keys.

    Keys are indexed by SHA-256 hash for O(1) lookup. Comparison uses
    hmac.compare_digest to prevent timing attacks.
    """

    def __init__(self, keys: list[ApiKeyRecord]) -> None:
        self._keys_by_hash: dict[str, ApiKeyRecord] = {k.key_hash: k for k in keys}

    async def authenticate(self, token: str) -> AuthResult:
        candidate_hash = hash_api_key(token)
        key = self._keys_by_hash.get(candidate_hash)
        if key is None:
            return AuthResult.denied("Invalid API key")
        # Timing-safe confirmation (prevents hash table timing leaks)
        if not hmac.compare_digest(candidate_hash, key.key_hash):
            return AuthResult.denied("Invalid API key")  # pragma: no cover
        if key.revoked:
            return AuthResult.denied("API key revoked")
        if key.expires_at and key.expires_at < datetime.now(UTC):
            return AuthResult.denied("API key expired")
        return AuthResult.ok(
            subject=key.name,
            scopes=key.scopes,
            method="api_key",
        )

    async def close(self) -> None:
        pass
