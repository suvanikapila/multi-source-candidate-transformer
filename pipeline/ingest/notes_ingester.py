"""
notes_ingester.py — Recruiter notes (.txt) ingester (unstructured source).

Free-text recruiter notes may contain fragments like:
  "Great candidate — 5 years Python, worked at Google"
  "Email: john@example.com, Phone: +1-555-0100"
  "Skills: Docker, Kubernetes, AWS"

Uses regex patterns to extract key signals.
Lower extraction confidence because values are informal.

Emits an IntermediateRecord tagged with source="notes".
Missing/unreadable file → logged warning, returns None (pipeline continues).
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_PRIORITY = 0.60
EXTRACTION_CONFIDENCE = 0.55   # Free text → lowest extraction certainty

EMAIL_RE    = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE    = re.compile(r"(?:\+?\d[\d\s\-().]{7,}\d)")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+/?", re.I)
GITHUB_RE   = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", re.I)

YEARS_EXP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?years?\s+(?:of\s+)?(?:experience|exp)", re.I
)

# Skills keyword (after "skills:" or "knows:" or "proficient in:")
SKILLS_LABEL_RE = re.compile(
    r"(?:skills?|proficient\s+in|knows?|expertise|tech(?:nologies)?)\s*[:\-]\s*(.+)",
    re.I,
)

# Company mentions (after "at", "worked at", "formerly at", "currently at")
COMPANY_RE = re.compile(
    r"(?:worked?\s+at|currently\s+at|formerly\s+at|joins?\s+from|from)\s+([A-Z][A-Za-z0-9\s&.,]+?)(?:[,.\n]|$)",
)

# Name label
NAME_LABEL_RE = re.compile(r"(?:name|candidate)\s*[:\-]\s*(.+)", re.I)


def ingest(filepath: str) -> Optional[dict]:
    """Parse recruiter notes .txt and return an IntermediateRecord."""
    if not filepath:
        return None

    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except FileNotFoundError:
        logger.warning("Notes ingester: file not found '%s' — skipping.", filepath)
        return None
    except Exception as exc:
        logger.warning("Notes ingester: failed to read '%s': %s — skipping.", filepath, exc)
        return None

    if not text.strip():
        logger.warning("Notes ingester: empty file '%s' — skipping.", filepath)
        return None

    fields = _parse_text(text)

    return {
        "source": "notes",
        "source_priority": SOURCE_PRIORITY,
        "extraction_confidence": EXTRACTION_CONFIDENCE,
        "fields": fields,
        "_raw_text": text[:1000],
    }


def _parse_text(text: str) -> dict:
    fields: dict = {}

    # Name — explicit label first
    nm = NAME_LABEL_RE.search(text)
    if nm:
        name_candidate = nm.group(1).split("\n")[0].strip()
        if name_candidate:
            fields["full_name"] = name_candidate

    # Emails
    emails = list(dict.fromkeys(EMAIL_RE.findall(text)))
    if emails:
        fields["emails"] = emails

    # Phones
    phones = list(dict.fromkeys(PHONE_RE.findall(text)))
    if phones:
        fields["phones"] = [p.strip() for p in phones]

    # LinkedIn / GitHub
    li = LINKEDIN_RE.search(text)
    if li:
        fields["linkedin"] = li.group(0).rstrip("/")
    gh = GITHUB_RE.search(text)
    if gh:
        fields["github"] = gh.group(0).rstrip("/")

    # Years of experience
    ye = YEARS_EXP_RE.search(text)
    if ye:
        try:
            fields["years_experience"] = float(ye.group(1))
        except ValueError:
            pass

    # Skills
    skill_lines = SKILLS_LABEL_RE.findall(text)
    if skill_lines:
        raw_skills = []
        for line in skill_lines:
            parts = re.split(r"[,|•·\n]+", line)
            raw_skills.extend(p.strip() for p in parts if p.strip())
        if raw_skills:
            fields["skills_raw"] = raw_skills

    # Company mentions
    companies = COMPANY_RE.findall(text)
    if companies:
        fields["current_company"] = companies[0].strip()

    # Notes text itself stored as summary clue
    fields["notes_raw"] = text[:500]

    return fields
