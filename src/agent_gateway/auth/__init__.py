"""Pluggable authentication for the Agent Gateway."""

from agent_gateway.auth.domain import AuthResult
from agent_gateway.auth.protocols import AuthProvider

__all__ = ["AuthProvider", "AuthResult"]
