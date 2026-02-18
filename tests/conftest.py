"""Shared test fixtures for agent-gateway."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_WORKSPACE = FIXTURES_DIR / "workspace"


@pytest.fixture
def fixture_workspace() -> Path:
    """Path to the test fixture workspace."""
    return FIXTURE_WORKSPACE


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory with standard structure."""
    agents = tmp_path / "agents"
    skills = tmp_path / "skills"
    tools = tmp_path / "tools"
    agents.mkdir()
    skills.mkdir()
    tools.mkdir()
    return tmp_path
