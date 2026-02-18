"""Gateway - FastAPI subclass for AI agent services."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI


class Gateway(FastAPI):
    """An opinionated FastAPI extension for building API-first AI agent services.

    Subclasses FastAPI directly. Everything you can do with a FastAPI app,
    you can do with a Gateway.
    """

    def __init__(
        self,
        workspace: str = "./workspace",
        auth: bool | None = True,
        reload: bool = False,
        **fastapi_kwargs: Any,
    ) -> None:
        self._workspace_path = workspace
        self._auth_enabled = auth
        self._reload_enabled = reload
        super().__init__(**fastapi_kwargs)

    def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        **kwargs: object,
    ) -> None:
        """Start the gateway server using uvicorn."""
        import uvicorn

        uvicorn.run(self, host=host, port=port, **kwargs)  # type: ignore[arg-type]
