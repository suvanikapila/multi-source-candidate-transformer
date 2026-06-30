"""
date_normalizer.py — Normalize date strings to YYYY-MM format.

Handles many real-world date formats found in resumes and ATS systems:
  "Jan 2020", "January 2020", "01/2020", "2020-01", "2020",
  "Jan '20", "Q1 2020", etc.

Returns YYYY-MM string, or None if unparseable.
"""

import re
from typing import Optional

MONTH_MAP = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

QUARTER_MAP = {"q1": "03", "q2": "06", "q3": "09", "q4": "12"}

# Pattern: Mon YYYY or YYYY Mon (e.g. "Jan 2020", "2020 Jan")
MON_YEAR_RE = re.compile(
    r"(?i)(?P<mon>[A-Za-z]+)['\s,.-]+(?P<year>(?:19|20)\d{2})"
    r"|(?P<year2>(?:19|20)\d{2})['\s,.-]+(?P<mon2>[A-Za-z]+)"
)

# Pattern: MM/YYYY or YYYY/MM or MM-YYYY
NUM_MONTH_YEAR_RE = re.compile(
    r"(?P<m>\d{1,2})[/\-](?P<y>(?:19|20)\d{2})"
    r"|(?P<y2>(?:19|20)\d{2})[/\-](?P<m2>\d{1,2})"
)

# Pattern: YYYY-MM-DD
ISO_RE = re.compile(r"(?P<y>(?:19|20)\d{2})-(?P<m>\d{2})(?:-\d{2})?")

# Pattern: Quarter
QUARTER_RE = re.compile(r"(?i)(?P<q>Q[1-4])\s*(?P<y>(?:19|20)\d{2})")

# Pattern: bare year
YEAR_RE = re.compile(r"\b(?P<y>(?:19|20)\d{2})\b")


def normalize_date(raw: Optional[str]) -> Optional[str]:
    """
    Convert a raw date string to YYYY-MM.
    Returns None if the value is None, empty, or unparseable.
    """
    if not raw:
        return None

    raw = str(raw).strip()
    if not raw:
        return None

    # ISO format: YYYY-MM or YYYY-MM-DD
    m = ISO_RE.match(raw)
    if m:
        return f"{m.group('y')}-{m.group('m').zfill(2)}"

    # Quarter: Q1 2020 → 2020-03
    m = QUARTER_RE.search(raw)
    if m:
        month = QUARTER_MAP[m.group("q").lower()]
        return f"{m.group('y')}-{month}"

    # Month name + year
    m = MON_YEAR_RE.search(raw)
    if m:
        mon_str = (m.group("mon") or m.group("mon2") or "").lower().rstrip(".")
        year = m.group("year") or m.group("year2")
        month = MONTH_MAP.get(mon_str)
        if month and year:
            return f"{year}-{month}"

    # Numeric: MM/YYYY or YYYY/MM
    m = NUM_MONTH_YEAR_RE.search(raw)
    if m:
        mo = m.group("m") or m.group("m2") or ""
        yr = m.group("y") or m.group("y2") or ""
        if 1 <= int(mo) <= 12 and yr:
            return f"{yr}-{mo.zfill(2)}"

    # Bare year → YYYY-01 (Jan as default)
    m = YEAR_RE.search(raw)
    if m:
        return f"{m.group('y')}-01"

    return None


def normalize_year(raw: Optional[str]) -> Optional[int]:
    """Extract a 4-digit year as int from a string. Returns None if not found."""
    if not raw:
        return None
    m = YEAR_RE.search(str(raw))
    if m:
        return int(m.group("y"))
    return None
