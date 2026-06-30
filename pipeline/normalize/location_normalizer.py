"""
location_normalizer.py — Normalize location strings to canonical form.

Parses raw location strings (e.g. "San Francisco, CA, USA", "Bangalore, India")
and produces:
  { "city": str|None, "region": str|None, "country": "ISO-3166 alpha-2"|None }

Uses `pycountry` for country lookup. Gracefully returns partial results when
parts cannot be resolved.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pycountry
    _HAS_PYCOUNTRY = True
except ImportError:
    _HAS_PYCOUNTRY = False
    logger.warning("location_normalizer: 'pycountry' not installed. "
                   "Country normalization skipped.")

# Common country name aliases not in pycountry
COUNTRY_ALIASES = {
    "usa": "US", "us": "US", "united states": "US", "united states of america": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB", "britain": "GB",
    "uae": "AE", "emirates": "AE",
    "south korea": "KR",
    "north korea": "KP",
    "russia": "RU",
    "taiwan": "TW",
    "vietnam": "VN",
    "iran": "IR",
    "czech republic": "CZ",
    "slovakia": "SK",
    "hong kong": "HK",
}

# US State abbreviations
US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
    "TX","UT","VT","VA","WA","WV","WI","WY","DC",
}


def normalize_location(raw: Optional[str]) -> dict:
    """
    Parse a raw location string and return a dict with city, region, country.
    Always returns a dict (never raises). Unknown parts → None.
    """
    empty = {"city": None, "region": None, "country": None}

    if not raw or not str(raw).strip():
        return empty

    raw = str(raw).strip()

    # Split on common separators: ", " or " - "
    parts = [p.strip() for p in re.split(r",\s*|\s+[-–]\s+", raw) if p.strip()]

    city = None
    region = None
    country_alpha2 = None

    if len(parts) == 1:
        # Try to resolve as country first
        resolved = _resolve_country(parts[0])
        if resolved:
            country_alpha2 = resolved
        else:
            city = parts[0]

    elif len(parts) == 2:
        # city, country  OR  city, state (US)
        city = parts[0]
        country_alpha2 = _resolve_country(parts[1])
        if not country_alpha2:
            # Maybe it's a state abbreviation
            if parts[1].upper() in US_STATES:
                region = parts[1].upper()
                country_alpha2 = "US"
            else:
                region = parts[1]

    elif len(parts) >= 3:
        # city, region/state, country
        city = parts[0]
        region = parts[1]
        country_alpha2 = _resolve_country(parts[-1])
        if not country_alpha2:
            # Last part might be state if not recognized
            region = parts[1]

    return {
        "city": city,
        "region": region,
        "country": country_alpha2,
    }


def normalize_country(raw: Optional[str]) -> Optional[str]:
    """Resolve a country name/code string to ISO-3166 alpha-2. Returns None if unknown."""
    if not raw:
        return None
    return _resolve_country(str(raw).strip())


def _resolve_country(text: str) -> Optional[str]:
    """Internal: try to resolve text to ISO-3166 alpha-2 code."""
    if not text:
        return None

    key = text.strip().lower()

    # Direct alias check
    alias = COUNTRY_ALIASES.get(key)
    if alias:
        return alias

    # Already a 2-letter code?
    if len(text) == 2 and text.upper().isalpha():
        if _HAS_PYCOUNTRY:
            try:
                c = pycountry.countries.get(alpha_2=text.upper())
                if c:
                    return c.alpha_2
            except Exception:
                pass
        return text.upper()  # best-effort

    if not _HAS_PYCOUNTRY:
        return None

    # Search by name
    try:
        results = pycountry.countries.search_fuzzy(text)
        if results:
            return results[0].alpha_2
    except LookupError:
        pass
    except Exception:
        pass

    return None
