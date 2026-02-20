"""Integration tests for agent introspection endpoints."""

from __future__ import annotations

from pathlib import Path

from agent_gateway.gateway import Gateway

from .conftest import make_test_client


async def test_list_agents_includes_metadata(tmp_path: Path) -> None:
    """GET /v1/agents returns agents with public metadata fields."""
    agent_dir = tmp_path / "workspace" / "agents" / "my-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "description: A test agent\n"
        "display_name: My Agent\n"
        "tags:\n  - test\n  - demo\n"
        "version: '2.0.0'\n"
        "---\n"
        "# My Agent\n\nYou are a secret prompt."
    )

    gw = Gateway(workspace=str(tmp_path / "workspace"), auth=False)
    ac = await make_test_client(gw)
    try:
        resp = await ac.get("/v1/agents")
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 1

        agent = agents[0]
        assert agent["id"] == "my-agent"
        assert agent["description"] == "A test agent"
        assert agent["display_name"] == "My Agent"
        assert agent["tags"] == ["test", "demo"]
        assert agent["version"] == "2.0.0"
    finally:
        await ac.aclose()
        await gw._shutdown()


async def test_get_agent_includes_metadata(tmp_path: Path) -> None:
    """GET /v1/agents/{id} returns agent with public metadata fields."""
    agent_dir = tmp_path / "workspace" / "agents" / "my-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\n"
        "description: Detailed agent\n"
        "display_name: Detailed\n"
        "tags:\n  - detail\n"
        "version: '1.0.0'\n"
        "---\n"
        "# Agent\n\nInternal prompt here."
    )

    gw = Gateway(workspace=str(tmp_path / "workspace"), auth=False)
    ac = await make_test_client(gw)
    try:
        resp = await ac.get("/v1/agents/my-agent")
        assert resp.status_code == 200
        agent = resp.json()
        assert agent["description"] == "Detailed agent"
        assert agent["display_name"] == "Detailed"
        assert agent["tags"] == ["detail"]
        assert agent["version"] == "1.0.0"
    finally:
        await ac.aclose()
        await gw._shutdown()


async def test_agent_prompt_not_exposed(tmp_path: Path) -> None:
    """Agent prompt content must never appear in API responses."""
    agent_dir = tmp_path / "workspace" / "agents" / "secret-agent"
    agent_dir.mkdir(parents=True)
    secret_prompt = "TOP_SECRET_PROMPT_CONTENT_12345"
    (agent_dir / "AGENT.md").write_text(
        f"---\ndescription: A public description\n---\n# Agent\n\n{secret_prompt}"
    )

    gw = Gateway(workspace=str(tmp_path / "workspace"), auth=False)
    ac = await make_test_client(gw)
    try:
        # Check list endpoint
        resp = await ac.get("/v1/agents")
        assert secret_prompt not in resp.text

        # Check detail endpoint
        resp = await ac.get("/v1/agents/secret-agent")
        assert secret_prompt not in resp.text
    finally:
        await ac.aclose()
        await gw._shutdown()


async def test_agent_description_fallback(tmp_path: Path) -> None:
    """Agent without description gets auto-generated fallback from id."""
    agent_dir = tmp_path / "workspace" / "agents" / "bare-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text("# Agent\n\nJust a prompt, no frontmatter.")

    gw = Gateway(workspace=str(tmp_path / "workspace"), auth=False)
    ac = await make_test_client(gw)
    try:
        resp = await ac.get("/v1/agents/bare-agent")
        assert resp.status_code == 200
        agent = resp.json()
        assert agent["description"] == "Agent: bare-agent"
        assert agent["display_name"] is None
        assert agent["tags"] == []
        assert agent["version"] is None
    finally:
        await ac.aclose()
        await gw._shutdown()
