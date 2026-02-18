"""Tests for skill model loading."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.workspace.skill import SkillDefinition


class TestSkillDefinition:
    def test_load_skill_with_tools(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "math-workflow"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: math-workflow\n"
            "description: Multi-step arithmetic\n"
            "tools:\n  - add-numbers\n  - multiply\n"
            "---\n"
            "# Math Workflow\n\nBreak problems into steps."
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert skill.id == "math-workflow"
        assert skill.name == "math-workflow"
        assert skill.description == "Multi-step arithmetic"
        assert skill.tools == ["add-numbers", "multiply"]
        assert "Break problems into steps" in skill.instructions

    def test_load_skill_without_tools(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "simple-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: simple\n"
            "description: A simple skill\n"
            "---\n"
            "# Instructions\n\nJust do the thing."
        )

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert skill.tools == []

    def test_missing_skill_md_returns_none(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "no-skill"
        skill_dir.mkdir()
        assert SkillDefinition.load(skill_dir) is None

    def test_missing_description_uses_empty(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "no-desc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: no-desc\n---\n# Skill\n\nInstructions.")

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert skill.description == ""

    def test_name_defaults_to_dir_name(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: A skill\n---\n# Skill")

        skill = SkillDefinition.load(skill_dir)
        assert skill is not None
        assert skill.name == "my-skill"
