"""Tests for exception hierarchy."""

from agent_gateway.exceptions import (
    AgentGatewayError,
    AuthError,
    ConfigError,
    ExecutionError,
    GuardrailTriggered,
    ToolError,
    WorkspaceError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self) -> None:
        assert issubclass(ConfigError, AgentGatewayError)
        assert issubclass(WorkspaceError, AgentGatewayError)
        assert issubclass(ExecutionError, AgentGatewayError)
        assert issubclass(ToolError, ExecutionError)
        assert issubclass(GuardrailTriggered, ExecutionError)
        assert issubclass(AuthError, AgentGatewayError)

    def test_workspace_error_has_path(self) -> None:
        err = WorkspaceError("bad file", path="/workspace/agents/foo/AGENT.md")
        assert err.path == "/workspace/agents/foo/AGENT.md"
        assert "bad file" in str(err)

    def test_tool_error_has_tool_name(self) -> None:
        err = ToolError("timeout", tool_name="companies-house-check", execution_id="exec_123")
        assert err.tool_name == "companies-house-check"
        assert err.execution_id == "exec_123"

    def test_guardrail_triggered(self) -> None:
        err = GuardrailTriggered(reason="max_iterations", partial_result="partial...")
        assert err.reason == "max_iterations"
        assert err.partial_result == "partial..."
        assert "Guardrail triggered" in str(err)

    def test_auth_error_has_code(self) -> None:
        err = AuthError("invalid key", code="invalid_api_key")
        assert err.code == "invalid_api_key"
