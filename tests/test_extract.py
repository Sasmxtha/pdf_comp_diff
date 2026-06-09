"""Tests for text extraction and header/footer removal."""

from pathlib import Path

from specdiff.extract import (
    detect_headers_footers,
    extract_document,
    extract_text_blocks,
    remove_headers_footers,
)


def test_extract_text_blocks(simple_pdf: Path):
    """Test basic text extraction."""
    blocks = extract_text_blocks(simple_pdf)

    assert len(blocks) > 0
    assert all("text" in block for block in blocks)
    assert all("page" in block for block in blocks)
    assert all("bbox" in block for block in blocks)

    # Check we extracted the expected content
    all_text = " ".join(block["text"] for block in blocks)
    assert "Introduction" in all_text
    assert "Scope" in all_text


def test_detect_headers_footers(pdf_with_header_footer: Path):
    """Test header and footer detection."""
    blocks = extract_text_blocks(pdf_with_header_footer)

    headers, footers = detect_headers_footers(blocks, page_count=3)

    # Should detect the repeating header
    assert any("ASTM" in h for h in headers)

    # Should detect page numbers as footers
    assert len(footers) > 0


def test_remove_headers_footers(pdf_with_header_footer: Path):
    """Test removal of headers and footers."""
    blocks = extract_text_blocks(pdf_with_header_footer)
    initial_count = len(blocks)

    headers, footers = detect_headers_footers(blocks, page_count=3)
    cleaned = remove_headers_footers(blocks, headers, footers)

    # Should have removed some blocks
    assert len(cleaned) < initial_count

    # Unique content should remain
    cleaned_text = " ".join(block["text"] for block in cleaned)
    assert "Page 1 content" in cleaned_text or "Page 2 content" in cleaned_text


def test_extract_document(simple_pdf: Path):
    """Test full document extraction."""
    doc = extract_document(simple_pdf)

    assert doc.metadata.page_count == 1
    assert len(doc.blocks) > 0
    assert doc.metadata.file_hash
    assert len(doc.page_dimensions) == 1
