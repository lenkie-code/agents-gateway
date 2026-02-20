"""Tests for the workflow executor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_gateway.engine.llm import LLMResponse
from agent_gateway.engine.models import ToolContext
from agent_gateway.engine.workflow import WorkflowExecutor
from agent_gateway.workspace.registry import CodeTool, ToolRegistry
from agent_gateway.workspace.skill import SkillDefinition, SkillStep, ToolStep


def _make_tool_registry(*tool_names: str) -> ToolRegistry:
    """Create a registry with simple echo-style code tools."""
    registry = ToolRegistry()
    for name in tool_names:

        async def handler(tool_name: str = name, **kwargs: Any) -> dict[str, Any]:
            return {"tool": tool_name, "args": kwargs}

        code_tool = CodeTool(
            name=name,
            description=f"Tool {name}",
            fn=handler,
            parameters_schema={"type": "object", "properties": {}},
        )
        registry.register_code_tool(code_tool)
    return registry


def _make_context() -> ToolContext:
    return ToolContext(execution_id="test-exec", agent_id="test-agent", metadata={})


async def _simple_executor(tool: Any, arguments: dict[str, Any], context: ToolContext) -> Any:
    """Execute a tool by calling its code_tool function."""
    if tool.code_tool:
        return await tool.code_tool.fn(**arguments)
    return {"error": "no handler"}


def _make_skill(steps: list[SkillStep], tools: list[str] | None = None) -> SkillDefinition:
    return SkillDefinition(
        id="test-skill",
        path=Path("/tmp/skills/test-skill"),
        name="test-skill",
        description="Test skill",
        tools=tools or [],
        instructions="",
        steps=steps,
    )


class TestWorkflowExecutorSequential:
    @pytest.mark.asyncio
    async def test_single_tool_step(self) -> None:
        """Workflow with one tool step executes and returns output."""
        registry = _make_tool_registry("lookup")

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            raise RuntimeError("LLM should not be called")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)

        skill = _make_skill(
            steps=[
                SkillStep(name="fetch", tool="lookup", input={"query": "$.input.term"}),
            ],
            tools=["lookup"],
        )

        result = await executor.execute(
            skill=skill,
            input_data={"term": "test-query"},
            tool_context=_make_context(),
        )

        assert result["output"]["tool"] == "lookup"
        assert result["output"]["args"]["query"] == "test-query"
        assert "fetch" in result["steps"]

    @pytest.mark.asyncio
    async def test_chained_steps_pass_output_forward(self) -> None:
        """Step B can reference Step A's output."""
        registry = ToolRegistry()

        async def enrich(**kwargs: Any) -> dict[str, Any]:
            return {"enriched": True, "company": kwargs.get("name", "")}

        async def score(**kwargs: Any) -> dict[str, Any]:
            data = kwargs.get("data", {})
            return {"score": 100 if data.get("enriched") else 0}

        for name, fn in [("enrich", enrich), ("score", score)]:
            registry.register_code_tool(
                CodeTool(
                    name=name,
                    description=name,
                    fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            raise RuntimeError("LLM should not be called")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)

        skill = _make_skill(
            steps=[
                SkillStep(name="enrich", tool="enrich", input={"name": "$.input.company"}),
                SkillStep(name="score", tool="score", input={"data": "$.steps.enrich.output"}),
            ],
            tools=["enrich", "score"],
        )

        result = await executor.execute(
            skill=skill,
            input_data={"company": "Acme"},
            tool_context=_make_context(),
        )

        assert result["steps"]["enrich"]["output"]["enriched"] is True
        assert result["steps"]["score"]["output"]["score"] == 100
        assert result["output"]["score"] == 100

    @pytest.mark.asyncio
    async def test_missing_tool_returns_error(self) -> None:
        """Referencing a non-existent tool returns an error dict."""
        registry = ToolRegistry()

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            raise RuntimeError("LLM should not be called")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)

        skill = _make_skill(
            steps=[SkillStep(name="fail", tool="nonexistent")],
        )

        result = await executor.execute(
            skill=skill,
            input_data={},
            tool_context=_make_context(),
        )

        assert "error" in result["steps"]["fail"]["output"]


class TestWorkflowExecutorParallel:
    @pytest.mark.asyncio
    async def test_parallel_fan_out(self) -> None:
        """Multiple tools in a step run concurrently."""
        registry = _make_tool_registry("tool-a", "tool-b")

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            raise RuntimeError("LLM should not be called")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)

        skill = _make_skill(
            steps=[
                SkillStep(
                    name="gather",
                    tools=[
                        ToolStep(tool="tool-a", input={"x": "$.input.x"}),
                        ToolStep(tool="tool-b", input={"y": "$.input.y"}),
                    ],
                ),
            ],
            tools=["tool-a", "tool-b"],
        )

        result = await executor.execute(
            skill=skill,
            input_data={"x": "hello", "y": "world"},
            tool_context=_make_context(),
        )

        outputs = result["steps"]["gather"]["output"]
        assert isinstance(outputs, list)
        assert len(outputs) == 2
        assert outputs[0]["tool"] == "tool-a"
        assert outputs[1]["tool"] == "tool-b"

    @pytest.mark.asyncio
    async def test_fan_out_with_missing_tool(self) -> None:
        """Missing tool in parallel step returns error for that entry."""
        registry = _make_tool_registry("tool-a")

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            raise RuntimeError("LLM should not be called")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)

        skill = _make_skill(
            steps=[
                SkillStep(
                    name="gather",
                    tools=[
                        ToolStep(tool="tool-a"),
                        ToolStep(tool="missing"),
                    ],
                ),
            ],
        )

        result = await executor.execute(
            skill=skill,
            input_data={},
            tool_context=_make_context(),
        )

        outputs = result["steps"]["gather"]["output"]
        assert len(outputs) == 2
        assert "error" in outputs[1]


class TestWorkflowExecutorPrompt:
    @pytest.mark.asyncio
    async def test_prompt_step(self) -> None:
        """Prompt step calls LLM and returns text."""
        registry = ToolRegistry()

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            return LLMResponse(
                text="The answer is 42.",
                tool_calls=[],
                model="test",
                input_tokens=10,
                output_tokens=5,
                cost=0.001,
            )

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)

        skill = _make_skill(
            steps=[
                SkillStep(
                    name="analyze",
                    prompt="What is the answer?",
                    input={"context": "$.input.data"},
                ),
            ],
        )

        result = await executor.execute(
            skill=skill,
            input_data={"data": "some data"},
            tool_context=_make_context(),
        )

        assert result["output"] == "The answer is 42."

    @pytest.mark.asyncio
    async def test_prompt_step_llm_failure(self) -> None:
        """LLM failure in prompt step returns error dict."""
        registry = ToolRegistry()

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            raise RuntimeError("LLM down")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)

        skill = _make_skill(
            steps=[SkillStep(name="fail", prompt="Do something")],
        )

        result = await executor.execute(
            skill=skill,
            input_data={},
            tool_context=_make_context(),
        )

        assert "error" in result["output"]


class TestWorkflowExecutorTimeout:
    @pytest.mark.asyncio
    async def test_timeout_returns_error(self) -> None:
        """Workflow that exceeds timeout returns error."""
        import asyncio

        registry = ToolRegistry()

        async def slow_handler(**kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(10)
            return {}

        registry.register_code_tool(
            CodeTool(
                name="slow",
                description="Slow tool",
                fn=slow_handler,
                parameters_schema={"type": "object", "properties": {}},
            )
        )

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            raise RuntimeError("LLM should not be called")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)

        skill = _make_skill(
            steps=[SkillStep(name="slow", tool="slow")],
            tools=["slow"],
        )

        result = await executor.execute(
            skill=skill,
            input_data={},
            tool_context=_make_context(),
            timeout_s=0.1,
        )

        assert result["output"] is None
        assert "error" in result
        assert "timed out" in result["error"]
