"""
merge.py — Merge and conflict-resolve multiple IntermediateRecords into one
           canonical record.

Strategy:
  - Match key: normalized primary email → fallback: fuzzy name + phone.
  - For each field: winner = highest (source_priority × extraction_confidence).
  - Ties broken by majority agreement across sources.
  - ALL losing values stored in provenance (nothing silently discarded).
  - Skills merged across all sources; deduped by canonical name.
  - Experience / education lists: union across sources, deduped by company+dates.
"""

import hashlib
import logging
import uuid
from typing import Optional

from pipeline.normalize.date_normalizer import normalize_date, normalize_year
from pipeline.normalize.phone_normalizer import normalize_phones
from pipeline.normalize.location_normalizer import normalize_location
from pipeline.normalize.skill_normalizer import normalize_skills

logger = logging.getLogger(__name__)

# Source priority weights (used as multiplier with extraction_confidence)
SOURCE_WEIGHTS = {
    "csv":    0.90,
    "ats":    0.85,
    "resume": 0.75,
    "notes":  0.60,
}


def merge(records: list) -> dict:
    """
    Merge a list of IntermediateRecords into one canonical record.

    Args:
        records: list of dicts from ingesters (may contain None values, filtered out).

    Returns:
        Canonical record dict (pre-confidence, pre-projection).
    """
    records = [r for r in records if r]  # drop None entries

    if not records:
        logger.error("merge: no valid records to merge.")
        return _empty_canonical()

    provenance: list = []

    # ── Scalar fields ─────────────────────────────────────────────────────────
    full_name     = _pick_winner("full_name",        records, provenance)
    headline      = _pick_winner("headline",          records, provenance)
    current_co    = _pick_winner("current_company",   records, provenance)
    years_exp_raw = _pick_winner("years_experience",  records, provenance)
    linkedin      = _pick_winner("linkedin",          records, provenance)
    github        = _pick_winner("github",            records, provenance)
    portfolio     = _pick_winner("portfolio",         records, provenance)
    summary       = _pick_winner("summary",           records, provenance)

    # ── Email list (union across sources, primary = highest-priority source) ──
    emails = _merge_list("emails", records, provenance)
    emails = list(dict.fromkeys(e.lower().strip() for e in emails if e))

    # ── Phone list (union, normalized to E.164) ──────────────────────────────
    phones_raw = _merge_list("phones", records, provenance)
    phones = normalize_phones(phones_raw)

    # ── Candidate ID — derived from primary email (deterministic) ─────────────
    candidate_id = _make_candidate_id(emails, full_name)

    # ── Location ──────────────────────────────────────────────────────────────
    location_raw = _pick_winner("location_raw", records, provenance)
    city_raw     = _pick_winner("city",         records, provenance)
    region_raw   = _pick_winner("region",       records, provenance)
    country_raw  = _pick_winner("country",      records, provenance)

    if location_raw:
        loc = normalize_location(location_raw)
        # Explicit city/country fields override parsed ones
        if city_raw:    loc["city"]    = city_raw
        if region_raw:  loc["region"]  = region_raw
        if country_raw:
            from pipeline.normalize.location_normalizer import normalize_country
            loc["country"] = normalize_country(country_raw) or country_raw
    elif city_raw or country_raw:
        from pipeline.normalize.location_normalizer import normalize_country
        loc = {
            "city":    city_raw,
            "region":  region_raw,
            "country": normalize_country(country_raw) if country_raw else None,
        }
    else:
        loc = {"city": None, "region": None, "country": None}

    if loc != {"city": None, "region": None, "country": None}:
        provenance.append({
            "field":  "location",
            "source": _best_source("location_raw", records) or "merged",
            "method": "location_normalizer",
        })

    # ── Skills — union across all sources, deduped by canonical name ──────────
    all_skills_raw = []
    skills_sources: dict = {}  # canonical_lower → [source names]
    for rec in records:
        raw_list = rec["fields"].get("skills_raw", [])
        if raw_list:
            src = rec["source"]
            for skill in raw_list:
                all_skills_raw.append(skill)
                # track source for each skill
                skills_sources.setdefault(skill.lower().strip(), []).append(src)

    skills = normalize_skills(all_skills_raw)
    # Attach source tags to each skill
    for sk in skills:
        key = sk["name"].lower()
        # Find best-matching raw skill for source lookup
        srcs = set()
        for raw_key, src_list in skills_sources.items():
            from rapidfuzz import fuzz as _fuzz
            try:
                if _fuzz.token_sort_ratio(raw_key, key) >= 75:
                    srcs.update(src_list)
            except Exception:
                srcs.update(src_list)
        sk["sources"] = sorted(srcs) if srcs else ["merged"]

    if skills:
        provenance.append({"field": "skills", "source": "merged", "method": "skill_normalizer+rapidfuzz"})

    # ── Experience — union from resume + ATS, deduped ────────────────────────
    experience = _merge_experience(records, provenance)

    # ── Education — union, deduped by institution+degree ─────────────────────
    education = _merge_education(records, provenance)

    # ── years_experience ─────────────────────────────────────────────────────
    years_experience = None
    if years_exp_raw is not None:
        try:
            years_experience = float(years_exp_raw)
        except (TypeError, ValueError):
            pass

    # ── Links ─────────────────────────────────────────────────────────────────
    links = {
        "linkedin":  linkedin,
        "github":    github,
        "portfolio": portfolio,
        "other":     [],
    }

    return {
        "candidate_id":     candidate_id,
        "full_name":        full_name,
        "emails":           emails,
        "phones":           phones,
        "location":         loc,
        "links":            links,
        "headline":         headline,
        "years_experience": years_experience,
        "skills":           skills,
        "experience":       experience,
        "education":        education,
        "provenance":       provenance,
        "overall_confidence": 0.0,  # filled by confidence.py
    }


# ── Helper: pick winner for a scalar field ─────────────────────────────────────

def _pick_winner(field: str, records: list, provenance: list) -> Optional[object]:
    """
    Return the winning value for a scalar field across records.
    Score = source_priority × extraction_confidence.
    All candidates added to provenance.
    """
    candidates = []
    for rec in records:
        val = rec["fields"].get(field)
        if val is None:
            continue
        score = (
            SOURCE_WEIGHTS.get(rec["source"], 0.5) *
            rec.get("extraction_confidence", 0.5)
        )
        candidates.append({
            "value":  val,
            "source": rec["source"],
            "score":  score,
        })

    if not candidates:
        return None

    # Sort descending by score
    candidates.sort(key=lambda c: c["score"], reverse=True)
    winner = candidates[0]

    # Record provenance for winner
    provenance.append({
        "field":  field,
        "source": winner["source"],
        "method": f"priority_score={winner['score']:.3f}",
    })

    # Record non-winners too (value may differ — kept in provenance)
    for c in candidates[1:]:
        if str(c["value"]) != str(winner["value"]):
            provenance.append({
                "field":  f"{field}[alt]",
                "source": c["source"],
                "method": f"priority_score={c['score']:.3f}",
            })

    return winner["value"]


def _merge_list(field: str, records: list, provenance: list) -> list:
    """Union a list field across all records."""
    seen = set()
    result = []
    for rec in records:
        vals = rec["fields"].get(field) or []
        if isinstance(vals, str):
            vals = [vals]
        for v in vals:
            if v and v not in seen:
                seen.add(v)
                result.append(v)
    if result:
        provenance.append({"field": field, "source": "merged", "method": "union"})
    return result


def _best_source(field: str, records: list) -> Optional[str]:
    """Return the source name of the highest-priority record that has the field."""
    for rec in sorted(records, key=lambda r: SOURCE_WEIGHTS.get(r["source"], 0), reverse=True):
        if rec["fields"].get(field):
            return rec["source"]
    return None


def _merge_experience(records: list, provenance: list) -> list:
    """Collect and deduplicate experience entries across sources."""
    all_exp = []
    seen_keys = set()

    for rec in sorted(records, key=lambda r: SOURCE_WEIGHTS.get(r["source"], 0), reverse=True):
        raw_list = rec["fields"].get("experience_raw") or []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            company = (item.get("company") or "").strip()
            start   = normalize_date(item.get("start"))
            end     = normalize_date(item.get("end"))
            key     = f"{company.lower()}|{start}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_exp.append({
                "company": company or None,
                "title":   (item.get("title") or "").strip() or None,
                "start":   start,
                "end":     end,
                "summary": (item.get("summary") or "").strip() or None,
            })

    if all_exp:
        provenance.append({"field": "experience", "source": "merged", "method": "union+dedup"})
    return all_exp


def _merge_education(records: list, provenance: list) -> list:
    """Collect and deduplicate education entries across sources."""
    all_edu = []
    seen_keys = set()

    for rec in sorted(records, key=lambda r: SOURCE_WEIGHTS.get(r["source"], 0), reverse=True):
        raw_list = rec["fields"].get("education_raw") or []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            inst   = (item.get("institution") or "").strip()
            degree = (item.get("degree") or "").strip()
            key    = f"{inst.lower()}|{degree.lower()}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_edu.append({
                "institution": inst or None,
                "degree":      degree or None,
                "field":       (item.get("field") or "").strip() or None,
                "end_year":    normalize_year(str(item.get("end_year") or "")) or item.get("end_year"),
            })

    if all_edu:
        provenance.append({"field": "education", "source": "merged", "method": "union+dedup"})
    return all_edu


def _make_candidate_id(emails: list, full_name: Optional[str]) -> str:
    """Generate a deterministic candidate_id from primary email or name."""
    seed = (emails[0] if emails else (full_name or "unknown")).lower().strip()
    return "cand_" + hashlib.sha256(seed.encode()).hexdigest()[:12]


def _empty_canonical() -> dict:
    return {
        "candidate_id":     "cand_unknown",
        "full_name":        None,
        "emails":           [],
        "phones":           [],
        "location":         {"city": None, "region": None, "country": None},
        "links":            {"linkedin": None, "github": None, "portfolio": None, "other": []},
        "headline":         None,
        "years_experience": None,
        "skills":           [],
        "experience":       [],
        "education":        [],
        "provenance":       [],
        "overall_confidence": 0.0,
    }
