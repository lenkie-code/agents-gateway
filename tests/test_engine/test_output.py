"""Tests for structured output validation."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from agent_gateway.engine.models import StopReason
from agent_gateway.engine.output import (
    build_correction_message,
    build_schema_instruction,
    resolve_schema,
    validate_output,
    validate_output_pydantic,
)
from tests.test_engine.conftest import (
    make_agent,
    make_engine,
    make_llm_response,
    make_workspace,
)

SIMPLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "integer"},
        "explanation": {"type": "string"},
    },
    "required": ["answer"],
}


class TestValidateOutput:
    def test_valid_json_matching_schema(self) -> None:
        raw = '{"answer": 42, "explanation": "The answer"}'
        output, errors = validate_output(raw, SIMPLE_SCHEMA)
        assert output == {"answer": 42, "explanation": "The answer"}
        assert errors == []

    def test_valid_json_missing_required(self) -> None:
        raw = '{"explanation": "No answer"}'
        output, errors = validate_output(raw, SIMPLE_SCHEMA)
        assert output is None
        assert len(errors) == 1
        assert "answer" in errors[0]

    def test_invalid_json(self) -> None:
        raw = "not json at all"
        output, errors = validate_output(raw, SIMPLE_SCHEMA)
        assert output is None
        assert len(errors) == 1
        assert "Invalid JSON" in errors[0]

    def test_wrong_type(self) -> None:
        raw = '{"answer": "not an integer"}'
        output, errors = validate_output(raw, SIMPLE_SCHEMA)
        assert output is None
        assert len(errors) == 1

    def test_empty_string(self) -> None:
        output, errors = validate_output("", SIMPLE_SCHEMA)
        assert output is None
        assert len(errors) == 1


class TestBuildSchemaInstruction:
    def test_includes_schema(self) -> None:
        instruction = build_schema_instruction(SIMPLE_SCHEMA)
        assert "Required Output Format" in instruction
        assert '"answer"' in instruction
        assert "integer" in instruction


class TestBuildCorrectionMessage:
    def test_correction_message(self) -> None:
        msg = build_correction_message(["Missing field: answer"], SIMPLE_SCHEMA)
        assert msg["role"] == "user"
        assert "Missing field: answer" in msg["content"]
        assert '"answer"' in msg["content"]


class TestStructuredOutputInExecution:
    @pytest.mark.asyncio
    async def test_valid_output_schema(self) -> None:
        """LLM returns valid JSON matching schema → output populated."""
        engine, _, _ = make_engine(responses=[make_llm_response(text='{"answer": 42}')])
        agent = make_agent()
        workspace = make_workspace()
        from agent_gateway.engine.models import ExecutionOptions

        options = ExecutionOptions(output_schema=SIMPLE_SCHEMA)
        result = await engine.execute(agent, "What is 6*7?", workspace, options=options)

        assert result.stop_reason == StopReason.COMPLETED
        assert result.output == {"answer": 42}
        assert result.validation_errors is None

    @pytest.mark.asyncio
    async def test_invalid_then_retry_success(self) -> None:
        """LLM returns invalid JSON → retry → valid JSON → output populated."""
        engine, _, _ = make_engine(
            responses=[
                make_llm_response(text="not json"),
                make_llm_response(text='{"answer": 42}'),
            ]
        )
        agent = make_agent()
        workspace = make_workspace()
        from agent_gateway.engine.models import ExecutionOptions

        options = ExecutionOptions(output_schema=SIMPLE_SCHEMA)
        result = await engine.execute(agent, "What is 6*7?", workspace, options=options)

        assert result.stop_reason == StopReason.COMPLETED
        assert result.output == {"answer": 42}

    @pytest.mark.asyncio
    async def test_invalid_then_retry_also_fails(self) -> None:
        """LLM returns invalid twice → output=None, validation_errors populated."""
        engine, _, _ = make_engine(
            responses=[
                make_llm_response(text="not json"),
                make_llm_response(text="still not json"),
            ]
        )
        agent = make_agent()
        workspace = make_workspace()
        from agent_gateway.engine.models import ExecutionOptions

        options = ExecutionOptions(output_schema=SIMPLE_SCHEMA)
        result = await engine.execute(agent, "What is 6*7?", workspace, options=options)

        assert result.stop_reason == StopReason.COMPLETED
        assert result.output is None
        assert result.validation_errors is not None
        assert len(result.validation_errors) > 0

    @pytest.mark.asyncio
    async def test_no_schema(self) -> None:
        """No output_schema → raw_text only, output=None."""
        engine, _, _ = make_engine(responses=[make_llm_response(text="Just text")])
        agent = make_agent()
        workspace = make_workspace()

        result = await engine.execute(agent, "Hi", workspace)

        assert result.output is None
        assert result.raw_text == "Just text"


# -- Pydantic model helpers --------------------------------------------------


class MathAnswer(BaseModel):
    answer: int
    explanation: str | None = None


class TravelPlan(BaseModel):
    destination: str
    flights: list[dict[str, Any]]
    total_cost: float


# -- resolve_schema -----------------------------------------------------------


class TestCodeFenceStripping:
    def test_fenced_json_dict_schema(self) -> None:
        raw = '```json\n{"answer": 42}\n```'
        output, errors = validate_output(raw, SIMPLE_SCHEMA)
        assert errors == []
        assert output == {"answer": 42}

    def test_fenced_json_pydantic(self) -> None:
        raw = '```json\n{"answer": 42, "explanation": "test"}\n```'
        result, errors = validate_output_pydantic(raw, MathAnswer)
        assert errors == []
        assert isinstance(result, MathAnswer)
        assert result.answer == 42

    def test_bare_fence(self) -> None:
        raw = '```\n{"answer": 7}\n```'
        output, errors = validate_output(raw, SIMPLE_SCHEMA)
        assert errors == []
        assert output == {"answer": 7}

    def test_no_fences_still_works(self) -> None:
        raw = '{"answer": 10}'
        output, errors = validate_output(raw, SIMPLE_SCHEMA)
        assert errors == []
        assert output == {"answer": 10}


class TestResolveSchema:
    def test_dict_passthrough(self) -> None:
        schema_dict = {"type": "object", "properties": {"x": {"type": "integer"}}}
        json_schema, model_cls = resolve_schema(schema_dict)
        assert json_schema is schema_dict
        assert model_cls is None

    def test_pydantic_model(self) -> None:
        json_schema, model_cls = resolve_schema(MathAnswer)
        assert model_cls is MathAnswer
        assert json_schema["type"] == "object"
        assert "answer" in json_schema["properties"]

    def test_pydantic_model_complex(self) -> None:
        json_schema, model_cls = resolve_schema(TravelPlan)
        assert model_cls is TravelPlan
        assert "destination" in json_schema["properties"]
        assert "total_cost" in json_schema["properties"]


# -- validate_output_pydantic -------------------------------------------------


class TestValidateOutputPydantic:
    def test_valid_json(self) -> None:
        raw = '{"answer": 42, "explanation": "six times seven"}'
        result, errors = validate_output_pydantic(raw, MathAnswer)
        assert errors == []
        assert isinstance(result, MathAnswer)
        assert result.answer == 42
        assert result.explanation == "six times seven"

    def test_valid_json_optional_missing(self) -> None:
        raw = '{"answer": 7}'
        result, errors = validate_output_pydantic(raw, MathAnswer)
        assert errors == []
        assert isinstance(result, MathAnswer)
        assert result.answer == 7
        assert result.explanation is None

    def test_invalid_json(self) -> None:
        result, errors = validate_output_pydantic("not json", MathAnswer)
        assert result is None
        assert len(errors) == 1
        assert "Invalid JSON" in errors[0]

    def test_wrong_type(self) -> None:
        raw = '{"answer": "not an int"}'
        result, errors = validate_output_pydantic(raw, MathAnswer)
        assert result is None
        assert len(errors) >= 1

    def test_missing_required(self) -> None:
        raw = '{"explanation": "no answer field"}'
        result, errors = validate_output_pydantic(raw, MathAnswer)
        assert result is None
        assert len(errors) >= 1

    def test_complex_model(self) -> None:
        raw = '{"destination": "Tokyo", "flights": [{"from": "SFO", "to": "NRT"}], "total_cost": 1200.50}'
        result, errors = validate_output_pydantic(raw, TravelPlan)
        assert errors == []
        assert isinstance(result, TravelPlan)
        assert result.destination == "Tokyo"
        assert result.total_cost == 1200.50
        assert len(result.flights) == 1


# -- Integration: Pydantic model through executor ----------------------------


class TestPydanticOutputInExecution:
    @pytest.mark.asyncio
    async def test_pydantic_model_valid(self) -> None:
        """LLM returns valid JSON → result.output is a Pydantic model instance."""
        engine, _, _ = make_engine(
            responses=[make_llm_response(text='{"answer": 42, "explanation": "math"}')]
        )
        agent = make_agent()
        workspace = make_workspace()
        from agent_gateway.engine.models import ExecutionOptions

        options = ExecutionOptions(output_schema=MathAnswer)
        result = await engine.execute(agent, "What is 6*7?", workspace, options=options)

        assert result.stop_reason == StopReason.COMPLETED
        assert isinstance(result.output, MathAnswer)
        assert result.output.answer == 42
        assert result.validation_errors is None

    @pytest.mark.asyncio
    async def test_pydantic_model_invalid_then_retry_success(self) -> None:
        """LLM returns invalid → retry → valid → model instance."""
        engine, _, _ = make_engine(
            responses=[
                make_llm_response(text="not json"),
                make_llm_response(text='{"answer": 42}'),
            ]
        )
        agent = make_agent()
        workspace = make_workspace()
        from agent_gateway.engine.models import ExecutionOptions

        options = ExecutionOptions(output_schema=MathAnswer)
        result = await engine.execute(agent, "What is 6*7?", workspace, options=options)

        assert result.stop_reason == StopReason.COMPLETED
        assert isinstance(result.output, MathAnswer)
        assert result.output.answer == 42

    @pytest.mark.asyncio
    async def test_pydantic_model_invalid_both_attempts(self) -> None:
        """LLM returns invalid twice → output=None, validation_errors populated."""
        engine, _, _ = make_engine(
            responses=[
                make_llm_response(text="nope"),
                make_llm_response(text="still nope"),
            ]
        )
        agent = make_agent()
        workspace = make_workspace()
        from agent_gateway.engine.models import ExecutionOptions

        options = ExecutionOptions(output_schema=MathAnswer)
        result = await engine.execute(agent, "What is 6*7?", workspace, options=options)

        assert result.stop_reason == StopReason.COMPLETED
        assert result.output is None
        assert result.validation_errors is not None

    @pytest.mark.asyncio
    async def test_dict_schema_still_works(self) -> None:
        """Existing dict schema path is unaffected."""
        engine, _, _ = make_engine(
            responses=[make_llm_response(text='{"answer": 42}')]
        )
        agent = make_agent()
        workspace = make_workspace()
        from agent_gateway.engine.models import ExecutionOptions

        options = ExecutionOptions(output_schema=SIMPLE_SCHEMA)
        result = await engine.execute(agent, "What is 6*7?", workspace, options=options)

        assert result.stop_reason == StopReason.COMPLETED
        assert result.output == {"answer": 42}
        assert isinstance(result.output, dict)
