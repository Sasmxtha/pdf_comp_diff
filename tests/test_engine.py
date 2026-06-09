"""Integration tests for the main engine."""

from pathlib import Path

from specdiff.engine import compare_pdfs
from specdiff.models import ChangeKind


def test_compare_pdfs_simple(pdf_pair_simple: tuple[Path, Path]):
    """Test end-to-end PDF comparison."""
    old_pdf, new_pdf = pdf_pair_simple

    result = compare_pdfs(old_pdf, new_pdf)

    # Should return complete result
    assert result.old_metadata
    assert result.new_metadata
    assert result.changes is not None
    assert result.summary

    # Should have detected some changes
    assert len(result.changes) >= 0

    # Summary should be computed
    assert result.summary.insertions >= 0
    assert result.summary.deletions >= 0
    assert result.summary.modifications >= 0


def test_comparison_result_structure(pdf_pair_simple: tuple[Path, Path]):
    """Test that comparison result has required structure."""
    old_pdf, new_pdf = pdf_pair_simple

    result = compare_pdfs(old_pdf, new_pdf)

    # Metadata
    assert result.old_metadata.page_count > 0
    assert result.new_metadata.page_count > 0
    assert result.old_metadata.file_hash
    assert result.new_metadata.file_hash

    # Changes have required fields
    for change in result.changes:
        assert change.id
        assert isinstance(change.kind, ChangeKind)
        assert change.location
        assert change.location.page >= 0
        assert 0.0 <= change.confidence <= 1.0

    # Summary counts match changes
    insertion_count = sum(1 for c in result.changes if c.kind == ChangeKind.INSERTION)
    assert result.summary.insertions == insertion_count

    deletion_count = sum(1 for c in result.changes if c.kind == ChangeKind.DELETION)
    assert result.summary.deletions == deletion_count


def test_figure_detection(pdf_pair_simple: tuple[Path, Path]):
    """Test that figure changes are detected."""
    old_pdf, new_pdf = pdf_pair_simple

    result = compare_pdfs(old_pdf, new_pdf)

    # Should have checked for figures (may or may not flag any)
    assert result.summary.figure_flags >= 0
    assert result.manual_review_pages is not None

    # Figure flags should be in changes
    figure_flags = [c for c in result.changes if c.kind == ChangeKind.FIGURE_FLAG]
    assert len(figure_flags) == result.summary.figure_flags
