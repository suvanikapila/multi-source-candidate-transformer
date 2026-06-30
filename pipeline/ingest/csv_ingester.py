"""
csv_ingester.py — Recruiter CSV export ingester.

Reads a structured CSV (recruiter export) with columns like:
  name, email, phone, current_company, title, location, linkedin, github,
  skills, years_experience, education

Emits an IntermediateRecord dict tagged with source="csv".
Missing/unreadable file → logged warning, returns None (pipeline continues).
"""

import csv
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Map CSV column names → canonical field names
CSV_FIELD_MAP = {
    "name":             "full_name",
    "full_name":        "full_name",
    "email":            "emails",
    "emails":           "emails",
    "phone":            "phones",
    "phones":           "phones",
    "current_company":  "current_company",
    "company":          "current_company",
    "title":            "headline",
    "job_title":        "headline",
    "headline":         "headline",
    "location":         "location_raw",
    "city":             "city",
    "country":          "country",
    "linkedin":         "linkedin",
    "linkedin_url":     "linkedin",
    "github":           "github",
    "github_url":       "github",
    "portfolio":        "portfolio",
    "skills":           "skills_raw",
    "years_experience": "years_experience",
    "years_exp":        "years_experience",
    "education":        "education_raw",
    "summary":          "summary",
    "notes":            "notes_raw",
}

SOURCE_PRIORITY = 0.9   # CSV is highest-priority source
EXTRACTION_CONFIDENCE = 0.95  # Structured → near-certain extraction


def ingest(filepath: str) -> Optional[dict]:
    """
    Parse a recruiter CSV and return an IntermediateRecord.

    Returns None if the file is missing/unreadable (logs a warning).
    Returns a list with one record per CSV row that has an email or name.
    For simplicity (single candidate pipeline), returns the FIRST valid row.
    """
    if not filepath:
        return None

    try:
        rows = []
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rec = _parse_row(row)
                if rec:
                    rows.append(rec)

        if not rows:
            logger.warning("CSV ingester: no valid rows found in '%s'", filepath)
            return None

        if len(rows) > 1:
            logger.info("CSV ingester: %d rows found, using first valid row.", len(rows))

        return rows[0]

    except FileNotFoundError:
        logger.warning("CSV ingester: file not found '%s' — skipping.", filepath)
        return None
    except Exception as exc:
        logger.warning("CSV ingester: failed to parse '%s': %s — skipping.", filepath, exc)
        return None


def ingest_all(filepath: str) -> list:
    """Return ALL rows as IntermediateRecords (for batch/multi-candidate use)."""
    if not filepath:
        return []
    try:
        rows = []
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rec = _parse_row(row)
                if rec:
                    rows.append(rec)
        return rows
    except FileNotFoundError:
        logger.warning("CSV ingester: file not found '%s' — skipping.", filepath)
        return []
    except Exception as exc:
        logger.warning("CSV ingester: failed to parse '%s': %s — skipping.", filepath, exc)
        return []


def _parse_row(row: dict) -> Optional[dict]:
    """Convert one CSV row dict into an IntermediateRecord."""
    fields = {}

    for col, value in row.items():
        col_clean = col.strip().lower().replace(" ", "_")
        canonical = CSV_FIELD_MAP.get(col_clean)
        if canonical and value and value.strip():
            raw_val = value.strip()

            # List fields
            if canonical in ("emails",):
                fields[canonical] = [e.strip() for e in raw_val.split(";") if e.strip()]
            elif canonical in ("phones",):
                fields[canonical] = [p.strip() for p in raw_val.split(";") if p.strip()]
            elif canonical == "skills_raw":
                fields[canonical] = [s.strip() for s in raw_val.replace(";", ",").split(",") if s.strip()]
            elif canonical == "years_experience":
                try:
                    fields[canonical] = float(raw_val)
                except ValueError:
                    fields[canonical] = None
            else:
                fields[canonical] = raw_val

    # Must have at minimum a name or an email
    if not fields.get("full_name") and not fields.get("emails"):
        return None

    return {
        "source": "csv",
        "source_priority": SOURCE_PRIORITY,
        "extraction_confidence": EXTRACTION_CONFIDENCE,
        "fields": fields,
    }
