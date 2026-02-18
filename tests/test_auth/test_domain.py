"""Tests for auth domain types."""

from __future__ import annotations

from agent_gateway.auth.domain import ApiKeyRecord, AuthResult


class TestAuthResult:
    def test_ok_factory(self) -> None:
        result = AuthResult.ok(subject="user", scopes=["*"], method="api_key")
        assert result.authenticated is True
        assert result.subject == "user"
        assert result.scopes == ["*"]
        assert result.auth_method == "api_key"
        assert result.error == ""

    def test_ok_with_claims(self) -> None:
        result = AuthResult.ok(subject="u", scopes=[], method="oauth2", iss="https://a.com")
        assert result.claims == {"iss": "https://a.com"}

    def test_denied_factory(self) -> None:
        result = AuthResult.denied("bad key")
        assert result.authenticated is False
        assert result.error == "bad key"
        assert result.subject == ""
        assert result.scopes == []

    def test_denied_default_message(self) -> None:
        result = AuthResult.denied()
        assert result.error == "Access denied"

    def test_frozen(self) -> None:
        result = AuthResult.ok(subject="u", scopes=["*"], method="api_key")
        import pytest

        with pytest.raises(AttributeError):
            result.subject = "other"  # type: ignore[misc]


class TestApiKeyRecord:
    def test_defaults(self) -> None:
        rec = ApiKeyRecord(id="1", name="test", key_hash="abc", key_prefix="ag_12345")
        assert rec.scopes == ["*"]
        assert rec.revoked is False
        assert rec.expires_at is None
