"""Tests for Jinja2 template rendering."""

from __future__ import annotations

import json
from pathlib import Path

from agent_gateway.notifications.template import render_template, render_template_string


class TestRenderTemplateString:
    def test_basic_rendering(self) -> None:
        result = render_template_string("Hello {{ name }}!", name="World")
        assert result == "Hello World!"

    def test_tojson_filter(self) -> None:
        result = render_template_string("{{ data | tojson }}", data={"key": "value"})
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_nested_object_access(self) -> None:
        class Event:
            agent_id = "my-agent"
            execution_id = "exec-1"

        result = render_template_string(
            '{"agent": "{{ event.agent_id }}"}',
            event=Event(),
        )
        parsed = json.loads(result)
        assert parsed["agent"] == "my-agent"


class TestRenderTemplate:
    def test_file_template(self, tmp_path: Path) -> None:
        template = tmp_path / "test.json.j2"
        template.write_text('[{"text": "{{ message }}"}]')

        result = render_template(template, message="Hello")
        parsed = json.loads(result)
        assert parsed == [{"text": "Hello"}]

    def test_tojson_in_file_template(self, tmp_path: Path) -> None:
        template = tmp_path / "test.json.j2"
        template.write_text('{"data": {{ items | tojson }}}')

        result = render_template(template, items=["a", "b", "c"])
        parsed = json.loads(result)
        assert parsed["data"] == ["a", "b", "c"]
