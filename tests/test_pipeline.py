"""
test_pipeline.py — End-to-end integration tests for the full pipeline.
"""

import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.pipeline import run

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


class TestPipelineEndToEnd:
    def test_csv_and_ats_sources(self):
        """Pipeline runs on CSV + ATS (two structured sources)."""
        result = run(
            csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
            ats=os.path.join(DATA_DIR, "sample_ats.json"),
        )
        assert result.get("full_name") == "Priya Sharma"
        assert "priya.sharma@gmail.com" in result.get("emails", [])
        assert isinstance(result.get("skills"), list)
        assert result.get("overall_confidence", 0) > 0.0

    def test_all_four_sources(self):
        """Pipeline runs on all 4 sources (both structured + unstructured)."""
        result = run(
            csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
            ats=os.path.join(DATA_DIR, "sample_ats.json"),
            resume=os.path.join(DATA_DIR, "sample_resume.txt"),
            notes=os.path.join(DATA_DIR, "sample_notes.txt"),
        )
        assert result.get("full_name") is not None
        assert len(result.get("emails", [])) >= 1
        assert result.get("overall_confidence", 0) > 0.0

    def test_missing_csv_graceful(self):
        """Missing CSV should not crash — pipeline continues on remaining sources."""
        result = run(
            csv="nonexistent_file.csv",
            ats=os.path.join(DATA_DIR, "sample_ats.json"),
        )
        # Should still produce a record from ATS
        assert result.get("full_name") is not None

    def test_missing_all_sources(self):
        """All missing → returns error dict, no crash."""
        result = run(
            csv="bad.csv",
            ats="bad.json",
        )
        assert "error" in result or result.get("candidate_id") is None or result.get("full_name") is None

    def test_custom_config_projection(self):
        """Custom config produces only requested fields."""
        config = {
            "fields": [
                {"path": "full_name", "type": "string", "required": True},
                {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
                {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
                {"path": "skill_names", "from": "skills[].name", "type": "string[]"},
            ],
            "include_confidence": True,
            "on_missing": "null",
        }
        result = run(
            csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
            ats=os.path.join(DATA_DIR, "sample_ats.json"),
            config=config,
        )
        # Only projected fields + confidence should be present
        assert "full_name" in result
        assert "primary_email" in result
        assert "overall_confidence" in result
        # Canonical-only fields should NOT be present
        assert "candidate_id" not in result
        assert "experience" not in result

    def test_deterministic_output(self):
        """Same inputs → same output (determinism requirement)."""
        result1 = run(
            csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
            ats=os.path.join(DATA_DIR, "sample_ats.json"),
        )
        result2 = run(
            csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
            ats=os.path.join(DATA_DIR, "sample_ats.json"),
        )
        assert result1["candidate_id"] == result2["candidate_id"]
        assert result1["full_name"] == result2["full_name"]
        assert result1["overall_confidence"] == result2["overall_confidence"]

    def test_output_file_written(self):
        """Pipeline writes output to file when --out specified."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmppath = f.name
        try:
            run(
                csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
                ats=os.path.join(DATA_DIR, "sample_ats.json"),
                output_file=tmppath,
            )
            with open(tmppath, encoding="utf-8") as f:
                data = json.load(f)
            assert data.get("full_name") is not None
        finally:
            os.unlink(tmppath)

    def test_malformed_ats_json_graceful(self):
        """Malformed ATS JSON should not crash the pipeline."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("{ invalid json !!!")
            tmppath = f.name
        try:
            result = run(
                csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
                ats=tmppath,
            )
            # Pipeline should continue using CSV only
            assert result.get("full_name") is not None
        finally:
            os.unlink(tmppath)

    def test_provenance_present_and_non_empty(self):
        """Every output must have non-empty provenance."""
        result = run(
            csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
            ats=os.path.join(DATA_DIR, "sample_ats.json"),
        )
        assert isinstance(result.get("provenance"), list)
        assert len(result["provenance"]) > 0

    def test_phones_are_e164(self):
        """All phones in canonical output must be E.164 format."""
        result = run(
            csv=os.path.join(DATA_DIR, "sample_candidate.csv"),
            ats=os.path.join(DATA_DIR, "sample_ats.json"),
        )
        for phone in result.get("phones", []):
            assert phone.startswith("+"), f"Phone not E.164: {phone}"
