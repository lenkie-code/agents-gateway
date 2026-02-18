"""Tests for the API key auth provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_gateway.auth.domain import ApiKeyRecord
from agent_gateway.auth.providers.api_key import ApiKeyProvider, hash_api_key


class TestHashHelpers:
    def test_hash_api_key_deterministic(self) -> None:
        assert hash_api_key("test-key") == hash_api_key("test-key")

    def test_hash_api_key_different_inputs(self) -> None:
        assert hash_api_key("key-a") != hash_api_key("key-b")


class TestApiKeyProvider:
    def _make_record(
        self,
        raw_key: str = "test-key-123",
        name: str = "test",
        scopes: list[str] | None = None,
        revoked: bool = False,
        expires_at: datetime | None = None,
    ) -> tuple[str, ApiKeyRecord]:
        return raw_key, ApiKeyRecord(
            id="1",
            name=name,
            key_hash=hash_api_key(raw_key),
            scopes=scopes or ["*"],
            revoked=revoked,
            expires_at=expires_at,
        )

    async def test_valid_key(self) -> None:
        raw, record = self._make_record()
        provider = ApiKeyProvider([record])
        result = await provider.authenticate(raw)
        assert result.authenticated is True
        assert result.subject == "test"
        assert result.scopes == ["*"]
        assert result.auth_method == "api_key"

    async def test_invalid_key(self) -> None:
        _, record = self._make_record()
        provider = ApiKeyProvider([record])
        result = await provider.authenticate("wrong-key")
        assert result.authenticated is False
        assert "Invalid API key" in result.error

    async def test_revoked_key(self) -> None:
        raw, record = self._make_record(revoked=True)
        provider = ApiKeyProvider([record])
        result = await provider.authenticate(raw)
        assert result.authenticated is False

    async def test_expired_key(self) -> None:
        raw, record = self._make_record(
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        provider = ApiKeyProvider([record])
        result = await provider.authenticate(raw)
        assert result.authenticated is False

    async def test_not_yet_expired_key(self) -> None:
        raw, record = self._make_record(
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        provider = ApiKeyProvider([record])
        result = await provider.authenticate(raw)
        assert result.authenticated is True

    async def test_custom_scopes(self) -> None:
        raw, record = self._make_record(scopes=["agents:read", "executions:read"])
        provider = ApiKeyProvider([record])
        result = await provider.authenticate(raw)
        assert result.scopes == ["agents:read", "executions:read"]

    async def test_multiple_keys(self) -> None:
        raw1, rec1 = self._make_record(raw_key="key-1", name="first")
        raw2, rec2 = self._make_record(raw_key="key-2", name="second")
        provider = ApiKeyProvider([rec1, rec2])

        r1 = await provider.authenticate(raw1)
        assert r1.subject == "first"

        r2 = await provider.authenticate(raw2)
        assert r2.subject == "second"

    async def test_close_is_noop(self) -> None:
        provider = ApiKeyProvider([])
        await provider.close()  # should not raise
