"""Tests for the workflow input resolver."""

from __future__ import annotations

from agent_gateway.engine.resolver import resolve_input


class TestResolveInput:
    def test_literal_values_pass_through(self) -> None:
        template = {"city": "London", "count": "5"}
        context: dict = {"input": {}, "steps": {}}
        result = resolve_input(template, context)
        assert result == {"city": "London", "count": "5"}

    def test_resolve_input_reference(self) -> None:
        template = {"company": "$.input.company_name"}
        context = {"input": {"company_name": "Acme"}, "steps": {}}
        result = resolve_input(template, context)
        assert result == {"company": "Acme"}

    def test_resolve_step_output(self) -> None:
        template = {"data": "$.steps.enrich.output"}
        context = {
            "input": {},
            "steps": {"enrich": {"output": {"name": "Acme", "size": 100}}},
        }
        result = resolve_input(template, context)
        assert result == {"data": {"name": "Acme", "size": 100}}

    def test_resolve_array_index(self) -> None:
        template = {"score": "$.steps.parallel.output[0]"}
        context = {
            "input": {},
            "steps": {"parallel": {"output": [42, 99]}},
        }
        result = resolve_input(template, context)
        assert result == {"score": 42}

    def test_resolve_nested_path(self) -> None:
        template = {"score": "$.steps.score.output.value"}
        context = {
            "input": {},
            "steps": {"score": {"output": {"value": 85}}},
        }
        result = resolve_input(template, context)
        assert result == {"score": 85}

    def test_missing_input_key_returns_none(self) -> None:
        template = {"x": "$.input.nonexistent"}
        context = {"input": {}, "steps": {}}
        result = resolve_input(template, context)
        assert result == {"x": None}

    def test_missing_step_returns_none(self) -> None:
        template = {"x": "$.steps.ghost.output"}
        context = {"input": {}, "steps": {}}
        result = resolve_input(template, context)
        assert result == {"x": None}

    def test_array_index_out_of_range_returns_none(self) -> None:
        template = {"x": "$.steps.par.output[99]"}
        context = {"input": {}, "steps": {"par": {"output": [1, 2]}}}
        result = resolve_input(template, context)
        assert result == {"x": None}

    def test_empty_template(self) -> None:
        result = resolve_input({}, {"input": {}, "steps": {}})
        assert result == {}

    def test_mixed_literals_and_references(self) -> None:
        template = {
            "literal": "hello",
            "from_input": "$.input.name",
            "from_step": "$.steps.first.output",
        }
        context = {
            "input": {"name": "Alice"},
            "steps": {"first": {"output": "step-result"}},
        }
        result = resolve_input(template, context)
        assert result == {
            "literal": "hello",
            "from_input": "Alice",
            "from_step": "step-result",
        }
