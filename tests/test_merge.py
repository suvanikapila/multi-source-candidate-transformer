"""
test_merge.py — Unit tests for the merge / conflict-resolution engine.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.merge import merge, _pick_winner


def _make_record(source, priority, confidence, fields):
    return {
        "source": source,
        "source_priority": priority,
        "extraction_confidence": confidence,
        "fields": fields,
    }


class TestPickWinner:
    def test_higher_priority_wins(self):
        records = [
            _make_record("csv",    0.9,  0.95, {"full_name": "Alice Smith"}),
            _make_record("notes",  0.6,  0.55, {"full_name": "Alice S."}),
        ]
        provenance = []
        winner = _pick_winner("full_name", records, provenance)
        assert winner == "Alice Smith"

    def test_missing_field_skipped(self):
        records = [
            _make_record("csv",   0.9, 0.95, {}),
            _make_record("notes", 0.6, 0.55, {"full_name": "Bob"}),
        ]
        provenance = []
        winner = _pick_winner("full_name", records, provenance)
        assert winner == "Bob"

    def test_no_field_anywhere_returns_none(self):
        records = [
            _make_record("csv", 0.9, 0.95, {}),
        ]
        provenance = []
        winner = _pick_winner("full_name", records, provenance)
        assert winner is None

    def test_alternative_stored_in_provenance(self):
        records = [
            _make_record("csv",    0.9, 0.95, {"headline": "Engineer"}),
            _make_record("notes",  0.6, 0.55, {"headline": "Senior Eng"}),
        ]
        provenance = []
        _pick_winner("headline", records, provenance)
        fields_in_prov = [p["field"] for p in provenance]
        assert "headline[alt]" in fields_in_prov


class TestMerge:
    def test_merge_single_source(self):
        records = [
            _make_record("csv", 0.9, 0.95, {
                "full_name": "Alice Smith",
                "emails": ["alice@example.com"],
                "phones": ["+14155552671"],
            })
        ]
        result = merge(records)
        assert result["full_name"] == "Alice Smith"
        assert "alice@example.com" in result["emails"]

    def test_merge_two_sources_winner(self):
        """CSV should beat notes for full_name."""
        records = [
            _make_record("csv",   0.9, 0.95, {"full_name": "Alice Smith", "emails": ["alice@ex.com"]}),
            _make_record("notes", 0.6, 0.55, {"full_name": "Alice S.",    "emails": ["alice@ex.com"]}),
        ]
        result = merge(records)
        assert result["full_name"] == "Alice Smith"

    def test_emails_union(self):
        """Emails from both sources should be unioned."""
        records = [
            _make_record("csv",    0.9, 0.95, {"emails": ["a@ex.com"], "full_name": "X"}),
            _make_record("resume", 0.75, 0.7, {"emails": ["b@ex.com"], "full_name": "X"}),
        ]
        result = merge(records)
        assert "a@ex.com" in result["emails"]
        assert "b@ex.com" in result["emails"]

    def test_empty_records_returns_empty(self):
        result = merge([])
        assert result["candidate_id"] == "cand_unknown"
        assert result["emails"] == []

    def test_none_records_filtered(self):
        result = merge([None, None])
        assert result["candidate_id"] == "cand_unknown"

    def test_candidate_id_deterministic(self):
        records1 = [_make_record("csv", 0.9, 0.95, {"emails": ["test@ex.com"], "full_name": "Test"})]
        records2 = [_make_record("csv", 0.9, 0.95, {"emails": ["test@ex.com"], "full_name": "Test"})]
        assert merge(records1)["candidate_id"] == merge(records2)["candidate_id"]

    def test_provenance_populated(self):
        records = [
            _make_record("csv", 0.9, 0.95, {"full_name": "Alice", "emails": ["a@ex.com"]}),
        ]
        result = merge(records)
        assert len(result["provenance"]) > 0
        fields_in_prov = [p["field"] for p in result["provenance"]]
        assert "full_name" in fields_in_prov

    def test_skills_merged_across_sources(self):
        records = [
            _make_record("csv",    0.9,  0.95, {"emails": ["x@ex.com"], "full_name": "X",
                                                  "skills_raw": ["Python", "Docker"]}),
            _make_record("resume", 0.75, 0.70, {"emails": ["x@ex.com"], "full_name": "X",
                                                  "skills_raw": ["Kubernetes", "AWS"]}),
        ]
        result = merge(records)
        skill_names = [s["name"] for s in result["skills"]]
        assert "Python" in skill_names
        assert "Kubernetes" in skill_names

    def test_malformed_source_skipped(self):
        """None record should not crash the merge."""
        records = [
            None,
            _make_record("csv", 0.9, 0.95, {"full_name": "Bob", "emails": ["b@ex.com"]}),
        ]
        result = merge(records)
        assert result["full_name"] == "Bob"
