"""Tests for structural segmentation."""

from pathlib import Path

from specdiff.extract import extract_document
from specdiff.segment import extract_title, parse_clause_number, segment_document


def test_parse_clause_number():
    """Test clause number extraction."""
    assert parse_clause_number("1 Introduction") == "1"
    assert parse_clause_number("1.2.3 Requirements") == "1.2.3"
    assert parse_clause_number("A.1 Annex Section") == "A.1"
    assert parse_clause_number("Annex B Normative References") == "Annex B"
    assert parse_clause_number("Table 5 Test Results") == "Table 5"
    assert parse_clause_number("Figure 3 Diagram") == "Figure 3"
    assert parse_clause_number("No clause number here") is None


def test_extract_title():
    """Test title extraction."""
    title = extract_title("1 Introduction to the Standard", "1")
    assert "Introduction" in title
    assert "1" not in title

    title = extract_title("Some text without clause", None)
    assert "Some text" in title


def test_segment_document(simple_pdf: Path):
    """Test document segmentation."""
    doc = extract_document(simple_pdf)
    segmented = segment_document(doc)

    assert len(segmented.segments) > 0

    # Should find clause-numbered segments
    clause_segments = [s for s in segmented.segments if s.clause_id]
    assert len(clause_segments) > 0

    # Check metadata updated
    assert segmented.metadata.clause_count > 0

    # Check segments have required fields
    for segment in segmented.segments:
        assert segment.page_start >= 0
        assert segment.page_end >= segment.page_start
        assert segment.text
        assert segment.text_hash
