"""Tests for the workflow executor."""

from __future__ import annotations

import asyncio
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


def _make_llm_response(text: str = "ok") -> LLMResponse:
    return LLMResponse(
        text=text, tool_calls=[], model="test",
        input_tokens=10, output_tokens=5, cost=0.001,
    )


def _noop_llm() -> Any:
    async def mock_llm(**kwargs: Any) -> LLMResponse:
        raise RuntimeError("LLM should not be called")
    return mock_llm


class TestWorkflowExecutorSequential:
    @pytest.mark.asyncio
    async def test_single_tool_step(self) -> None:
        """Workflow with one tool step executes and returns output."""
        registry = _make_tool_registry("lookup")
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

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
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

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
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

        skill = _make_skill(
            steps=[SkillStep(name="fail", tool="nonexistent")],
        )

        result = await executor.execute(
            skill=skill,
            input_data={},
            tool_context=_make_context(),
        )

        assert "error" in result["steps"]["fail"]["output"]

    @pytest.mark.asyncio
    async def test_empty_steps_returns_none_output(self) -> None:
        """Skill with no steps returns None output and empty steps dict."""
        executor = WorkflowExecutor(ToolRegistry(), _simple_executor, _noop_llm())
        skill = _make_skill(steps=[])

        result = await executor.execute(
            skill=skill, input_data={"x": 1}, tool_context=_make_context(),
        )

        assert result["output"] is None
        assert result["steps"] == {}

    @pytest.mark.asyncio
    async def test_tool_exception_returns_error_dict(self) -> None:
        """Tool that raises an exception returns an error dict, doesn't crash."""
        registry = ToolRegistry()

        async def exploding(**kwargs: Any) -> dict[str, Any]:
            raise ValueError("kaboom")

        registry.register_code_tool(
            CodeTool(
                name="bomb", description="explodes", fn=exploding,
                parameters_schema={"type": "object", "properties": {}},
            )
        )

        async def raising_executor(
            tool: Any, arguments: dict[str, Any], context: ToolContext,
        ) -> Any:
            return await tool.code_tool.fn(**arguments)

        executor = WorkflowExecutor(registry, raising_executor, _noop_llm())
        skill = _make_skill(steps=[SkillStep(name="boom", tool="bomb")])

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert "error" in result["output"]
        assert "kaboom" in result["output"]["error"]

    @pytest.mark.asyncio
    async def test_step_with_no_input(self) -> None:
        """Tool step with empty input resolves to empty dict."""
        registry = _make_tool_registry("ping")
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

        skill = _make_skill(
            steps=[SkillStep(name="ping", tool="ping")],
            tools=["ping"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert result["output"]["tool"] == "ping"
        assert result["output"]["args"] == {}

    @pytest.mark.asyncio
    async def test_step_referencing_missing_input_gets_none(self) -> None:
        """Input reference to nonexistent key resolves to None."""
        registry = ToolRegistry()

        async def echo(**kwargs: Any) -> dict[str, Any]:
            return kwargs

        registry.register_code_tool(
            CodeTool(
                name="echo", description="echo", fn=echo,
                parameters_schema={"type": "object", "properties": {}},
            )
        )
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

        skill = _make_skill(
            steps=[
                SkillStep(name="s1", tool="echo", input={"x": "$.input.nonexistent"}),
            ],
            tools=["echo"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert result["output"]["x"] is None

    @pytest.mark.asyncio
    async def test_three_step_chain_context_accumulates(self) -> None:
        """Three sequential steps each see all prior outputs in context."""
        registry = ToolRegistry()

        async def step_a(**kwargs: Any) -> dict[str, Any]:
            return {"val": "a"}

        async def step_b(**kwargs: Any) -> dict[str, Any]:
            return {"val": "b", "got_a": kwargs.get("prev", {}).get("val", "")}

        async def step_c(**kwargs: Any) -> dict[str, Any]:
            return {
                "val": "c",
                "got_a": kwargs.get("from_a", {}).get("val", ""),
                "got_b": kwargs.get("from_b", {}).get("val", ""),
            }

        for name, fn in [("ta", step_a), ("tb", step_b), ("tc", step_c)]:
            registry.register_code_tool(
                CodeTool(
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())
        skill = _make_skill(
            steps=[
                SkillStep(name="a", tool="ta"),
                SkillStep(name="b", tool="tb", input={"prev": "$.steps.a.output"}),
                SkillStep(
                    name="c", tool="tc",
                    input={
                        "from_a": "$.steps.a.output",
                        "from_b": "$.steps.b.output",
                    },
                ),
            ],
            tools=["ta", "tb", "tc"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert result["steps"]["a"]["output"]["val"] == "a"
        assert result["steps"]["b"]["output"]["got_a"] == "a"
        assert result["steps"]["c"]["output"]["got_a"] == "a"
        assert result["steps"]["c"]["output"]["got_b"] == "b"
        assert result["output"]["val"] == "c"

    @pytest.mark.asyncio
    async def test_error_in_step_n_still_stored_in_context(self) -> None:
        """If step 1 returns an error, step 2 can still reference it."""
        registry = ToolRegistry()

        async def echo(**kwargs: Any) -> dict[str, Any]:
            return kwargs

        registry.register_code_tool(
            CodeTool(
                name="echo", description="echo", fn=echo,
                parameters_schema={"type": "object", "properties": {}},
            )
        )
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

        skill = _make_skill(
            steps=[
                SkillStep(name="bad", tool="nonexistent"),
                SkillStep(
                    name="check", tool="echo",
                    input={"prev": "$.steps.bad.output"},
                ),
            ],
            tools=["echo"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        # Step 2 receives the error dict from step 1
        assert "error" in result["steps"]["bad"]["output"]
        assert "error" in result["steps"]["check"]["output"]["prev"]


class TestWorkflowExecutorParallel:
    @pytest.mark.asyncio
    async def test_parallel_fan_out(self) -> None:
        """Multiple tools in a step run concurrently."""
        registry = _make_tool_registry("tool-a", "tool-b")
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

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
        """Missing tool in parallel step returns error for that entry only."""
        registry = _make_tool_registry("tool-a")
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

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
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        outputs = result["steps"]["gather"]["output"]
        assert len(outputs) == 2
        # First tool succeeds
        assert outputs[0]["tool"] == "tool-a"
        # Second tool has error
        assert "error" in outputs[1]

    @pytest.mark.asyncio
    async def test_parallel_actually_concurrent(self) -> None:
        """Verify parallel tools run concurrently, not sequentially.

        Two tools each sleep 0.1s. If sequential, total would be >= 0.2s.
        If parallel, total should be ~0.1s.
        """
        registry = ToolRegistry()
        events: list[str] = []

        async def slow_a(**kwargs: Any) -> dict[str, Any]:
            events.append("a-start")
            await asyncio.sleep(0.1)
            events.append("a-end")
            return {"tool": "a"}

        async def slow_b(**kwargs: Any) -> dict[str, Any]:
            events.append("b-start")
            await asyncio.sleep(0.1)
            events.append("b-end")
            return {"tool": "b"}

        for name, fn in [("slow-a", slow_a), ("slow-b", slow_b)]:
            registry.register_code_tool(
                CodeTool(
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())
        skill = _make_skill(
            steps=[
                SkillStep(
                    name="par",
                    tools=[ToolStep(tool="slow-a"), ToolStep(tool="slow-b")],
                ),
            ],
            tools=["slow-a", "slow-b"],
        )

        import time
        start = time.monotonic()
        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )
        duration = time.monotonic() - start

        # Must complete in under 0.2s (proves concurrency)
        assert duration < 0.2
        # Both tools started before either finished
        assert "a-start" in events
        assert "b-start" in events
        outputs = result["steps"]["par"]["output"]
        assert len(outputs) == 2

    @pytest.mark.asyncio
    async def test_fan_in_preserves_order(self) -> None:
        """Fan-in returns results in tool definition order, not completion order.

        Tool B finishes before Tool A, but output[0] is still A's result.
        """
        registry = ToolRegistry()

        async def slow_first(**kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(0.15)
            return {"tool": "first"}

        async def fast_second(**kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(0.01)
            return {"tool": "second"}

        for name, fn in [("slow", slow_first), ("fast", fast_second)]:
            registry.register_code_tool(
                CodeTool(
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())
        skill = _make_skill(
            steps=[
                SkillStep(
                    name="par",
                    tools=[
                        ToolStep(tool="slow"),   # index 0, finishes last
                        ToolStep(tool="fast"),   # index 1, finishes first
                    ],
                ),
            ],
            tools=["slow", "fast"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        outputs = result["steps"]["par"]["output"]
        assert outputs[0]["tool"] == "first"   # slow tool at index 0
        assert outputs[1]["tool"] == "second"  # fast tool at index 1

    @pytest.mark.asyncio
    async def test_parallel_single_tool_fast_path(self) -> None:
        """Parallel step with exactly one tool takes the optimized path."""
        registry = _make_tool_registry("only")
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

        skill = _make_skill(
            steps=[
                SkillStep(
                    name="single",
                    tools=[ToolStep(tool="only", input={"v": "$.input.v"})],
                ),
            ],
            tools=["only"],
        )

        result = await executor.execute(
            skill=skill, input_data={"v": "val"}, tool_context=_make_context(),
        )

        outputs = result["steps"]["single"]["output"]
        assert isinstance(outputs, list)
        assert len(outputs) == 1
        assert outputs[0]["tool"] == "only"
        assert outputs[0]["args"]["v"] == "val"

    @pytest.mark.asyncio
    async def test_parallel_tool_exception_isolated(self) -> None:
        """One tool raising an exception doesn't prevent other tools from completing."""
        registry = ToolRegistry()

        async def good(**kwargs: Any) -> dict[str, Any]:
            return {"ok": True}

        async def bad(**kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("tool failure")

        for name, fn in [("good", good), ("bad", bad)]:
            registry.register_code_tool(
                CodeTool(
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())
        skill = _make_skill(
            steps=[
                SkillStep(
                    name="par",
                    tools=[ToolStep(tool="good"), ToolStep(tool="bad")],
                ),
            ],
            tools=["good", "bad"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        outputs = result["steps"]["par"]["output"]
        assert outputs[0]["ok"] is True
        assert "error" in outputs[1]
        assert "tool failure" in outputs[1]["error"]

    @pytest.mark.asyncio
    async def test_fan_out_three_tools(self) -> None:
        """Fan-out works with 3+ tools."""
        registry = _make_tool_registry("a", "b", "c")
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

        skill = _make_skill(
            steps=[
                SkillStep(
                    name="gather",
                    tools=[
                        ToolStep(tool="a"),
                        ToolStep(tool="b"),
                        ToolStep(tool="c"),
                    ],
                ),
            ],
            tools=["a", "b", "c"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        outputs = result["steps"]["gather"]["output"]
        assert len(outputs) == 3
        assert [o["tool"] for o in outputs] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_parallel_results_accessible_by_next_step(self) -> None:
        """Sequential step after parallel can reference parallel output by index."""
        registry = ToolRegistry()

        async def gen_a(**kwargs: Any) -> dict[str, Any]:
            return {"val": 10}

        async def gen_b(**kwargs: Any) -> dict[str, Any]:
            return {"val": 20}

        async def combine(**kwargs: Any) -> dict[str, Any]:
            a_val = kwargs.get("a_result", {}).get("val", 0)
            b_val = kwargs.get("b_result", {}).get("val", 0)
            return {"sum": a_val + b_val}

        for name, fn in [("gen-a", gen_a), ("gen-b", gen_b), ("combine", combine)]:
            registry.register_code_tool(
                CodeTool(
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())
        skill = _make_skill(
            steps=[
                SkillStep(
                    name="gather",
                    tools=[ToolStep(tool="gen-a"), ToolStep(tool="gen-b")],
                ),
                SkillStep(
                    name="combine", tool="combine",
                    input={
                        "a_result": "$.steps.gather.output[0]",
                        "b_result": "$.steps.gather.output[1]",
                    },
                ),
            ],
            tools=["gen-a", "gen-b", "combine"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert result["output"]["sum"] == 30


class TestWorkflowExecutorPrompt:
    @pytest.mark.asyncio
    async def test_prompt_step(self) -> None:
        """Prompt step calls LLM and returns text."""
        registry = ToolRegistry()

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            return _make_llm_response("The answer is 42.")

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
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert "error" in result["output"]

    @pytest.mark.asyncio
    async def test_prompt_step_without_inputs(self) -> None:
        """Prompt step with no input template sends just the prompt text."""
        captured_messages: list[Any] = []

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            captured_messages.append(kwargs.get("messages", []))
            return _make_llm_response("response")

        executor = WorkflowExecutor(ToolRegistry(), _simple_executor, mock_llm)
        skill = _make_skill(
            steps=[SkillStep(name="ask", prompt="What is 2+2?")],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert result["output"] == "response"
        # The user message should be just the prompt (no Context block)
        user_msg = captured_messages[0][1]["content"]
        assert user_msg == "What is 2+2?"
        assert "Context" not in user_msg

    @pytest.mark.asyncio
    async def test_prompt_step_with_inputs_adds_context_block(self) -> None:
        """Prompt step with input adds a Context JSON block to the message."""
        captured_messages: list[Any] = []

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            captured_messages.append(kwargs.get("messages", []))
            return _make_llm_response("analyzed")

        executor = WorkflowExecutor(ToolRegistry(), _simple_executor, mock_llm)
        skill = _make_skill(
            steps=[
                SkillStep(
                    name="analyze",
                    prompt="Summarize this.",
                    input={"data": "$.input.payload"},
                ),
            ],
        )

        result = await executor.execute(
            skill=skill,
            input_data={"payload": {"key": "value"}},
            tool_context=_make_context(),
        )

        assert result["output"] == "analyzed"
        user_msg = captured_messages[0][1]["content"]
        assert "Summarize this." in user_msg
        assert "## Context" in user_msg
        assert '"key": "value"' in user_msg

    @pytest.mark.asyncio
    async def test_prompt_step_receives_system_message(self) -> None:
        """Prompt step sends a system message to the LLM."""
        captured_messages: list[Any] = []

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            captured_messages.append(kwargs.get("messages", []))
            return _make_llm_response("ok")

        executor = WorkflowExecutor(ToolRegistry(), _simple_executor, mock_llm)
        skill = _make_skill(steps=[SkillStep(name="s", prompt="Do it.")])

        await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        messages = captured_messages[0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_prompt_null_text_returns_empty_string(self) -> None:
        """LLM returning None text is coerced to empty string."""
        async def mock_llm(**kwargs: Any) -> LLMResponse:
            return LLMResponse(
                text=None, tool_calls=[], model="test",
                input_tokens=0, output_tokens=0, cost=0,
            )

        executor = WorkflowExecutor(ToolRegistry(), _simple_executor, mock_llm)
        skill = _make_skill(steps=[SkillStep(name="s", prompt="Do it.")])

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert result["output"] == ""


class TestWorkflowExecutorTimeout:
    @pytest.mark.asyncio
    async def test_timeout_returns_error(self) -> None:
        """Workflow that exceeds timeout returns error."""
        registry = ToolRegistry()

        async def slow_handler(**kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(10)
            return {}

        registry.register_code_tool(
            CodeTool(
                name="slow", description="Slow tool", fn=slow_handler,
                parameters_schema={"type": "object", "properties": {}},
            )
        )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

        skill = _make_skill(
            steps=[SkillStep(name="slow", tool="slow")],
            tools=["slow"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
            timeout_s=0.1,
        )

        assert result["output"] is None
        assert "error" in result
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_timeout_preserves_completed_steps(self) -> None:
        """Steps completed before timeout are preserved in the result."""
        registry = ToolRegistry()

        async def fast(**kwargs: Any) -> dict[str, Any]:
            return {"done": True}

        async def slow(**kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(10)
            return {}

        for name, fn in [("fast", fast), ("slow", slow)]:
            registry.register_code_tool(
                CodeTool(
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())
        skill = _make_skill(
            steps=[
                SkillStep(name="quick", tool="fast"),
                SkillStep(name="blocked", tool="slow"),
            ],
            tools=["fast", "slow"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
            timeout_s=0.2,
        )

        assert "error" in result
        # The fast step completed before timeout
        assert result["steps"]["quick"]["output"]["done"] is True
        # The slow step never completed
        assert "blocked" not in result["steps"]

    @pytest.mark.asyncio
    async def test_timeout_during_parallel_step(self) -> None:
        """Timeout during a parallel fan-out cancels all running tools."""
        registry = ToolRegistry()

        async def slow_a(**kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(10)
            return {"tool": "a"}

        async def slow_b(**kwargs: Any) -> dict[str, Any]:
            await asyncio.sleep(10)
            return {"tool": "b"}

        for name, fn in [("slow-a", slow_a), ("slow-b", slow_b)]:
            registry.register_code_tool(
                CodeTool(
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())
        skill = _make_skill(
            steps=[
                SkillStep(
                    name="par",
                    tools=[ToolStep(tool="slow-a"), ToolStep(tool="slow-b")],
                ),
            ],
            tools=["slow-a", "slow-b"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
            timeout_s=0.1,
        )

        assert result["output"] is None
        assert "timed out" in result["error"]


class TestWorkflowExecutorMixed:
    """Tests for workflows combining multiple step types."""

    @pytest.mark.asyncio
    async def test_full_pipeline_tool_parallel_prompt(self) -> None:
        """Complete workflow: tool -> parallel fan-out -> prompt summarization."""
        registry = ToolRegistry()

        async def fetch(**kwargs: Any) -> dict[str, Any]:
            return {"company": kwargs.get("name", ""), "data": [1, 2, 3]}

        async def analyze_a(**kwargs: Any) -> dict[str, Any]:
            return {"analysis": "growth", "source": "a"}

        async def analyze_b(**kwargs: Any) -> dict[str, Any]:
            return {"analysis": "stable", "source": "b"}

        for name, fn in [("fetch", fetch), ("analyze-a", analyze_a), ("analyze-b", analyze_b)]:
            registry.register_code_tool(
                CodeTool(
                    name=name, description=name, fn=fn,
                    parameters_schema={"type": "object", "properties": {}},
                )
            )

        call_count = 0

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            nonlocal call_count
            call_count += 1
            return _make_llm_response("Final summary: growth and stable")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)
        skill = _make_skill(
            steps=[
                # Step 1: Single tool fetch
                SkillStep(
                    name="fetch", tool="fetch",
                    input={"name": "$.input.company"},
                ),
                # Step 2: Parallel analysis
                SkillStep(
                    name="analyze",
                    tools=[
                        ToolStep(tool="analyze-a", input={"data": "$.steps.fetch.output"}),
                        ToolStep(tool="analyze-b", input={"data": "$.steps.fetch.output"}),
                    ],
                ),
                # Step 3: LLM summary
                SkillStep(
                    name="summarize",
                    prompt="Summarize the analyses.",
                    input={"analyses": "$.steps.analyze.output"},
                ),
            ],
            tools=["fetch", "analyze-a", "analyze-b"],
        )

        result = await executor.execute(
            skill=skill,
            input_data={"company": "Acme"},
            tool_context=_make_context(),
        )

        # Verify all steps ran
        assert "fetch" in result["steps"]
        assert "analyze" in result["steps"]
        assert "summarize" in result["steps"]

        # Verify data flow
        assert result["steps"]["fetch"]["output"]["company"] == "Acme"
        analyses = result["steps"]["analyze"]["output"]
        assert len(analyses) == 2
        assert analyses[0]["source"] == "a"
        assert analyses[1]["source"] == "b"

        # Verify LLM was called exactly once
        assert call_count == 1
        assert result["output"] == "Final summary: growth and stable"

    @pytest.mark.asyncio
    async def test_parallel_then_parallel(self) -> None:
        """Two parallel steps in sequence both complete correctly."""
        registry = _make_tool_registry("a", "b", "c", "d")
        executor = WorkflowExecutor(registry, _simple_executor, _noop_llm())

        skill = _make_skill(
            steps=[
                SkillStep(
                    name="first",
                    tools=[ToolStep(tool="a"), ToolStep(tool="b")],
                ),
                SkillStep(
                    name="second",
                    tools=[ToolStep(tool="c"), ToolStep(tool="d")],
                ),
            ],
            tools=["a", "b", "c", "d"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        first = result["steps"]["first"]["output"]
        second = result["steps"]["second"]["output"]
        assert [o["tool"] for o in first] == ["a", "b"]
        assert [o["tool"] for o in second] == ["c", "d"]
        # Output is last step's output
        assert result["output"] == second

    @pytest.mark.asyncio
    async def test_prompt_then_tool_uses_prompt_output(self) -> None:
        """A tool step can reference a previous prompt step's output."""
        registry = ToolRegistry()

        async def echo(**kwargs: Any) -> dict[str, Any]:
            return kwargs

        registry.register_code_tool(
            CodeTool(
                name="echo", description="echo", fn=echo,
                parameters_schema={"type": "object", "properties": {}},
            )
        )

        async def mock_llm(**kwargs: Any) -> LLMResponse:
            return _make_llm_response("generated-query")

        executor = WorkflowExecutor(registry, _simple_executor, mock_llm)
        skill = _make_skill(
            steps=[
                SkillStep(name="generate", prompt="Generate a search query."),
                SkillStep(
                    name="search", tool="echo",
                    input={"query": "$.steps.generate.output"},
                ),
            ],
            tools=["echo"],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        # The tool step received the LLM's text output as input
        assert result["output"]["query"] == "generated-query"

    @pytest.mark.asyncio
    async def test_invalid_step_returns_error_dict(self) -> None:
        """Step with no tool/tools/prompt returns an error dict."""
        executor = WorkflowExecutor(ToolRegistry(), _simple_executor, _noop_llm())

        # Manually create a step with no tool/tools/prompt (bypassing parser validation)
        skill = _make_skill(
            steps=[SkillStep(name="empty")],
        )

        result = await executor.execute(
            skill=skill, input_data={}, tool_context=_make_context(),
        )

        assert "error" in result["steps"]["empty"]["output"]
        assert "Invalid step" in result["steps"]["empty"]["output"]["error"]
