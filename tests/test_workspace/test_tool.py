"""Tests for tool model loading."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.workspace.tool import ToolDefinition


class TestToolDefinition:
    def test_load_function_tool(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "echo"
        tool_dir.mkdir()
        (tool_dir / "TOOL.md").write_text(
            "---\n"
            "name: echo\n"
            "description: Echo the input back\n"
            "type: function\n"
            "parameters:\n"
            "  message:\n"
            "    type: string\n"
            "    description: Message to echo\n"
            "    required: true\n"
            "---\n"
            "# Echo Tool\n\nReturns input unchanged."
        )

        tool = ToolDefinition.load(tool_dir)
        assert tool is not None
        assert tool.id == "echo"
        assert tool.name == "echo"
        assert tool.type == "function"
        assert len(tool.parameters) == 1
        assert tool.parameters[0].name == "message"
        assert tool.parameters[0].required is True
        assert tool.handler_path is None  # No handler.py

    def test_load_function_tool_with_handler(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "compute"
        tool_dir.mkdir()
        (tool_dir / "TOOL.md").write_text(
            "---\nname: compute\ndescription: Compute things\ntype: function\n---\n# Compute"
        )
        (tool_dir / "handler.py").write_text("def handle(args): return args")

        tool = ToolDefinition.load(tool_dir)
        assert tool is not None
        assert tool.handler_path == tool_dir / "handler.py"

    def test_load_http_tool(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "api-call"
        tool_dir.mkdir()
        (tool_dir / "TOOL.md").write_text(
            "---\n"
            "name: api-call\n"
            "description: Call an API\n"
            "type: http\n"
            "http:\n"
            "  method: POST\n"
            "  url: https://api.example.com/data\n"
            "  headers:\n"
            "    Authorization: Bearer ${API_KEY}\n"
            "  timeout_ms: 10000\n"
            "parameters:\n"
            "  query:\n"
            "    type: string\n"
            "    description: Search query\n"
            "    required: true\n"
            "---\n"
            "# API Call Tool"
        )

        tool = ToolDefinition.load(tool_dir)
        assert tool is not None
        assert tool.type == "http"
        assert tool.http is not None
        assert tool.http.method == "POST"
        assert tool.http.url == "https://api.example.com/data"
        assert tool.http.timeout_ms == 10000
        assert "Authorization" in tool.http.headers

    def test_load_script_tool(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "runner"
        tool_dir.mkdir()
        (tool_dir / "TOOL.md").write_text(
            "---\n"
            "name: runner\n"
            "description: Run a script\n"
            "type: script\n"
            "script:\n"
            "  command: python process.py\n"
            "  timeout_ms: 60000\n"
            "---\n"
            "# Script Runner"
        )

        tool = ToolDefinition.load(tool_dir)
        assert tool is not None
        assert tool.type == "script"
        assert tool.script is not None
        assert tool.script.command == "python process.py"
        assert tool.script.timeout_ms == 60000

    def test_missing_tool_md_returns_none(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "no-tool"
        tool_dir.mkdir()
        assert ToolDefinition.load(tool_dir) is None

    def test_parameter_with_enum(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "choice"
        tool_dir.mkdir()
        (tool_dir / "TOOL.md").write_text(
            "---\n"
            "name: choice\n"
            "description: Pick one\n"
            "parameters:\n"
            "  color:\n"
            "    type: string\n"
            "    description: Pick a color\n"
            "    enum:\n      - red\n      - blue\n      - green\n"
            "---\n# Choice"
        )

        tool = ToolDefinition.load(tool_dir)
        assert tool is not None
        assert tool.parameters[0].enum == ["red", "blue", "green"]

    def test_parameter_with_default(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "default-param"
        tool_dir.mkdir()
        (tool_dir / "TOOL.md").write_text(
            "---\n"
            "name: default-param\n"
            "description: Has default\n"
            "parameters:\n"
            "  count:\n"
            "    type: integer\n"
            "    description: Number of items\n"
            "    default: 10\n"
            "---\n# Default"
        )

        tool = ToolDefinition.load(tool_dir)
        assert tool is not None
        assert tool.parameters[0].default == 10


class TestToolJsonSchema:
    def test_to_json_schema(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "schema-tool"
        tool_dir.mkdir()
        (tool_dir / "TOOL.md").write_text(
            "---\n"
            "name: schema-tool\n"
            "description: Test schema\n"
            "parameters:\n"
            "  name:\n"
            "    type: string\n"
            "    description: A name\n"
            "    required: true\n"
            "  count:\n"
            "    type: integer\n"
            "    description: A count\n"
            "    default: 5\n"
            "---\n# Schema"
        )

        tool = ToolDefinition.load(tool_dir)
        assert tool is not None
        schema = tool.to_json_schema()
        assert schema["type"] == "object"
        assert "name" in schema["properties"]
        assert "count" in schema["properties"]
        assert schema["required"] == ["name"]
        assert schema["properties"]["count"]["default"] == 5

    def test_to_llm_declaration(self, tmp_path: Path) -> None:
        tool_dir = tmp_path / "llm-tool"
        tool_dir.mkdir()
        (tool_dir / "TOOL.md").write_text(
            "---\n"
            "name: llm-tool\n"
            "description: For LLM\n"
            "parameters:\n"
            "  input:\n"
            "    type: string\n"
            "    description: Input text\n"
            "    required: true\n"
            "---\n# LLM Tool"
        )

        tool = ToolDefinition.load(tool_dir)
        assert tool is not None
        decl = tool.to_llm_declaration()
        assert decl["type"] == "function"
        assert decl["function"]["name"] == "llm-tool"
        assert decl["function"]["description"] == "For LLM"
        assert "input" in decl["function"]["parameters"]["properties"]
