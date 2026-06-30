"""
project.py — Stateless projection layer.

Reads a runtime config and reshapes the canonical record into the requested
output format — WITHOUT mutating the canonical record itself.

Config shape:
{
  "fields": [
    { "path": "full_name",      "type": "string",   "required": true },
    { "path": "primary_email",  "from": "emails[0]","type": "string",   "required": true },
    { "path": "phone",          "from": "phones[0]","type": "string",   "normalize": "E164" },
    { "path": "skills",         "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "on_missing": "null"          // "null" | "omit" | "error"
}

Path syntax:
  "field"           → canonical["field"]
  "field[0]"        → canonical["field"][0]
  "field[].key"     → [item["key"] for item in canonical["field"]]
  "field.subfield"  → canonical["field"]["subfield"]
"""

import copy
import logging
import re
from typing import Any, Optional

from pipeline.normalize.phone_normalizer import normalize_phone
from pipeline.normalize.skill_normalizer import normalize_skill

logger = logging.getLogger(__name__)

INDEX_RE = re.compile(r"^(\w+)\[(\d+|\*|)\](.*)$")


def project(canonical: dict, config: Optional[dict]) -> dict:
    """
    Apply the runtime config to produce a projected output record.

    Args:
        canonical:  The merged + confidence-scored canonical record.
        config:     The runtime output config dict (or None for default output).

    Returns:
        A new dict shaped per the config (canonical record is NOT mutated).
    """
    if not config or not config.get("fields"):
        # No config → return canonical record as-is (minus internal fields)
        return _default_projection(canonical, config)

    on_missing = config.get("on_missing", "null")   # null | omit | error
    include_confidence = config.get("include_confidence", False)

    output: dict = {}

    for field_spec in config["fields"]:
        path     = field_spec.get("path")
        from_key = field_spec.get("from") or path
        required = field_spec.get("required", False)
        normalize = field_spec.get("normalize")
        ftype    = field_spec.get("type", "string")

        if not path:
            continue

        # Resolve value from canonical using the "from" path
        value = _resolve_path(canonical, from_key)

        # Apply normalization override
        if value is not None and normalize:
            value = _apply_normalize(value, normalize)

        # Handle missing
        if value is None:
            if required and on_missing == "error":
                raise ValueError(f"Required field '{path}' is missing in canonical record.")
            if on_missing == "omit":
                continue
            # on_missing == "null" (default) → include with null
            output[path] = None
        else:
            # Type coercion (best-effort)
            output[path] = _coerce(value, ftype)

    # Optionally include confidence
    if include_confidence:
        output["overall_confidence"] = canonical.get("overall_confidence", 0.0)
        output["provenance"] = canonical.get("provenance", [])

    return output


def _default_projection(canonical: dict, config: Optional[dict]) -> dict:
    """Return the canonical record with no structural changes."""
    out = copy.deepcopy(canonical)
    include_confidence = (config or {}).get("include_confidence", True)
    if not include_confidence:
        out.pop("overall_confidence", None)
        out.pop("provenance", None)
    return out


def _resolve_path(canonical: dict, path: str) -> Any:
    """
    Resolve a dotted/indexed path against a dict.

    Supported:
        "full_name"         → canonical["full_name"]
        "emails[0]"         → canonical["emails"][0]
        "skills[].name"     → [s["name"] for s in canonical["skills"]]
        "location.country"  → canonical["location"]["country"]
    """
    if not path:
        return None

    parts = _split_path(path)
    value = canonical

    for part in parts:
        if value is None:
            return None

        m = INDEX_RE.match(part)
        if m:
            key    = m.group(1)
            index  = m.group(2)
            rest   = m.group(3).lstrip(".")

            sub = value.get(key) if isinstance(value, dict) else None
            if sub is None:
                return None

            if index == "" or index == "*":
                # Array expansion: skills[].name
                # Collect remaining parts AFTER this one to form the sub-path
                remaining_parts = parts[parts.index(part) + 1:]
                sub_path = ".".join(remaining_parts) if remaining_parts else rest

                if sub_path and isinstance(sub, list):
                    results = []
                    for item in sub:
                        if isinstance(item, dict):
                            v = _resolve_path(item, sub_path)
                        else:
                            v = item
                        if v is not None:
                            results.append(v)
                    return results if results else None
                elif rest and isinstance(sub, list):
                    results = []
                    for item in sub:
                        v = _resolve_path(item, rest) if isinstance(item, dict) else item
                        if v is not None:
                            results.append(v)
                    return results if results else None
                return sub
            else:
                # Specific index: emails[0]
                idx = int(index)
                if isinstance(sub, list) and 0 <= idx < len(sub):
                    value = sub[idx]
                else:
                    return None
                if rest:
                    # If there's still a rest path, resolve it now and return
                    remaining_parts = parts[parts.index(part) + 1:]
                    sub_path = ".".join(remaining_parts) if remaining_parts else rest
                    if sub_path:
                        return _resolve_path(value, sub_path) if isinstance(value, dict) else value
                continue
        else:
            # Plain key (including dot-separated)
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

    return value



def _split_path(path: str) -> list:
    """
    Split a path string into parts, handling bracket notation.
    "skills[].name" → ["skills[]", "name"]
    "emails[0]" → ["emails[0]"]
    "location.country" → ["location", "country"]
    """
    # Split on "." but not inside brackets
    parts = []
    current = ""
    depth = 0
    for ch in path:
        if ch == "[":
            depth += 1
            current += ch
        elif ch == "]":
            depth -= 1
            current += ch
        elif ch == "." and depth == 0:
            if current:
                parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return parts


def _apply_normalize(value: Any, normalize: str) -> Any:
    """Apply a normalization function by name."""
    n = normalize.lower()
    if n == "e164":
        if isinstance(value, list):
            return [normalize_phone(v) for v in value]
        return normalize_phone(str(value))
    if n in ("canonical", "skill_canonical"):
        if isinstance(value, list):
            results = []
            for v in value:
                if isinstance(v, dict):
                    v = v.get("name") or str(v)
                results.append(normalize_skill(str(v))[0])
            return results
        return normalize_skill(str(value))[0]
    # Unknown normalize → pass through
    return value


def _coerce(value: Any, ftype: str) -> Any:
    """Best-effort type coercion."""
    if ftype == "string":
        return str(value) if value is not None else None
    if ftype == "string[]":
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]
    if ftype == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if ftype == "boolean":
        return bool(value)
    return value
