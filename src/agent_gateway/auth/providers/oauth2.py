"""OAuth2/OIDC JWT authentication provider.

Validates JWT access tokens against an OAuth2 provider's JWKS endpoint.
Requires: pip install agent-gateway[oauth2]
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agent_gateway.auth.domain import AuthResult

logger = logging.getLogger(__name__)

# Only allow asymmetric algorithms — reject 'none' and HS* (symmetric)
_ALLOWED_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"})

_DEFAULT_JWKS_TTL = 3600.0  # 1 hour


@dataclass
class _JWKSCache:
    """Cached JWKS keys with TTL-based refresh."""

    keys: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: float = 0.0
    ttl: float = _DEFAULT_JWKS_TTL

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.fetched_at > self.ttl


class OAuth2Provider:
    """Validates JWT access tokens using JWKS from an OAuth2/OIDC provider.

    Requires: pip install agent-gateway[oauth2]
    """

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_uri: str | None = None,
        algorithms: list[str] | None = None,
        scope_claim: str = "scope",
        clock_skew_seconds: int = 30,
    ) -> None:
        try:
            import jwt  # noqa: F401
        except ImportError:
            raise ImportError(
                "OAuth2 provider requires the oauth2 extra: pip install agent-gateway[oauth2]"
            ) from None

        requested = set(algorithms or ["RS256", "ES256"])
        invalid = requested - _ALLOWED_ALGORITHMS
        if invalid:
            raise ValueError(
                f"Disallowed JWT algorithms: {invalid}. "
                f"Only asymmetric algorithms are permitted: {sorted(_ALLOWED_ALGORITHMS)}"
            )

        self._issuer = issuer
        self._audience = audience
        self._jwks_uri = jwks_uri or f"{issuer.rstrip('/')}/.well-known/jwks.json"
        self._algorithms = list(requested)
        self._scope_claim = scope_claim
        self._clock_skew = clock_skew_seconds
        self._cache = _JWKSCache()
        self._lock = asyncio.Lock()

        import httpx

        self._http = httpx.AsyncClient(timeout=10.0)

    async def authenticate(self, token: str) -> AuthResult:
        """Validate JWT: signature, expiry, issuer, audience, then extract scopes."""
        import jwt as pyjwt

        try:
            header = pyjwt.get_unverified_header(token)
        except pyjwt.exceptions.DecodeError:
            return AuthResult.denied("Invalid token format")

        kid = header.get("kid")
        if not kid:
            return AuthResult.denied("Token missing 'kid' header")

        alg = header.get("alg", "")
        if alg not in _ALLOWED_ALGORITHMS:
            return AuthResult.denied(f"Disallowed algorithm: {alg}")

        # Try with cached JWKS first, retry with fresh on failure
        for attempt in range(2):
            try:
                keys = await self._get_jwks(force_refresh=(attempt == 1))
                public_key = self._find_key(kid, keys)
                claims = pyjwt.decode(
                    token,
                    key=public_key,
                    algorithms=self._algorithms,
                    audience=self._audience,
                    issuer=self._issuer,
                    leeway=self._clock_skew,
                    options={"require": ["exp", "iss", "aud"]},
                )
                return self._claims_to_result(claims)
            except KeyError:
                if attempt == 0:
                    continue  # retry with fresh JWKS (key rotation)
                return AuthResult.denied(f"No JWKS key matching kid={kid}")
            except pyjwt.ExpiredSignatureError:
                return AuthResult.denied("Token expired")
            except pyjwt.InvalidAudienceError:
                return AuthResult.denied("Invalid audience")
            except pyjwt.InvalidIssuerError:
                return AuthResult.denied("Invalid issuer")
            except pyjwt.PyJWTError as exc:
                return AuthResult.denied(str(exc))
            except Exception as exc:
                logger.warning("OAuth2 auth error: %s", exc, exc_info=True)
                return AuthResult.denied("Authentication failed")

        return AuthResult.denied("Authentication failed")  # pragma: no cover

    def _claims_to_result(self, claims: dict[str, Any]) -> AuthResult:
        """Extract scopes and subject from JWT claims."""
        raw_scopes = claims.get(self._scope_claim, "")
        scopes = raw_scopes.split() if isinstance(raw_scopes, str) else list(raw_scopes)
        subject = claims.get("sub", "unknown")

        # Pass through non-standard claims
        extra = {k: v for k, v in claims.items() if k not in ("sub", self._scope_claim)}

        return AuthResult.ok(
            subject=subject,
            scopes=scopes,
            method="oauth2",
            **extra,
        )

    async def _get_jwks(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Fetch JWKS keys with caching and lock to prevent thundering herd."""
        if not force_refresh and not self._cache.expired:
            return self._cache.keys

        async with self._lock:
            # Double-check after acquiring lock
            if not force_refresh and not self._cache.expired:
                return self._cache.keys

            try:
                resp = await self._http.get(self._jwks_uri)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                keys: list[dict[str, Any]] = data.get("keys", [])
                self._cache = _JWKSCache(keys=keys, fetched_at=time.monotonic())
                return keys
            except Exception:
                # On fetch failure, use stale cache if available
                if self._cache.keys:
                    logger.warning(
                        "JWKS fetch failed, using stale cache (%d keys)",
                        len(self._cache.keys),
                    )
                    return self._cache.keys
                raise

    @staticmethod
    def _find_key(kid: str, keys: list[dict[str, Any]]) -> Any:
        """Find a JWKS key by kid and convert to a public key."""
        import jwt as pyjwt

        for key_data in keys:
            if key_data.get("kid") == kid:
                alg = key_data.get("alg", key_data.get("kty", ""))
                if alg.startswith("EC") or key_data.get("kty") == "EC":
                    return pyjwt.algorithms.ECAlgorithm(
                        pyjwt.algorithms.ECAlgorithm.SHA256
                    ).from_jwk(key_data)
                return pyjwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        raise KeyError(kid)

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._http.aclose()
