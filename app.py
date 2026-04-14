"""Lenkie agents-gateway — local dev entry point."""

from dotenv import load_dotenv

from agent_gateway import Gateway

load_dotenv()

gw = Gateway(
    workspace="./workspace",
    title="Lenkie Agent Gateway",
    description="Lenkie's AI agent platform — local dev.",
    version="0.1.0",
)

gw.use_api_keys(
    [
        {
            "name": "dev",
            "key": "dev-api-key",
            "scopes": ["*"],
        }
    ]
)

if __name__ == "__main__":
    gw.run(port=8001)
