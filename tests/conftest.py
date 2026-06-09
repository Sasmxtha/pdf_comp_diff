"""Pytest configuration and fixtures."""

import tempfile
from pathlib import Path

import fitz
import pytest


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def simple_pdf(temp_dir: Path) -> Path:
    """Create a simple test PDF."""
    pdf_path = temp_dir / "test.pdf"

    doc = fitz.open()
    page = doc.new_page()

    # Add title
    page.insert_text((72, 72), "Test Specification", fontsize=16)

    # Add clause 1
    page.insert_text((72, 120), "1 Introduction")
    page.insert_text((72, 150), "This is the introduction section with some text content.")

    # Add clause 1.1
    page.insert_text((72, 180), "1.1 Scope")
    page.insert_text((72, 210), "This document specifies requirements for testing.")

    doc.save(pdf_path)
    doc.close()

    return pdf_path


@pytest.fixture
def pdf_with_header_footer(temp_dir: Path) -> Path:
    """Create PDF with repeating headers and footers."""
    pdf_path = temp_dir / "test_header.pdf"

    doc = fitz.open()

    for page_num in range(3):
        page = doc.new_page()

        # Header (repeats on all pages)
        page.insert_text((72, 30), "ASTM Standard E123-45", fontsize=10)

        # Content (different on each page)
        page.insert_text((72, 100), f"Page {page_num + 1} content")
        page.insert_text((72, 130), f"This is unique text for page {page_num + 1}")

        # Footer (repeats on all pages)
        page.insert_text((72, 750), f"{page_num + 1}", fontsize=10)

    doc.save(pdf_path)
    doc.close()

    return pdf_path


@pytest.fixture
def pdf_pair_simple(temp_dir: Path) -> tuple[Path, Path]:
    """Create a pair of PDFs with simple changes."""
    # Old version
    old_pdf = temp_dir / "old.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "1 Introduction")
    page.insert_text((72, 100), "This is the original text.")
    page.insert_text((72, 130), "1.1 Scope")
    page.insert_text((72, 160), "Original scope statement.")
    doc.save(old_pdf)
    doc.close()

    # New version
    new_pdf = temp_dir / "new.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "1 Introduction")
    page.insert_text((72, 100), "This is the updated text with changes.")  # Modified
    page.insert_text((72, 130), "1.1 Scope")
    page.insert_text((72, 160), "Updated scope statement.")  # Modified
    page.insert_text((72, 190), "1.2 Definitions")  # Added
    page.insert_text((72, 220), "New definitions section.")
    doc.save(new_pdf)
    doc.close()

    return old_pdf, new_pdf


@pytest.fixture
def pdf_with_renumbering(temp_dir: Path) -> tuple[Path, Path]:
    """Create PDFs where clauses are renumbered."""
    # Old version
    old_pdf = temp_dir / "old_numbered.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "1 First Section")
    page.insert_text((72, 100), "Content of first section.")
    page.insert_text((72, 130), "2 Second Section")
    page.insert_text((72, 160), "Content of second section.")
    page.insert_text((72, 190), "3 Third Section")
    page.insert_text((72, 220), "Content of third section.")
    doc.save(old_pdf)
    doc.close()

    # New version - clause 2 removed, everything renumbered
    new_pdf = temp_dir / "new_numbered.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "1 First Section")
    page.insert_text((72, 100), "Content of first section.")
    # Clause 2 removed
    page.insert_text((72, 130), "2 Third Section")  # Was clause 3
    page.insert_text((72, 160), "Content of third section.")
    doc.save(new_pdf)
    doc.close()

    return old_pdf, new_pdf
