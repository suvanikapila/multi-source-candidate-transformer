"""
validate.py — Validate a projected output record against a JSON Schema.

For the default output, validates against schemas/canonical_schema.json.
For a custom config output, derives a minimal schema from the config fields.

Validation errors are returned as a list of strings (never raises).
A valid result returns an empty errors list.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import jsonschema
    from jsonschema import Draft7Validator
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False
    logger.warning("validate: 'jsonschema' not installed. Validation skipped.")


def _load_canonical_schema() -> Optional[dict]:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    schema_path = os.path.join(base, "schemas", "canonical_schema.json")
    try:
        with open(schema_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("validate: could not load canonical schema: %s", exc)
        return None


def validate(record: dict, config: Optional[dict] = None) -> list:
    """
    Validate `record` against the appropriate schema.

    Args:
        record:  The projected output record to validate.
        config:  The runtime config (used to derive schema for custom output).
                 If None → validates against canonical schema.

    Returns:
        List of error message strings. Empty list = valid.
    """
    if not _HAS_JSONSCHEMA:
        return []  # graceful degradation

    schema = None

    if config and config.get("fields"):
        schema = _derive_schema_from_config(config)
    else:
        schema = _load_canonical_schema()

    if not schema:
        logger.warning("validate: no schema available — skipping validation.")
        return []

    errors = []
    try:
        validator = Draft7Validator(schema)
        for error in sorted(validator.iter_errors(record), key=str):
            errors.append(f"{'.'.join(str(p) for p in error.absolute_path) or 'root'}: {error.message}")
    except Exception as exc:
        logger.warning("validate: schema validation error: %s", exc)

    return errors


def _derive_schema_from_config(config: dict) -> dict:
    """Build a minimal JSON Schema from a custom config's field list."""
    schema: dict = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": True,
    }

    type_map = {
        "string":   {"type": ["string", "null"]},
        "string[]": {"type": ["array", "null"], "items": {"type": "string"}},
        "number":   {"type": ["number", "null"]},
        "boolean":  {"type": ["boolean", "null"]},
    }

    on_missing = config.get("on_missing", "null")

    for field_spec in config.get("fields", []):
        path = field_spec.get("path")
        if not path:
            continue
        ftype = field_spec.get("type", "string")
        required = field_spec.get("required", False)

        prop_schema = type_map.get(ftype, {"type": ["string", "null"]}).copy()

        # If required AND on_missing is error, field must be non-null
        if required and on_missing == "error":
            prop_schema = {"type": ftype if ftype else "string"}
            schema["required"].append(path)

        schema["properties"][path] = prop_schema

    if config.get("include_confidence"):
        schema["properties"]["overall_confidence"] = {"type": "number"}

    return schema
