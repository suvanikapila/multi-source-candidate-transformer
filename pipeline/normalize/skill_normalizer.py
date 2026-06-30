"""
skill_normalizer.py — Normalize skill names to canonical form.

Strategy:
  1. Exact match against the skills dictionary (case-insensitive).
  2. Fuzzy match via rapidfuzz (token_sort_ratio ≥ threshold).
  3. If no match found → keep original (pass-through) with lower confidence.

Skills dictionary loaded once from skills_dictionary.txt.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 80  # minimum score (0–100) to accept a fuzzy match

try:
    from rapidfuzz import fuzz, process as rfprocess
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    logger.warning("skill_normalizer: 'rapidfuzz' not installed. Fuzzy matching disabled.")

_SKILLS_DICT: Optional[list] = None  # lazy-loaded
_SKILLS_LOWER: Optional[dict] = None  # lowercase → canonical


def _load_skills_dict() -> tuple:
    """Load skills dictionary from file. Returns (list_of_canonical, lower_map)."""
    global _SKILLS_DICT, _SKILLS_LOWER
    if _SKILLS_DICT is not None:
        return _SKILLS_DICT, _SKILLS_LOWER

    # Search for skills_dictionary.txt relative to this file → project root
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dict_path = os.path.join(base, "skills_dictionary.txt")

    if not os.path.exists(dict_path):
        logger.warning("skill_normalizer: skills_dictionary.txt not found at '%s'", dict_path)
        _SKILLS_DICT = []
        _SKILLS_LOWER = {}
        return _SKILLS_DICT, _SKILLS_LOWER

    with open(dict_path, encoding="utf-8") as f:
        skills = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    _SKILLS_DICT = skills
    _SKILLS_LOWER = {s.lower(): s for s in skills}
    return _SKILLS_DICT, _SKILLS_LOWER


def normalize_skill(raw: str) -> tuple:
    """
    Normalize a single raw skill name.

    Returns:
        (canonical_name: str, match_confidence: float)
        match_confidence is 1.0 for exact, 0.7–0.99 for fuzzy, 0.5 for no match.
    """
    if not raw or not raw.strip():
        return (raw, 0.0)

    raw = raw.strip()
    skills_list, skills_lower = _load_skills_dict()

    # 1. Exact match (case-insensitive)
    lower_raw = raw.lower()
    if lower_raw in skills_lower:
        return (skills_lower[lower_raw], 1.0)

    # 2. Fuzzy match
    if _HAS_RAPIDFUZZ and skills_list:
        result = rfprocess.extractOne(
            raw,
            skills_list,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=FUZZY_THRESHOLD,
        )
        if result:
            canonical, score, _ = result
            confidence = round(0.5 + (score - FUZZY_THRESHOLD) / (100 - FUZZY_THRESHOLD) * 0.49, 4)
            return (canonical, confidence)

    # 3. No match → pass-through with low confidence
    return (raw, 0.5)


def normalize_skills(raw_list: list) -> list:
    """
    Normalize a list of raw skill strings.

    Returns list of dicts: [{"name": str, "confidence": float, "sources": []}]
    Deduplicates by canonical name (keeps highest confidence).
    """
    seen: dict = {}  # canonical_name → entry

    for raw in (raw_list or []):
        if not raw:
            continue
        canonical, confidence = normalize_skill(str(raw))
        key = canonical.lower()
        if key not in seen or confidence > seen[key]["confidence"]:
            seen[key] = {
                "name": canonical,
                "confidence": confidence,
                "sources": [],
            }

    return list(seen.values())
