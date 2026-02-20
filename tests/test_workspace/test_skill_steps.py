"""Tests for skill step parsing."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.workspace.skill import SkillDefinition


class TestSkillStepParsing:
    def test_skill_without_steps(self, tmp_path: Path) -> None:
        """Skills without steps work as before."""
        skill_dir = tmp_path / "basic-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: basic\ndescription: Basic skill\ntools:\n  - echo\n---\n"
            "# Basic\n\nJust a tool container."
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert skill.steps == []
        assert skill.has_workflow is False
        assert skill.tools == ["echo"]

    def test_single_tool_step(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "single-step"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: single\n"
            "description: One step\n"
            "tools:\n  - lookup\n"
            "steps:\n"
            "  - name: fetch\n"
            "    tool: lookup\n"
            "    input:\n"
            "      query: '$.input.search_term'\n"
            "---\n"
            "# Single Step Skill"
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert skill.has_workflow is True
        assert len(skill.steps) == 1
        step = skill.steps[0]
        assert step.name == "fetch"
        assert step.tool == "lookup"
        assert step.tools is None
        assert step.prompt is None
        assert step.input == {"query": "$.input.search_term"}

    def test_parallel_fan_out_step(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "parallel-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: parallel\n"
            "description: Parallel step\n"
            "tools:\n  - tool-a\n  - tool-b\n"
            "steps:\n"
            "  - name: gather\n"
            "    tools:\n"
            "      - tool: tool-a\n"
            "        input:\n"
            "          x: '$.input.x'\n"
            "      - tool: tool-b\n"
            "        input:\n"
            "          y: '$.input.y'\n"
            "---\n"
            "# Parallel"
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert len(skill.steps) == 1
        step = skill.steps[0]
        assert step.name == "gather"
        assert step.tool is None
        assert step.tools is not None
        assert len(step.tools) == 2
        assert step.tools[0].tool == "tool-a"
        assert step.tools[0].input == {"x": "$.input.x"}
        assert step.tools[1].tool == "tool-b"

    def test_prompt_step(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "prompt-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: prompt\n"
            "description: LLM step\n"
            "steps:\n"
            "  - name: analyze\n"
            "    prompt: Analyze the data and summarize.\n"
            "    input:\n"
            "      data: '$.steps.fetch.output'\n"
            "---\n"
            "# Prompt Skill"
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert len(skill.steps) == 1
        step = skill.steps[0]
        assert step.name == "analyze"
        assert step.prompt == "Analyze the data and summarize."
        assert step.tool is None
        assert step.tools is None

    def test_multi_step_workflow(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "multi-step"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: multi\n"
            "description: Multi-step workflow\n"
            "tools:\n  - enrich\n  - score\n"
            "steps:\n"
            "  - name: enrich\n"
            "    tool: enrich\n"
            "    input:\n"
            "      company: '$.input.company'\n"
            "  - name: score\n"
            "    tool: score\n"
            "    input:\n"
            "      data: '$.steps.enrich.output'\n"
            "  - name: decide\n"
            "    prompt: Make a decision based on the score.\n"
            "    input:\n"
            "      score: '$.steps.score.output'\n"
            "---\n"
            "# Multi-step"
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert len(skill.steps) == 3
        assert skill.steps[0].name == "enrich"
        assert skill.steps[1].name == "score"
        assert skill.steps[2].name == "decide"

    def test_invalid_step_skipped(self, tmp_path: Path) -> None:
        """Step with neither tool, tools, nor prompt is skipped."""
        skill_dir = tmp_path / "bad-step"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: bad\n"
            "description: Bad step\n"
            "steps:\n"
            "  - name: empty-step\n"
            "---\n"
            "# Bad"
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert len(skill.steps) == 0

    def test_duplicate_step_name_skipped(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "dupe-step"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: dupe\n"
            "description: Duplicate step names\n"
            "tools:\n  - echo\n"
            "steps:\n"
            "  - name: fetch\n"
            "    tool: echo\n"
            "  - name: fetch\n"
            "    tool: echo\n"
            "---\n"
            "# Dupe"
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert len(skill.steps) == 1

    def test_step_missing_name_skipped(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "no-name"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: noname\n"
            "description: Missing step name\n"
            "steps:\n"
            "  - tool: echo\n"
            "---\n"
            "# No Name"
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert len(skill.steps) == 0

    def test_multiple_type_fields_skipped(self, tmp_path: Path) -> None:
        """Step with both tool and prompt is invalid."""
        skill_dir = tmp_path / "multi-type"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: multi\n"
            "description: Both tool and prompt\n"
            "steps:\n"
            "  - name: bad\n"
            "    tool: echo\n"
            "    prompt: Also a prompt\n"
            "---\n"
            "# Multi"
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert len(skill.steps) == 0
