"""Tests for auth config and env var resolution."""

from __future__ import annotations

import pytest

from agent_gateway.config import _resolve_env_vars


class TestResolveEnvVars:
    def test_resolve_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_KEY", "secret-123")
        data: dict[str, object] = {"key": "${MY_KEY}"}
        _resolve_env_vars(data)
        assert data["key"] == "secret-123"

    def test_resolve_nested_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_URL", "postgres://localhost")
        data: dict[str, object] = {"auth": {"url": "${DB_URL}"}}
        _resolve_env_vars(data)
        assert data["auth"]["url"] == "postgres://localhost"  # type: ignore[index]

    def test_resolve_in_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KEY1", "val1")
        data: dict[str, object] = {"keys": ["${KEY1}", "literal"]}
        _resolve_env_vars(data)
        assert data["keys"] == ["val1", "literal"]  # type: ignore[comparison-overlap]

    def test_undefined_var_raises(self) -> None:
        data: dict[str, object] = {"key": "${UNDEFINED_VAR_12345}"}
        with pytest.raises(ValueError, match="UNDEFINED_VAR_12345"):
            _resolve_env_vars(data)

    def test_no_vars_unchanged(self) -> None:
        data: dict[str, object] = {"key": "plain-value", "num": 42}
        _resolve_env_vars(data)
        assert data["key"] == "plain-value"
        assert data["num"] == 42

    def test_partial_replacement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOST", "localhost")
        data: dict[str, object] = {"url": "http://${HOST}:8080"}
        _resolve_env_vars(data)
        assert data["url"] == "http://localhost:8080"
