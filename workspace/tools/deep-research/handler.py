"""Deep research tool handler.

Uses Google's deep-research-pro agent via the google-genai SDK to perform
autonomous multi-source web research. Requires:
  GEMINI_API_KEY — the same key used by LiteLLM for Gemini model calls
"""

from __future__ import annotations

import os
import time
from typing import Any

_API_KEY_ENV = "GEMINI_API_KEY"
_RESEARCH_AGENT = "deep-research-pro-preview-12-2025"
_DEFAULT_TIMEOUT = 120
_POLL_INTERVAL = 5


def handle(arguments: dict[str, Any], context: Any) -> dict[str, Any]:
    """Run deep research via the Google genai SDK."""
    try:
        from google import genai  # noqa: PLC0415
    except ImportError:
        return {"error": "google-genai package is not installed. Add it to pyproject.toml dependencies."}

    api_key = os.environ.get(_API_KEY_ENV, "").strip()
    if not api_key:
        return {"error": f"Configuration error: {_API_KEY_ENV} environment variable is not set."}

    prompt = arguments.get("prompt", "").strip()
    if not prompt:
        return {"error": "prompt parameter is required and must not be empty."}

    timeout = int(arguments.get("timeout_seconds", _DEFAULT_TIMEOUT))

    client = genai.Client(api_key=api_key)

    try:
        interaction = client.interactions.create(
            input=prompt,
            agent=_RESEARCH_AGENT,
            background=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Failed to start deep research: {exc}"}

    start = time.time()

    while True:
        elapsed = time.time() - start

        if elapsed > timeout:
            return {
                "error": f"Deep research timed out after {timeout}s for prompt: {prompt[:120]}"
            }

        time.sleep(_POLL_INTERVAL)

        try:
            status = client.interactions.get(id=interaction.id)
        except Exception as exc:  # noqa: BLE001
            # Transient poll error — keep waiting
            continue

        if status.status == "completed":
            report = status.outputs[-1].text if status.outputs else ""
            return {"report": report}

        if status.status == "failed":
            error_msg = getattr(status, "error_message", "Unknown error")
            return {"error": f"Deep research failed: {error_msg}"}
