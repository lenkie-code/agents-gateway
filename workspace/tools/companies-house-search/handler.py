"""Companies House directory search tool handler.

Calls the Lenkie Working Capital API's Companies House directory endpoint
to find UK registered companies matching the supplied filters.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_CORE_API_URL_KEY = "CORE_API_URL"


def handle(arguments: dict[str, Any], context: Any) -> dict[str, Any]:
    """Search the Companies House directory via the Working Capital API."""
    base_url = os.environ.get(_CORE_API_URL_KEY, "").rstrip("/")
    if not base_url:
        return {
            "error": f"Configuration error: {_CORE_API_URL_KEY} environment variable is not set."
        }

    params = _build_params(arguments)
    url = f"{base_url}/lookups/companies-house-directory?{params}"

    req = Request(url, headers={"Accept": "application/json"})

    try:
        with urlopen(req, timeout=30) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as exc:
        error_body = ""
        with contextlib.suppress(Exception):
            error_body = exc.read().decode("utf-8")
        return {
            "error": f"API error {exc.code}: {exc.reason}",
            "detail": error_body[:500] if error_body else None,
        }
    except URLError as exc:
        return {"error": f"Connection error: {exc.reason}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Unexpected error: {exc}"}


def _build_params(arguments: dict[str, Any]) -> str:
    """Build URL query string from tool arguments, handling multi-value params."""
    parts: list[tuple[str, str]] = []

    # Single-value string params
    for key in (
        "company_number",
        "name_search",
        "postcode",
        "incorporation_date_from",
        "incorporation_date_to",
        "last_accounts_date_from",
        "last_accounts_date_to",
        "next_accounts_due_from",
        "next_accounts_due_to",
        "last_confirmation_date_from",
        "last_confirmation_date_to",
        "next_confirmation_due_from",
        "next_confirmation_due_to",
    ):
        val = arguments.get(key)
        if val is not None:
            parts.append((key, str(val)))

    # Integer params
    page_defaults = {"page_number": 1, "page_size": 15}
    for key in ("page_number", "page_size"):
        val = arguments.get(key)
        if val is not None:
            parts.append((key, str(int(val))))
        elif key in page_defaults:
            parts.append((key, str(page_defaults[key])))

    # Multi-value params (OR logic) — repeated query-string keys
    for key in ("sic_codes", "statuses", "company_types"):
        values = arguments.get(key)
        if values:
            if isinstance(values, str):
                # Accept comma-separated string as a convenience
                values = [v.strip() for v in values.split(",") if v.strip()]
            for v in values:
                parts.append((key, str(v)))

    # Default status to Active when not specified and no company_number override
    if "statuses" not in arguments and "company_number" not in arguments:
        parts.append(("statuses", "Active"))

    return urlencode(parts)
