"""
confidence.py — Compute per-field and overall confidence scores.

Per-field confidence:
  score = source_reliability_weight × extraction_certainty × agreement_bonus

  - source_reliability_weight: from SOURCE_WEIGHTS (csv=0.9, ats=0.85, ...)
  - extraction_certainty: set by each ingester (structured=high, unstructured=lower)
  - agreement_bonus: +0.05 per additional source that agrees on this field value

overall_confidence:
  Weighted mean of per-field scores for populated required fields.
  Fewer sources → lower overall confidence.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_WEIGHTS = {
    "csv":    0.90,
    "ats":    0.85,
    "resume": 0.75,
    "notes":  0.60,
}

# Fields that matter most for overall_confidence (higher weight)
FIELD_IMPORTANCE = {
    "full_name":        1.0,
    "emails":           1.0,
    "phones":           0.8,
    "headline":         0.7,
    "location":         0.7,
    "years_experience": 0.8,
    "skills":           0.9,
    "experience":       0.9,
    "education":        0.8,
    "links":            0.5,
}


def compute_confidence(canonical: dict, records: list) -> dict:
    """
    Annotate a canonical record with overall_confidence.

    Args:
        canonical:  The merged canonical record (will be mutated with confidence).
        records:    The list of IntermediateRecords used to build it.

    Returns:
        The same canonical record with overall_confidence filled in.
    """
    records = [r for r in (records or []) if r]
    n_sources = len(records)

    field_scores: dict = {}

    for field, importance in FIELD_IMPORTANCE.items():
        val = canonical.get(field)
        if val is None or val == [] or val == {} or val == {"city": None, "region": None, "country": None}:
            field_scores[field] = 0.0
            continue

        # Find best contributing source for this field
        best_score = 0.0
        agreement_count = 0

        for rec in records:
            # Check if this record contributed this field
            contributed = _record_contributed(field, rec)
            if not contributed:
                continue
            score = (
                SOURCE_WEIGHTS.get(rec["source"], 0.5) *
                rec.get("extraction_confidence", 0.5)
            )
            if score > best_score:
                best_score = score
            agreement_count += 1

        if best_score == 0.0 and val:
            # Field exists in canonical but we can't trace it to a specific record
            # (e.g. computed fields like candidate_id) → moderate confidence
            best_score = 0.5

        # Agreement bonus: +0.05 per additional source beyond first
        bonus = min(0.15, 0.05 * max(0, agreement_count - 1))
        field_scores[field] = min(1.0, round(best_score + bonus, 4))

    # Overall = weighted mean of populated fields
    total_weight = 0.0
    weighted_sum = 0.0
    for field, score in field_scores.items():
        importance = FIELD_IMPORTANCE.get(field, 0.5)
        weighted_sum += score * importance
        total_weight += importance

    if total_weight > 0:
        raw_overall = weighted_sum / total_weight
    else:
        raw_overall = 0.0

    # Penalty if very few sources
    if n_sources == 1:
        raw_overall *= 0.9
    elif n_sources == 0:
        raw_overall = 0.0

    canonical["overall_confidence"] = round(min(1.0, raw_overall), 4)

    # Also update skill confidences to reflect source agreement
    for skill in canonical.get("skills", []):
        n_skill_sources = len(skill.get("sources", []))
        src_bonus = min(0.1, 0.05 * max(0, n_skill_sources - 1))
        skill["confidence"] = round(min(1.0, skill["confidence"] + src_bonus), 4)

    return canonical


def _record_contributed(field: str, rec: dict) -> bool:
    """Check if a record contributed a value for the given canonical field."""
    fields = rec.get("fields", {})
    field_map = {
        "full_name":        ["full_name"],
        "emails":           ["emails"],
        "phones":           ["phones"],
        "headline":         ["headline"],
        "location":         ["location_raw", "city", "country"],
        "years_experience": ["years_experience"],
        "skills":           ["skills_raw"],
        "experience":       ["experience_raw"],
        "education":        ["education_raw"],
        "links":            ["linkedin", "github", "portfolio"],
    }
    keys = field_map.get(field, [field])
    return any(fields.get(k) for k in keys)
