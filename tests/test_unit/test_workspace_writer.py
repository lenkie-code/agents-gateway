"""Tests for workspace/writer.py -- AGENT.md frontmatter update utility."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_gateway.workspace.writer import AgentWriteError, update_agent_frontmatter


def _write_agent_md(agent_dir: Path, frontmatter: dict, body: str = "You are an agent.") -> None:
    agent_md = agent_dir / "AGENT.md"
    fm = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False)
    agent_md.write_text(f"---\n{fm}---\n\n{body}", encoding="utf-8")


def _read_agent_md(agent_dir: Path) -> tuple[dict, str]:
    agent_md = agent_dir / "AGENT.md"
    import frontmatter

    post = frontmatter.loads(agent_md.read_text(encoding="utf-8"))
    return dict(post.metadata), post.content


class TestUpdateAgentFrontmatter:
    def test_updates_single_field(self, tmp_path: Path) -> None:
        """Updating description preserves other fields and body."""
        _write_agent_md(tmp_path, {"description": "old", "tags": ["a"]})
        update_agent_frontmatter(tmp_path, {"description": "new"})
        meta, body = _read_agent_md(tmp_path)
        assert meta["description"] == "new"
        assert meta["tags"] == ["a"]

    def test_preserves_body_content(self, tmp_path: Path) -> None:
        """Markdown body after frontmatter is preserved exactly."""
        original_body = "You are a helpful assistant.\n\nDo great things."
        _write_agent_md(tmp_path, {"description": "test"}, body=original_body)
        update_agent_frontmatter(tmp_path, {"description": "updated"})
        _, body = _read_agent_md(tmp_path)
        assert body.strip() == original_body.strip()

    def test_preserves_unmodified_fields(self, tmp_path: Path) -> None:
        """Fields not in updates dict are left unchanged."""
        _write_agent_md(
            tmp_path,
            {"description": "d", "tags": ["x"], "execution_mode": "async"},
        )
        update_agent_frontmatter(tmp_path, {"description": "new"})
        meta, _ = _read_agent_md(tmp_path)
        assert meta["tags"] == ["x"]
        assert meta["execution_mode"] == "async"

    def test_updates_nested_model_field(self, tmp_path: Path) -> None:
        """Updating model.name deep-merges with existing model config."""
        _write_agent_md(
            tmp_path,
            {"model": {"name": "gpt-4o", "temperature": 0.5}},
        )
        update_agent_frontmatter(tmp_path, {"model": {"name": "gpt-4o-mini"}})
        meta, _ = _read_agent_md(tmp_path)
        assert meta["model"]["name"] == "gpt-4o-mini"
        assert meta["model"]["temperature"] == 0.5

    def test_raises_if_agent_md_missing(self, tmp_path: Path) -> None:
        """AgentWriteError raised if AGENT.md does not exist."""
        with pytest.raises(AgentWriteError):
            update_agent_frontmatter(tmp_path, {"description": "x"})

    def test_atomic_write_on_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Original file preserved if write fails midway."""
        _write_agent_md(tmp_path, {"description": "original"})
        original_content = (tmp_path / "AGENT.md").read_text(encoding="utf-8")

        # Make Path.replace raise to simulate a write failure
        def bad_replace(self: Path, target: Path) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(Path, "replace", bad_replace)
        with pytest.raises(OSError):
            update_agent_frontmatter(tmp_path, {"description": "new"})

        # Original file should be unchanged
        assert (tmp_path / "AGENT.md").read_text(encoding="utf-8") == original_content

    def test_updates_enabled_field(self, tmp_path: Path) -> None:
        """Can set enabled: false in frontmatter."""
        _write_agent_md(tmp_path, {"description": "test", "enabled": True})
        update_agent_frontmatter(tmp_path, {"enabled": False})
        meta, _ = _read_agent_md(tmp_path)
        assert meta["enabled"] is False
