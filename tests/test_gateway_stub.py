"""Tests for the Gateway stub."""

from agent_gateway import Gateway, __version__


class TestGatewayStub:
    def test_gateway_is_fastapi(self) -> None:
        from fastapi import FastAPI

        gw = Gateway()
        assert isinstance(gw, FastAPI)

    def test_gateway_default_params(self) -> None:
        gw = Gateway()
        assert gw._workspace_path == "./workspace"
        assert gw._auth_enabled is True
        assert gw._reload_enabled is False

    def test_gateway_custom_params(self) -> None:
        gw = Gateway(workspace="./my-agents", auth=False, reload=True, title="Test")
        assert gw._workspace_path == "./my-agents"
        assert gw._auth_enabled is False
        assert gw._reload_enabled is True
        assert gw.title == "Test"

    def test_version(self) -> None:
        assert __version__ == "0.1.0"
