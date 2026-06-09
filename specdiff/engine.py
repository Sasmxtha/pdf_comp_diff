"""Main comparison engine orchestrating all components."""

import logging
from pathlib import Path

from specdiff.diffengine import DiffEngine
from specdiff.extract import extract_document
from specdiff.figures import detect_figure_changes
from specdiff.formparser import diff_part_reports, parse_part_report
from specdiff.models import ComparisonResult
from specdiff.report import assemble_result
from specdiff.segment import segment_document
from specdiff.tables import compare_tables

logger = logging.getLogger(__name__)

# Minimum clause count to consider a doc "spec-structured"
_MIN_CLAUSES_FOR_SPEC_MODE = 3


def compare_pdfs(old_pdf: Path, new_pdf: Path) -> ComparisonResult:
    """
    Compare two PDF specifications and return complete change list.

    Auto-detects document type:
    - Spec/standard with numbered clauses → hierarchical clause diff
    - Part report / BOM form → field-by-field form diff

    Returns deterministic, complete list of changes.
    """
    logger.info(f"Starting comparison: {old_pdf.name} vs {new_pdf.name}")

    # Step 1: Extract
    logger.info("Step 1/6: Extracting text from PDFs")
    old_doc = extract_document(old_pdf)
    new_doc = extract_document(new_pdf)

    # Step 2: Segment
    logger.info("Step 2/6: Segmenting documents into clauses")
    old_segmented = segment_document(old_doc)
    new_segmented = segment_document(new_doc)

    # Auto-detect: if neither doc has meaningful clauses, use form-aware diff
    old_clauses = sum(1 for s in old_segmented.segments if s.clause_id)
    new_clauses = sum(1 for s in new_segmented.segments if s.clause_id)
    use_form_mode = old_clauses < _MIN_CLAUSES_FOR_SPEC_MODE and new_clauses < _MIN_CLAUSES_FOR_SPEC_MODE

    if use_form_mode:
        logger.info("Detected form/BOM document — using field-level diff")
        text_changes = _form_diff(old_pdf, new_pdf)
    else:
        # Step 3: Hierarchical diff
        logger.info("Step 3/6: Performing hierarchical diff")
        diff_engine = DiffEngine()
        text_changes = diff_engine.compare(old_segmented.segments, new_segmented.segments)

    # Step 4: Table diff
    logger.info("Step 4/6: Comparing tables")
    table_changes, new_table_count = compare_tables(old_pdf, new_pdf)
    new_segmented.metadata.table_count = new_table_count

    # Step 5: Figure detection
    logger.info("Step 5/6: Detecting figure changes")
    figure_changes, manual_review_pages = detect_figure_changes(old_pdf, new_pdf)

    # Step 6: Assemble result
    logger.info("Step 6/6: Assembling final result")
    result = assemble_result(
        old_metadata=old_segmented.metadata,
        new_metadata=new_segmented.metadata,
        text_changes=text_changes,
        table_changes=table_changes,
        figure_changes=figure_changes,
        manual_review_pages=manual_review_pages,
    )

    logger.info(
        f"Comparison complete: {len(result.changes)} changes, "
        f"{len(result.manual_review_pages)} pages need manual review"
    )

    return result


def _form_diff(old_pdf: Path, new_pdf: Path) -> list:
    """Parse both PDFs as structured part reports and diff field-by-field."""
    old_report = parse_part_report(old_pdf)
    new_report = parse_part_report(new_pdf)
    return diff_part_reports(old_report, new_report)
