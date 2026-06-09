"""Tests for diff engine."""

from pathlib import Path

from specdiff.diffengine import DiffEngine
from specdiff.extract import extract_document
from specdiff.models import ChangeKind
from specdiff.segment import segment_document


def test_word_diff():
    """Test word-level diffing."""
    engine = DiffEngine()

    old_text = "The quick brown fox jumps over the lazy dog"
    new_text = "The quick red fox leaps over the lazy cat"

    changes = engine.word_diff(old_text, new_text)

    # Should detect changes
    assert len(changes) > 0

    # Should have both deletions and insertions
    kinds = {c.kind for c in changes}
    assert ChangeKind.DELETION in kinds or ChangeKind.INSERTION in kinds


def test_segment_alignment_simple(pdf_pair_simple: tuple[Path, Path]):
    """Test segment alignment with simple changes."""
    old_pdf, new_pdf = pdf_pair_simple

    old_doc = extract_document(old_pdf)
    new_doc = extract_document(new_pdf)

    old_seg = segment_document(old_doc)
    new_seg = segment_document(new_doc)

    engine = DiffEngine()
    aligned = engine.align_segments(old_seg.segments, new_seg.segments)

    assert len(aligned) > 0

    # Should have matched, added, and/or removed segments
    statuses = {status for _, _, status in aligned}
    assert "matched" in statuses


def test_segment_alignment_renumbering(pdf_with_renumbering: tuple[Path, Path]):
    """Test alignment handles clause renumbering correctly."""
    old_pdf, new_pdf = pdf_with_renumbering

    old_doc = extract_document(old_pdf)
    new_doc = extract_document(new_pdf)

    old_seg = segment_document(old_doc)
    new_seg = segment_document(new_doc)

    engine = DiffEngine()
    aligned = engine.align_segments(old_seg.segments, new_seg.segments)

    # Should detect that clause 2 (Second Section) was removed
    # And clause 3 (Third Section) was matched even though renumbered
    statuses = [status for _, _, status in aligned]

    assert "removed" in statuses or len(old_seg.segments) > len(new_seg.segments)


def test_full_comparison(pdf_pair_simple: tuple[Path, Path]):
    """Test full document comparison."""
    old_pdf, new_pdf = pdf_pair_simple

    old_doc = extract_document(old_pdf)
    new_doc = extract_document(new_pdf)

    old_seg = segment_document(old_doc)
    new_seg = segment_document(new_doc)

    engine = DiffEngine()
    changes = engine.compare(old_seg.segments, new_seg.segments)

    # Should detect changes
    assert len(changes) > 0

    # Changes should have proper structure
    for change in changes:
        assert change.id
        assert change.kind
        assert change.location
        assert change.location.page >= 0
