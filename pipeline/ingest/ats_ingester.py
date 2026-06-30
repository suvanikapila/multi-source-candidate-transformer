"""
ats_ingester.py — ATS JSON blob ingester.

ATS JSON has its OWN field names that do NOT match our canonical schema.
This module maps ATS-specific keys → canonical fields.

Emits an IntermediateRecord tagged with source="ats".
Missing/unreadable file → logged warning, returns None (pipeline continues).
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_PRIORITY = 0.85
EXTRACTION_CONFIDENCE = 0.90

# ATS field name → canonical field name mapping
# ATS systems use many different naming conventions; this covers common ones.
ATS_FIELD_MAP = {
    # Name variants
    "applicant_name":       "full_name",
    "candidate_name":       "full_name",
    "firstName":            "_first_name",
    "lastName":             "_last_name",
    "first_name":           "_first_name",
    "last_name":            "_last_name",
    "name":                 "full_name",

    # Email
    "email_address":        "emails",
    "applicant_email":      "emails",
    "contact_email":        "emails",
    "email":                "emails",

    # Phone
    "mobile":               "phones",
    "phone_number":         "phones",
    "contact_phone":        "phones",
    "phone":                "phones",

    # Location
    "current_location":     "location_raw",
    "address":              "location_raw",
    "city":                 "city",
    "state":                "region",
    "country":              "country",
    "location":             "location_raw",

    # Professional
    "current_title":        "headline",
    "job_title":            "headline",
    "position":             "headline",
    "current_employer":     "current_company",
    "employer":             "current_company",
    "company":              "current_company",

    # Links
    "linkedin_profile":     "linkedin",
    "linkedin_url":         "linkedin",
    "github_profile":       "github",
    "github_url":           "github",
    "portfolio_url":        "portfolio",
    "website":              "portfolio",

    # Skills / experience
    "skill_set":            "skills_raw",
    "skills":               "skills_raw",
    "years_of_experience":  "years_experience",
    "experience_years":     "years_experience",

    # Experience history
    "work_history":         "experience_raw",
    "employment_history":   "experience_raw",
    "experience":           "experience_raw",

    # Education
    "education_history":    "education_raw",
    "education":            "education_raw",
    "academic":             "education_raw",

    # Misc
    "summary":              "summary",
    "bio":                  "summary",
    "about":                "summary",
    "notes":                "notes_raw",
}


def ingest(filepath: str) -> Optional[dict]:
    """Parse an ATS JSON blob and return an IntermediateRecord."""
    if not filepath:
        return None

    try:
        with open(filepath, encoding="utf-8") as f:
            blob = json.load(f)
    except FileNotFoundError:
        logger.warning("ATS ingester: file not found '%s' — skipping.", filepath)
        return None
    except json.JSONDecodeError as exc:
        logger.warning("ATS ingester: invalid JSON in '%s': %s — skipping.", filepath, exc)
        return None
    except Exception as exc:
        logger.warning("ATS ingester: failed to read '%s': %s — skipping.", filepath, exc)
        return None

    # ATS blob may wrap records in a key like "candidate", "applicant", "data"
    if isinstance(blob, dict):
        for wrapper in ("candidate", "applicant", "data", "record", "profile"):
            if wrapper in blob and isinstance(blob[wrapper], dict):
                blob = blob[wrapper]
                break
    else:
        logger.warning("ATS ingester: unexpected JSON structure in '%s' — skipping.", filepath)
        return None

    return _parse_blob(blob)


def _parse_blob(blob: dict) -> Optional[dict]:
    """Flatten an ATS blob dict into an IntermediateRecord."""
    fields: dict = {}
    first_name = None
    last_name = None

    for key, value in blob.items():
        canonical = ATS_FIELD_MAP.get(key)
        if not canonical:
            # Try lowercase/underscore variant
            canonical = ATS_FIELD_MAP.get(key.lower()) or ATS_FIELD_MAP.get(
                key.lower().replace(" ", "_")
            )
        if not canonical or value is None:
            continue

        # Handle list inputs
        if canonical == "emails":
            if isinstance(value, list):
                fields["emails"] = [str(v).strip() for v in value if v]
            else:
                fields["emails"] = [str(value).strip()]

        elif canonical == "phones":
            if isinstance(value, list):
                fields["phones"] = [str(v).strip() for v in value if v]
            else:
                fields["phones"] = [str(value).strip()]

        elif canonical == "skills_raw":
            if isinstance(value, list):
                fields["skills_raw"] = [
                    (s.get("name") or s.get("skill") or str(s)).strip()
                    if isinstance(s, dict) else str(s).strip()
                    for s in value if s
                ]
            else:
                fields["skills_raw"] = [s.strip() for s in str(value).replace(";", ",").split(",") if s.strip()]

        elif canonical == "experience_raw":
            if isinstance(value, list):
                fields["experience_raw"] = value  # raw list, normalizer handles it
            else:
                fields["experience_raw"] = []

        elif canonical == "education_raw":
            if isinstance(value, list):
                fields["education_raw"] = value
            else:
                fields["education_raw"] = []

        elif canonical == "years_experience":
            try:
                fields["years_experience"] = float(value)
            except (ValueError, TypeError):
                pass

        elif canonical == "_first_name":
            first_name = str(value).strip()

        elif canonical == "_last_name":
            last_name = str(value).strip()

        else:
            fields[canonical] = str(value).strip() if value else None

    # Combine first+last into full_name if full_name not already set
    if not fields.get("full_name") and (first_name or last_name):
        parts = [p for p in [first_name, last_name] if p]
        fields["full_name"] = " ".join(parts)

    if not fields.get("full_name") and not fields.get("emails"):
        return None

    return {
        "source": "ats",
        "source_priority": SOURCE_PRIORITY,
        "extraction_confidence": EXTRACTION_CONFIDENCE,
        "fields": fields,
    }
