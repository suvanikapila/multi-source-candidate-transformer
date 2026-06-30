"""
resume_ingester.py — Resume PDF/DOCX/TXT ingester (unstructured source).

Extracts raw text from:
  - PDF  → via pdfplumber
  - DOCX → via python-docx
  - TXT  → plain read

Then applies regex patterns to extract:
  full_name, emails, phones, linkedin, github, skills, experience, education,
  years_experience, location, headline/summary

Emits an IntermediateRecord tagged with source="resume".
Missing/unreadable file → logged warning, returns None (pipeline continues).
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_PRIORITY = 0.75
EXTRACTION_CONFIDENCE = 0.70  # Unstructured → lower extraction certainty


# ── Regex patterns ────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+?\d[\d\s\-().]{7,}\d)"
)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+/?", re.I)
GITHUB_RE   = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", re.I)

# Skills section header
SKILLS_SECTION_RE = re.compile(
    r"(?:technical\s+)?skills?\s*[:\-]?\s*\n(.*?)(?:\n\s*\n|\Z)",
    re.I | re.S,
)

# Education section
EDUCATION_SECTION_RE = re.compile(
    r"education\s*[:\-]?\s*\n(.*?)(?:\n\s*\n(?=[A-Z])|\Z)",
    re.I | re.S,
)

# Experience section
EXPERIENCE_SECTION_RE = re.compile(
    r"(?:work\s+)?experience\s*[:\-]?\s*\n(.*?)(?:\n\s*\n(?=[A-Z])|\Z)",
    re.I | re.S,
)

# Year ranges for experience calculation
YEAR_RANGE_RE = re.compile(r"(\d{4})\s*[–\-—to]+\s*(\d{4}|present|current)", re.I)

# Degree keywords
DEGREE_RE = re.compile(
    r"\b(B\.?Tech|B\.?E\.?|Bachelor|B\.?S\.?|M\.?Tech|M\.?S\.?|Master|Ph\.?D|MBA|B\.?Sc|M\.?Sc)\b",
    re.I
)


def ingest(filepath: str) -> Optional[dict]:
    """Extract text from resume and parse into an IntermediateRecord."""
    if not filepath:
        return None

    text = _extract_text(filepath)
    if text is None:
        return None
    if not text.strip():
        logger.warning("Resume ingester: empty text extracted from '%s'", filepath)
        return None

    fields = _parse_text(text)
    if not fields.get("full_name") and not fields.get("emails"):
        logger.warning("Resume ingester: could not extract name/email from '%s'", filepath)

    return {
        "source": "resume",
        "source_priority": SOURCE_PRIORITY,
        "extraction_confidence": EXTRACTION_CONFIDENCE,
        "fields": fields,
        "_raw_text": text[:2000],  # keep snippet for debugging
    }


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_text(filepath: str) -> Optional[str]:
    """Return raw text from PDF, DOCX, or TXT. Returns None on failure."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".pdf":
        return _extract_pdf(filepath)
    elif ext in (".docx", ".doc"):
        return _extract_docx(filepath)
    elif ext == ".txt":
        return _extract_txt(filepath)
    else:
        # Try plain text as fallback
        return _extract_txt(filepath)


def _extract_pdf(filepath: str) -> Optional[str]:
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)
    except FileNotFoundError:
        logger.warning("Resume ingester: PDF not found '%s' — skipping.", filepath)
        return None
    except Exception as exc:
        logger.warning("Resume ingester: PDF parse error '%s': %s — skipping.", filepath, exc)
        return None


def _extract_docx(filepath: str) -> Optional[str]:
    try:
        from docx import Document
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)
    except FileNotFoundError:
        logger.warning("Resume ingester: DOCX not found '%s' — skipping.", filepath)
        return None
    except Exception as exc:
        logger.warning("Resume ingester: DOCX parse error '%s': %s — skipping.", filepath, exc)
        return None


def _extract_txt(filepath: str) -> Optional[str]:
    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Resume ingester: file not found '%s' — skipping.", filepath)
        return None
    except Exception as exc:
        logger.warning("Resume ingester: read error '%s': %s — skipping.", filepath, exc)
        return None


# ── Field parsing ─────────────────────────────────────────────────────────────

def _parse_text(text: str) -> dict:
    fields: dict = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Full name — first non-empty line that looks like a name (2–4 words, title-case)
    for line in lines[:5]:
        if _looks_like_name(line):
            fields["full_name"] = line
            break

    # Emails
    emails = list(dict.fromkeys(EMAIL_RE.findall(text)))  # dedupe, preserve order
    if emails:
        fields["emails"] = emails

    # Phones
    phones = list(dict.fromkeys(PHONE_RE.findall(text)))
    if phones:
        fields["phones"] = [p.strip() for p in phones]

    # LinkedIn
    li = LINKEDIN_RE.search(text)
    if li:
        fields["linkedin"] = li.group(0).rstrip("/")

    # GitHub
    gh = GITHUB_RE.search(text)
    if gh:
        fields["github"] = gh.group(0).rstrip("/")

    # Skills section
    skills_match = SKILLS_SECTION_RE.search(text)
    if skills_match:
        skills_text = skills_match.group(1)
        # Remove parenthetical sub-items like AWS (EC2, S3, RDS, Lambda)
        skills_text = re.sub(r"\([^)]*\)", "", skills_text)
        skills = re.split(r"[,|•·\n\t]+", skills_text)
        fields["skills_raw"] = [s.strip() for s in skills if s.strip() and len(s.strip()) > 1]

    # Experience section → raw list of blocks
    exp_match = EXPERIENCE_SECTION_RE.search(text)
    if exp_match:
        fields["experience_raw"] = _parse_experience_blocks(exp_match.group(1))

    # Education section
    edu_match = EDUCATION_SECTION_RE.search(text)
    if edu_match:
        fields["education_raw"] = _parse_education_blocks(edu_match.group(1))

    # Years of experience — sum of year-ranges found in experience section
    all_ranges = YEAR_RANGE_RE.findall(text)
    if all_ranges:
        total_years = _sum_year_ranges(all_ranges)
        if total_years > 0:
            fields["years_experience"] = total_years

    # Headline / summary — look for a short line after the name that isn't contact info
    if lines and "full_name" in fields:
        for line in lines[1:6]:
            if (
                not EMAIL_RE.search(line)
                and not PHONE_RE.search(line)
                and not LINKEDIN_RE.search(line)
                and len(line.split()) >= 3
                and not _looks_like_name(line)
            ):
                fields["headline"] = line
                break

    return fields


def _looks_like_name(line: str) -> bool:
    """Heuristic: 2–4 words, mostly title-case, no digits."""
    words = line.split()
    if not 2 <= len(words) <= 4:
        return False
    if re.search(r"\d", line):
        return False
    if any(w[0].islower() for w in words if w):
        return False
    return True


def _parse_experience_blocks(text: str) -> list:
    """Split experience section text into job blocks."""
    blocks = []
    # Split on blank lines between jobs
    raw_segments = re.split(r"\n\s*\n", text.strip())

    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue

        lines = seg.splitlines()
        # Filter out bullet lines (start with -, •, *, or digit+period)
        non_bullet_lines = [
            l.strip() for l in lines
            if l.strip() and not re.match(r"^[-•*\d]", l.strip())
        ]
        bullet_lines = [
            l.strip() for l in lines
            if l.strip() and re.match(r"^[-•*]", l.strip())
        ]

        if not non_bullet_lines:
            continue

        company = non_bullet_lines[0] if non_bullet_lines else None
        # Skip if "company" is just a year range or date string
        if company and re.match(r"^\d{4}", company):
            continue

        title = non_bullet_lines[1] if len(non_bullet_lines) > 1 else None
        # If title looks like a date line, skip it
        if title and re.match(r"^\d{4}", title):
            title = None

        summary = " ".join(bullet_lines)[:500] if bullet_lines else None

        # Extract dates
        dates = YEAR_RANGE_RE.findall(seg)
        start = dates[0][0] if dates else None
        end_raw = dates[0][1] if dates else None
        end = None if end_raw and end_raw.lower() in ("present", "current") else end_raw

        if not company:
            continue

        blocks.append({
            "company": company,
            "title": title,
            "start": f"{start}-01" if start else None,
            "end": f"{end}-01" if end else None,
            "summary": summary,
        })
    return blocks


def _parse_education_blocks(text: str) -> list:
    """Split education section text into institution blocks."""
    blocks = []
    segments = re.split(r"\n(?=\S)", text.strip())
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        lines = seg.splitlines()
        institution = lines[0].strip() if lines else None
        deg_match = DEGREE_RE.search(seg)
        degree = deg_match.group(0) if deg_match else None
        years = re.findall(r"\b(19|20)\d{2}\b", seg)
        end_year = int(years[-1]) if years else None
        field = None
        # Try to extract field after degree keyword
        if deg_match:
            after = seg[deg_match.end():].strip().lstrip("in").strip()
            field_words = after.split()[:4]
            field = " ".join(field_words) if field_words else None

        blocks.append({
            "institution": institution,
            "degree": degree,
            "field": field,
            "end_year": end_year,
        })
    return blocks


def _sum_year_ranges(ranges: list) -> float:
    """Sum total years from a list of (start_year, end_year_or_present) tuples."""
    import datetime
    current_year = datetime.datetime.now().year
    total = 0.0
    for start_str, end_str in ranges:
        try:
            start = int(start_str)
            end = current_year if end_str.lower() in ("present", "current") else int(end_str)
            if 1980 <= start <= current_year and start <= end:
                total += end - start
        except (ValueError, AttributeError):
            pass
    return round(total, 1)
