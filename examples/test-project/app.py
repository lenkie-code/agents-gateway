"""Test project for agent-gateway development."""

from agent_gateway import Gateway

gw = Gateway(workspace="./workspace", auth=False, title="Test Project")


@gw.tool()
async def echo(message: str) -> dict:
    """Echo a message back - for testing the tool pipeline."""
    return {"echo": message}


@gw.tool()
async def add_numbers(a: float, b: float) -> dict:
    """Add two numbers - for testing structured params."""
    return {"result": a + b}


@gw.get("/api/health")
async def health():
    return {"status": "ok", "project": "test-project"}


if __name__ == "__main__":
    gw.run(port=8000)
