"""Tests for CLI output formatting and --format flag."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from agent_gateway.cli.formatting import OutputFormat, render_csv, render_json
from agent_gateway.cli.main import app

runner = CliRunner()
WORKSPACE = "tests/fixtures/workspace"


class TestRenderJson:
    def test_with_data(self) -> None:
        rows = [{"a": 1, "b": "hello"}]
        result = render_json(rows)
        assert json.loads(result) == rows

    def test_empty(self) -> None:
        assert json.loads(render_json([])) == []


class TestRenderCsv:
    def test_with_data(self) -> None:
        rows = [{"name": "alice", "age": 30}]
        result = render_csv(rows, ["name", "age"])
        lines = result.split("\n")
        assert lines[0] == "name,age"
        assert lines[1] == "alice,30"

    def test_empty_produces_header_only(self) -> None:
        result = render_csv([], ["name", "age"])
        assert result == "name,age"

    def test_special_characters(self) -> None:
        rows = [{"val": 'has,comma and "quotes"'}]
        result = render_csv(rows, ["val"])
        lines = result.split("\n")
        assert lines[0] == "val"
        # CSV should properly escape
        assert "comma" in lines[1]


class TestAgentsFormat:
    def test_table_default(self) -> None:
        result = runner.invoke(app, ["agents", "-w", WORKSPACE])
        assert result.exit_code == 0
        assert "test-agent" in result.output

    def test_json(self) -> None:
        result = runner.invoke(app, ["agents", "-w", WORKSPACE, "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["id"] == "test-agent"

    def test_csv(self) -> None:
        result = runner.invoke(app, ["agents", "-w", WORKSPACE, "--format", "csv"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert lines[0] == "id,skills,tools,model"
        assert "test-agent" in lines[1]


class TestSkillsFormat:
    def test_json(self) -> None:
        result = runner.invoke(app, ["skills", "-w", WORKSPACE, "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(s["id"] == "test-skill" for s in data)

    def test_csv(self) -> None:
        result = runner.invoke(app, ["skills", "-w", WORKSPACE, "--format", "csv"])
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert lines[0] == "id,tools,steps,description"


class TestSchedulesFormat:
    def test_json_empty(self) -> None:
        result = runner.invoke(app, ["schedules", "-w", WORKSPACE, "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_csv_empty(self) -> None:
        result = runner.invoke(app, ["schedules", "-w", WORKSPACE, "--format", "csv"])
        assert result.exit_code == 0
        assert "name,agent,cron,enabled,timezone" in result.output


class TestInvokeFormat:
    def test_csv_rejected(self) -> None:
        result = runner.invoke(app, ["invoke", "x", "hi", "-w", WORKSPACE, "--format", "csv"])
        assert result.exit_code == 1
        assert "CSV format is not supported" in result.output

    def test_json_and_format_json_compatible(self) -> None:
        """--json and --format json should not conflict (both request JSON)."""
        result = runner.invoke(
            app, ["invoke", "x", "hi", "-w", WORKSPACE, "--json", "--format", "json"]
        )
        # Should not error on flag conflict; may fail on agent not found
        assert "cannot use both" not in result.output

    def test_json_and_format_csv_conflict(self) -> None:
        result = runner.invoke(
            app, ["invoke", "x", "hi", "-w", WORKSPACE, "--json", "--format", "csv"]
        )
        assert result.exit_code == 1
        assert "cannot use both" in result.output


class TestOutputFormatEnum:
    def test_values(self) -> None:
        assert set(OutputFormat) == {OutputFormat.table, OutputFormat.json, OutputFormat.csv}
