"""Shared fixtures for dashboard tests."""

from __future__ import annotations

from agent_gateway.config import DashboardAuthConfig


def make_auth_config(**overrides: object) -> DashboardAuthConfig:
    """Build a DashboardAuthConfig with sensible test defaults."""
    defaults: dict[str, object] = {
        "enabled": True,
        "username": "testuser",
        "password": "testpass",
        "admin_username": "admin",
        "admin_password": "adminpass",
    }
    defaults.update(overrides)
    return DashboardAuthConfig(**defaults)
