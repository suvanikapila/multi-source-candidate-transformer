"""
phone_normalizer.py — Normalize phone numbers to E.164 format.

Uses the `phonenumbers` library. Default region fallback = "US" if no country
code present. Returns None if the number is unparseable or invalid — never
invents a number.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import phonenumbers
    from phonenumbers import NumberParseException
    _HAS_PHONENUMBERS = True
except ImportError:
    _HAS_PHONENUMBERS = False
    logger.warning("phone_normalizer: 'phonenumbers' library not installed. "
                   "Phone normalization will be skipped.")

DEFAULT_REGION = "US"


def normalize_phone(raw: Optional[str], default_region: str = DEFAULT_REGION) -> Optional[str]:
    """
    Normalize a phone number string to E.164 format (e.g. +14155552671).

    Args:
        raw:            Raw phone string.
        default_region: ISO-3166 alpha-2 country code used when no country
                        code is present in the number (default: "US").

    Returns E.164 string or None if unparseable / invalid.
    """
    if not raw:
        return None

    raw = str(raw).strip()
    if not raw:
        return None

    if not _HAS_PHONENUMBERS:
        # Graceful degradation: return cleaned digit string
        digits = re.sub(r"[^\d+]", "", raw)
        return digits if digits else None

    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
        # Try without region hint (might have country code)
        parsed_intl = phonenumbers.parse(raw, None)
        if phonenumbers.is_valid_number(parsed_intl):
            return phonenumbers.format_number(
                parsed_intl, phonenumbers.PhoneNumberFormat.E164
            )
        logger.debug("phone_normalizer: invalid number '%s'", raw)
        return None
    except NumberParseException:
        logger.debug("phone_normalizer: cannot parse '%s'", raw)
        return None
    except Exception as exc:
        logger.debug("phone_normalizer: unexpected error for '%s': %s", raw, exc)
        return None


def normalize_phones(raw_list: list, default_region: str = DEFAULT_REGION) -> list:
    """Normalize a list of phone strings, dropping unparseable ones."""
    results = []
    seen = set()
    for raw in (raw_list or []):
        normalized = normalize_phone(raw, default_region)
        if normalized and normalized not in seen:
            seen.add(normalized)
            results.append(normalized)
    return results
