"""
test_normalizers.py — Unit tests for all normalizer modules.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.normalize.date_normalizer import normalize_date, normalize_year
from pipeline.normalize.phone_normalizer import normalize_phone, normalize_phones
from pipeline.normalize.location_normalizer import normalize_location, normalize_country
from pipeline.normalize.skill_normalizer import normalize_skill, normalize_skills


# ── Date normalizer ────────────────────────────────────────────────────────────

class TestDateNormalizer:
    def test_iso_format(self):
        assert normalize_date("2020-06") == "2020-06"

    def test_iso_with_day(self):
        assert normalize_date("2020-06-15") == "2020-06"

    def test_month_name_year(self):
        assert normalize_date("Jan 2020") == "2020-01"
        assert normalize_date("January 2020") == "2020-01"

    def test_month_name_abbreviated_dot(self):
        assert normalize_date("Sep. 2021") == "2021-09"

    def test_numeric_slash(self):
        assert normalize_date("06/2020") == "2020-06"

    def test_year_month_slash(self):
        assert normalize_date("2020/06") == "2020-06"

    def test_bare_year(self):
        assert normalize_date("2018") == "2018-01"

    def test_quarter(self):
        assert normalize_date("Q2 2022") == "2022-06"

    def test_none_input(self):
        assert normalize_date(None) is None

    def test_empty_input(self):
        assert normalize_date("") is None

    def test_garbage_input(self):
        assert normalize_date("not-a-date") is None

    def test_normalize_year(self):
        assert normalize_year("B.Tech 2018") == 2018
        assert normalize_year("graduated in 2022") == 2022
        assert normalize_year("no year here") is None


# ── Phone normalizer ───────────────────────────────────────────────────────────

class TestPhoneNormalizer:
    def test_us_number(self):
        result = normalize_phone("+1 415 555 2671")
        assert result == "+14155552671"

    def test_indian_number(self):
        result = normalize_phone("+91 9876543210")
        assert result == "+919876543210"

    def test_indian_with_dashes(self):
        result = normalize_phone("+91-9876543210")
        assert result == "+919876543210"

    def test_none_input(self):
        assert normalize_phone(None) is None

    def test_empty_input(self):
        assert normalize_phone("") is None

    def test_garbage_input(self):
        # Should return None, never crash
        result = normalize_phone("not-a-phone")
        assert result is None

    def test_normalize_phones_dedup(self):
        phones = ["+91 9876543210", "+91-9876543210", "+1 415 555 2671"]
        result = normalize_phones(phones)
        assert len(result) == 2  # deduped
        assert "+919876543210" in result
        assert "+14155552671" in result


# ── Location normalizer ────────────────────────────────────────────────────────

class TestLocationNormalizer:
    def test_city_country(self):
        loc = normalize_location("Bengaluru, India")
        assert loc["city"] == "Bengaluru"
        assert loc["country"] == "IN"

    def test_city_state_country(self):
        loc = normalize_location("San Francisco, CA, USA")
        assert loc["city"] == "San Francisco"
        assert loc["country"] == "US"

    def test_country_only(self):
        loc = normalize_location("United States")
        assert loc["country"] == "US"

    def test_iso_code(self):
        assert normalize_country("IN") == "IN"
        assert normalize_country("US") == "US"
        assert normalize_country("GB") == "GB"

    def test_alias(self):
        assert normalize_country("usa") == "US"
        assert normalize_country("uk") == "GB"
        assert normalize_country("UAE") == "AE"

    def test_none_input(self):
        loc = normalize_location(None)
        assert loc == {"city": None, "region": None, "country": None}

    def test_empty_input(self):
        loc = normalize_location("")
        assert loc == {"city": None, "region": None, "country": None}

    def test_garbage_country(self):
        # Should not crash, country stays None or unknown
        loc = normalize_location("XYZ123")
        assert isinstance(loc, dict)


# ── Skill normalizer ───────────────────────────────────────────────────────────

class TestSkillNormalizer:
    def test_exact_match(self):
        canonical, confidence = normalize_skill("Python")
        assert canonical == "Python"
        assert confidence == 1.0

    def test_case_insensitive_exact(self):
        canonical, confidence = normalize_skill("python")
        assert canonical == "Python"
        assert confidence == 1.0

    def test_fuzzy_match(self):
        canonical, confidence = normalize_skill("machine learning")
        assert canonical == "Machine Learning"
        assert confidence > 0.7

    def test_no_match_passthrough(self):
        canonical, confidence = normalize_skill("ExoticUnknownSkill123")
        assert canonical == "ExoticUnknownSkill123"
        assert confidence == 0.5

    def test_empty_skill(self):
        canonical, confidence = normalize_skill("")
        assert confidence == 0.0

    def test_normalize_skills_dedup(self):
        raw = ["python", "Python", "PYTHON", "Machine Learning", "ml"]
        result = normalize_skills(raw)
        names = [s["name"] for s in result]
        # Python should appear only once
        assert names.count("Python") == 1

    def test_normalize_skills_empty_list(self):
        result = normalize_skills([])
        assert result == []

    def test_normalize_skills_none(self):
        result = normalize_skills(None)
        assert result == []
