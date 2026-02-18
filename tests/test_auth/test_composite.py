"""Tests for the composite auth provider."""

from __future__ import annotations

from agent_gateway.auth.domain import AuthResult
from agent_gateway.auth.providers.composite import CompositeProvider


class _AlwaysOk:
    async def authenticate(self, token: str) -> AuthResult:
        return AuthResult.ok(subject="ok-provider", scopes=["*"], method="test")

    async def close(self) -> None:
        pass


class _AlwaysDenied:
    def __init__(self, error: str = "denied") -> None:
        self._error = error

    async def authenticate(self, token: str) -> AuthResult:
        return AuthResult.denied(self._error)

    async def close(self) -> None:
        pass


class _TrackingProvider:
    def __init__(self) -> None:
        self.closed = False

    async def authenticate(self, token: str) -> AuthResult:
        return AuthResult.denied("tracking")

    async def close(self) -> None:
        self.closed = True


class TestCompositeProvider:
    async def test_first_match_wins(self) -> None:
        provider = CompositeProvider([_AlwaysOk(), _AlwaysDenied()])
        result = await provider.authenticate("any-token")
        assert result.authenticated is True
        assert result.subject == "ok-provider"

    async def test_fallback_to_second(self) -> None:
        provider = CompositeProvider([_AlwaysDenied(), _AlwaysOk()])
        result = await provider.authenticate("any-token")
        assert result.authenticated is True

    async def test_all_fail_returns_last_error(self) -> None:
        provider = CompositeProvider(
            [
                _AlwaysDenied("error-1"),
                _AlwaysDenied("error-2"),
            ]
        )
        result = await provider.authenticate("any-token")
        assert result.authenticated is False
        assert result.error == "error-2"

    async def test_empty_providers(self) -> None:
        provider = CompositeProvider([])
        result = await provider.authenticate("any-token")
        assert result.authenticated is False
        assert "No auth providers configured" in result.error

    async def test_close_disposes_all(self) -> None:
        p1 = _TrackingProvider()
        p2 = _TrackingProvider()
        provider = CompositeProvider([p1, p2])  # type: ignore[list-item]
        await provider.close()
        assert p1.closed
        assert p2.closed
