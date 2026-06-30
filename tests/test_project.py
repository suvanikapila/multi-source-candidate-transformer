"""
test_project.py — Unit tests for the stateless projection layer.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.project import project, _resolve_path


CANONICAL = {
    "candidate_id": "cand_abc123",
    "full_name": "Alice Smith",
    "emails": ["alice@example.com", "alice.smith@work.com"],
    "phones": ["+14155552671"],
    "location": {"city": "San Francisco", "region": "CA", "country": "US"},
    "links": {"linkedin": "https://linkedin.com/in/alice", "github": None, "portfolio": None, "other": []},
    "headline": "Senior Software Engineer",
    "years_experience": 7.0,
    "skills": [
        {"name": "Python", "confidence": 1.0, "sources": ["csv", "resume"]},
        {"name": "Docker", "confidence": 0.95, "sources": ["csv"]},
    ],
    "experience": [
        {"company": "Acme Corp", "title": "SWE", "start": "2020-01", "end": None, "summary": "Built stuff."}
    ],
    "education": [
        {"institution": "MIT", "degree": "B.S.", "field": "Computer Science", "end_year": 2016}
    ],
    "provenance": [{"field": "full_name", "source": "csv", "method": "priority_score=0.855"}],
    "overall_confidence": 0.87,
}


class TestResolvePath:
    def test_simple_field(self):
        assert _resolve_path(CANONICAL, "full_name") == "Alice Smith"

    def test_array_index(self):
        assert _resolve_path(CANONICAL, "emails[0]") == "alice@example.com"
        assert _resolve_path(CANONICAL, "emails[1]") == "alice.smith@work.com"

    def test_array_expansion(self):
        result = _resolve_path(CANONICAL, "skills[].name")
        assert result == ["Python", "Docker"]

    def test_nested_field(self):
        assert _resolve_path(CANONICAL, "location.country") == "US"
        assert _resolve_path(CANONICAL, "location.city") == "San Francisco"

    def test_missing_index(self):
        # emails[5] does not exist
        assert _resolve_path(CANONICAL, "emails[5]") is None

    def test_missing_field(self):
        assert _resolve_path(CANONICAL, "nonexistent_field") is None

    def test_nested_missing(self):
        assert _resolve_path(CANONICAL, "location.nonexistent") is None


class TestProject:
    def test_no_config_returns_canonical(self):
        result = project(CANONICAL, None)
        assert result["candidate_id"] == CANONICAL["candidate_id"]
        assert result["full_name"] == CANONICAL["full_name"]

    def test_field_subset(self):
        config = {
            "fields": [
                {"path": "full_name", "type": "string"},
                {"path": "primary_email", "from": "emails[0]", "type": "string"},
            ],
            "on_missing": "null",
        }
        result = project(CANONICAL, config)
        assert set(result.keys()) == {"full_name", "primary_email"}
        assert result["full_name"] == "Alice Smith"
        assert result["primary_email"] == "alice@example.com"

    def test_path_remap(self):
        config = {
            "fields": [
                {"path": "country", "from": "location.country", "type": "string"},
            ],
            "on_missing": "null",
        }
        result = project(CANONICAL, config)
        assert result["country"] == "US"

    def test_array_expansion_remap(self):
        config = {
            "fields": [
                {"path": "skill_names", "from": "skills[].name", "type": "string[]"},
            ],
            "on_missing": "null",
        }
        result = project(CANONICAL, config)
        assert "Python" in result["skill_names"]
        assert "Docker" in result["skill_names"]

    def test_on_missing_null(self):
        config = {
            "fields": [
                {"path": "portfolio", "from": "links.portfolio", "type": "string"},
            ],
            "on_missing": "null",
        }
        result = project(CANONICAL, config)
        assert "portfolio" in result
        assert result["portfolio"] is None

    def test_on_missing_omit(self):
        config = {
            "fields": [
                {"path": "portfolio", "from": "links.portfolio", "type": "string"},
            ],
            "on_missing": "omit",
        }
        result = project(CANONICAL, config)
        assert "portfolio" not in result

    def test_on_missing_error_required(self):
        config = {
            "fields": [
                {"path": "portfolio", "from": "links.portfolio", "type": "string", "required": True},
            ],
            "on_missing": "error",
        }
        with pytest.raises(ValueError, match="Required field 'portfolio' is missing"):
            project(CANONICAL, config)

    def test_include_confidence(self):
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "include_confidence": True,
            "on_missing": "null",
        }
        result = project(CANONICAL, config)
        assert "overall_confidence" in result
        assert "provenance" in result

    def test_no_confidence_by_default(self):
        config = {
            "fields": [{"path": "full_name", "type": "string"}],
            "on_missing": "null",
        }
        result = project(CANONICAL, config)
        assert "overall_confidence" not in result
