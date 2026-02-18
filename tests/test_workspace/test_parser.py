"""Tests for markdown + YAML frontmatter parser."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.workspace.parser import parse_markdown_file, parse_markdown_string


class TestParseMarkdownFile:
    def test_file_with_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("---\nname: test\ntags:\n  - a\n  - b\n---\n# Hello\n\nBody text.")
        result = parse_markdown_file(md)
        assert result.metadata["name"] == "test"
        assert result.metadata["tags"] == ["a", "b"]
        assert "# Hello" in result.content
        assert "Body text." in result.content
        assert result.path == md

    def test_file_without_frontmatter(self, tmp_path: Path) -> None:
        md = tmp_path / "plain.md"
        md.write_text("# Just Markdown\n\nNo frontmatter here.")
        result = parse_markdown_file(md)
        assert result.metadata == {}
        assert "# Just Markdown" in result.content

    def test_empty_file(self, tmp_path: Path) -> None:
        md = tmp_path / "empty.md"
        md.write_text("")
        result = parse_markdown_file(md)
        assert result.content == ""
        assert result.metadata == {}
        assert result.path == md

    def test_whitespace_only_file(self, tmp_path: Path) -> None:
        md = tmp_path / "spaces.md"
        md.write_text("   \n  \n  ")
        result = parse_markdown_file(md)
        assert result.content == ""

    def test_invalid_utf8(self, tmp_path: Path) -> None:
        md = tmp_path / "bad.md"
        md.write_bytes(b"\x80\x81\x82")
        result = parse_markdown_file(md)
        assert result.content == ""
        assert result.path == md

    def test_frontmatter_only(self, tmp_path: Path) -> None:
        md = tmp_path / "meta.md"
        md.write_text("---\nkey: value\n---\n")
        result = parse_markdown_file(md)
        assert result.metadata["key"] == "value"
        assert result.content.strip() == ""


class TestParseMarkdownString:
    def test_with_frontmatter(self) -> None:
        text = "---\nname: hello\n---\n# Body"
        result = parse_markdown_string(text)
        assert result.metadata["name"] == "hello"
        assert "# Body" in result.content

    def test_without_frontmatter(self) -> None:
        result = parse_markdown_string("# Plain text")
        assert result.metadata == {}
        assert "# Plain text" in result.content

    def test_empty_string(self) -> None:
        result = parse_markdown_string("")
        assert result.content == ""
        assert result.metadata == {}

    def test_whitespace_only(self) -> None:
        result = parse_markdown_string("   ")
        assert result.content == ""
