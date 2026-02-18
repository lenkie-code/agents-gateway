"""API key authentication provider."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from agent_gateway.auth.domain import ApiKeyRecord, AuthResult


def hash_api_key(raw: str) -> str:
    """Hash an API key using SHA-256. Returns hex digest."""
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_api_key(prefix: str = "ag") -> tuple[str, str]:
    """Generate a new API key and its hash.

    Returns:
        Tuple of (raw_key, sha256_hash). The raw key is shown once to the
        caller; only the hash should be stored.
    """
    raw = f"{prefix}_{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw)


class ApiKeyProvider:
    """Validates Bearer tokens against hashed API keys.

    Keys are stored as SHA-256 hashes. Comparison uses hmac.compare_digest
    to prevent timing attacks.
    """

    def __init__(self, keys: list[ApiKeyRecord]) -> None:
        self._keys = keys

    async def authenticate(self, token: str) -> AuthResult:
        candidate_hash = hash_api_key(token)
        for key in self._keys:
            if key.revoked:
                continue
            if key.expires_at and key.expires_at < datetime.now(UTC):
                continue
            if hmac.compare_digest(candidate_hash, key.key_hash):
                return AuthResult.ok(
                    subject=key.name,
                    scopes=key.scopes,
                    method="api_key",
                )
        return AuthResult.denied("Invalid API key")

    async def close(self) -> None:
        pass
