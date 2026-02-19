"""Structured output validation — parse and validate LLM output against JSON Schema."""

from __future__ import annotations

import json
import logging
from typing import Any

import jsonschema
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

CORRECTION_PROMPT = (
    "Your response did not match the required JSON schema.\n"
    "Errors: {errors}\n\n"
    "Please respond again with valid JSON matching this schema:\n"
    "```json\n{schema}\n```"
)

SCHEMA_INSTRUCTION = (
    "\n\n## Required Output Format\n\n"
    "You MUST respond with valid JSON matching this schema:\n"
    "```json\n{schema}\n```\n"
    "Do not include any other text outside the JSON object."
)


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences that LLMs often wrap around JSON output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove opening fence (```json, ```, etc.)
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        # Remove closing fence
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()
    return stripped


def build_schema_instruction(schema: dict[str, Any]) -> str:
    """Build the schema instruction to append to the system prompt."""
    return SCHEMA_INSTRUCTION.format(schema=json.dumps(schema, indent=2))


def validate_output(
    raw_text: str,
    schema: dict[str, Any],
) -> tuple[Any | None, list[str]]:
    """Validate raw LLM output against a JSON Schema.

    Returns:
        (parsed_output, errors) — parsed_output is None if validation fails.
    """
    # Try to parse JSON (strip code fences LLMs often add)
    cleaned = _strip_code_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as e:
        return None, [f"Invalid JSON: {e}"]

    # Validate against schema
    try:
        jsonschema.validate(instance=parsed, schema=schema)
    except jsonschema.ValidationError as e:
        return None, [e.message]

    return parsed, []


def resolve_schema(
    schema: dict[str, Any] | type[BaseModel],
) -> tuple[dict[str, Any], type[BaseModel] | None]:
    """Normalize an output schema to (json_schema_dict, optional model class).

    If *schema* is a Pydantic model class, the JSON Schema is generated
    automatically and the class is returned for later validation.
    If it's already a raw dict, it's passed through unchanged.
    """
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_json_schema(), schema
    return schema, None


def validate_output_pydantic(
    raw_text: str,
    model_cls: type[BaseModel],
) -> tuple[Any | None, list[str]]:
    """Validate raw LLM output by parsing into a Pydantic model.

    Returns:
        (model_instance, []) on success, or (None, [error_messages]) on failure.
    """
    cleaned = _strip_code_fences(raw_text)
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as e:
        return None, [f"Invalid JSON: {e}"]

    try:
        return model_cls.model_validate(parsed), []
    except ValidationError as e:
        return None, [err["msg"] for err in e.errors()]


def build_correction_message(
    errors: list[str],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Build a correction prompt message for the LLM to retry."""
    return {
        "role": "user",
        "content": CORRECTION_PROMPT.format(
            errors="; ".join(errors),
            schema=json.dumps(schema, indent=2),
        ),
    }
