"""Agent Gateway - a FastAPI extension for AI agent services."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agent-gateway")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from agent_gateway.context.protocol import ContextRetriever
from agent_gateway.gateway import Gateway

__all__ = ["ContextRetriever", "Gateway", "__version__"]
