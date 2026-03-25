"""Unit tests for the companies-house-search tool handler."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

# Load the handler module directly from the example project workspace so these
# tests work without installing anything extra.
_HANDLER_PATH = (
    Path(__file__).parent.parent.parent
    / "examples"
    / "test-project"
    / "workspace"
    / "tools"
    / "companies-house-search"
    / "handler.py"
)

_MODULE_NAME = "ch_search_handler"


def _load_handler() -> Any:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HANDLER_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register on sys.modules so patch() can resolve it by name
    sys.modules[_MODULE_NAME] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load_handler()
handle = _mod.handle
_build_params = _mod._build_params


# ---------------------------------------------------------------------------
# _build_params helpers
# ---------------------------------------------------------------------------


class TestBuildParams:
    def test_defaults_to_active_status(self) -> None:
        params = _build_params({})
        assert "statuses=Active" in params

    def test_no_default_status_when_company_number_given(self) -> None:
        params = _build_params({"company_number": "12345678"})
        assert "statuses" not in params
        assert "company_number=12345678" in params

    def test_custom_statuses_override_default(self) -> None:
        params = _build_params({"statuses": ["Active", "Liquidation"]})
        assert "statuses=Active" in params
        assert "statuses=Liquidation" in params

    def test_sic_codes_repeated(self) -> None:
        params = _build_params({"sic_codes": ["86230", "86210"]})
        assert "sic_codes=86230" in params
        assert "sic_codes=86210" in params

    def test_sic_codes_comma_string(self) -> None:
        params = _build_params({"sic_codes": "86230,86210"})
        assert "sic_codes=86230" in params
        assert "sic_codes=86210" in params

    def test_date_params_included(self) -> None:
        params = _build_params(
            {"incorporation_date_from": "2000-01-01", "incorporation_date_to": "2020-01-01"}
        )
        assert "incorporation_date_from=2000-01-01" in params
        assert "incorporation_date_to=2020-01-01" in params

    def test_pagination_params(self) -> None:
        params = _build_params({"page_number": 2, "page_size": 50})
        assert "page_number=2" in params
        assert "page_size=50" in params


# ---------------------------------------------------------------------------
# handle() — happy path
# ---------------------------------------------------------------------------


class TestHandleHappyPath:
    def test_returns_parsed_json_on_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {"items": [{"company_name": "Acme Dental Ltd"}], "total_count": 1}

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        monkeypatch.setenv("CORE_API_URL", "https://api.example.com")
        with patch(f"{_mod.__name__}.urlopen", return_value=mock_resp):
            result = handle({"sic_codes": ["86230"]}, context=None)

        assert result == payload

    def test_appends_active_status_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured_url: list[str] = []

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"items": []}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        def fake_urlopen(req: Any, timeout: int) -> Any:
            captured_url.append(req.full_url)
            return mock_resp

        monkeypatch.setenv("CORE_API_URL", "https://api.example.com")
        with patch(f"{_mod.__name__}.urlopen", side_effect=fake_urlopen):
            handle({}, context=None)

        assert "statuses=Active" in captured_url[0]


# ---------------------------------------------------------------------------
# handle() — error paths
# ---------------------------------------------------------------------------


class TestHandleErrors:
    def test_missing_env_var_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CORE_API_URL", raising=False)
        result = handle({}, context=None)
        assert "error" in result
        assert "CORE_API_URL" in result["error"]

    def test_http_error_returns_error_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORE_API_URL", "https://api.example.com")
        http_err = HTTPError(
            url="https://api.example.com/lookups/companies-house-directory",
            code=422,
            msg="Unprocessable Entity",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=io.BytesIO(b'{"detail": "invalid sic code"}'),
        )
        with patch(f"{_mod.__name__}.urlopen", side_effect=http_err):
            result = handle({"sic_codes": ["INVALID"]}, context=None)

        assert "error" in result
        assert "422" in result["error"]

    def test_url_error_returns_error_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORE_API_URL", "https://api.example.com")
        with patch(f"{_mod.__name__}.urlopen", side_effect=URLError("connection refused")):
            result = handle({}, context=None)

        assert "error" in result
        assert "connection" in result["error"].lower()

    def test_http_error_includes_detail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CORE_API_URL", "https://api.example.com")
        http_err = HTTPError(
            url="https://api.example.com/lookups/companies-house-directory",
            code=500,
            msg="Internal Server Error",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=io.BytesIO(b"server exploded"),
        )
        with patch(f"{_mod.__name__}.urlopen", side_effect=http_err):
            result = handle({}, context=None)

        assert result.get("detail") == "server exploded"
