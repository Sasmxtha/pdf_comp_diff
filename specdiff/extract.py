"""Text extraction with header/footer removal."""

import hashlib
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from specdiff.config import get_config
from specdiff.models import DocumentMetadata

logger = logging.getLogger(__name__)


class TextBlock(dict[str, Any]):
    """Text block with position and content."""

    def __init__(
        self,
        text: str,
        page: int,
        bbox: tuple[float, float, float, float],
        block_no: int,
    ):
        super().__init__(
            text=text,
            page=page,
            bbox=bbox,
            block_no=block_no,
            y_band=(bbox[1], bbox[3]),  # top, bottom
        )


class ExtractedDocument:
    """Extracted and cleaned document with position mapping."""

    def __init__(
        self,
        blocks: list[TextBlock],
        metadata: DocumentMetadata,
        page_dimensions: list[tuple[float, float]],
    ):
        self.blocks = blocks
        self.metadata = metadata
        self.page_dimensions = page_dimensions


def compute_file_hash(pdf_path: Path) -> str:
    """Compute SHA256 hash of PDF file."""
    hasher = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_headers_footers(
    blocks: list[TextBlock], page_count: int
) -> tuple[set[str], set[str]]:
    """Detect repeating headers and footers across pages."""
    config = get_config()
    threshold = config.extraction.repetition_threshold

    # Group text by y-band across pages
    top_texts: defaultdict[str, list[int]] = defaultdict(list)
    bottom_texts: defaultdict[str, list[int]] = defaultdict(list)

    for block in blocks:
        text = block["text"].strip()
        if not text or len(text) > 200:  # Skip very long blocks
            continue

        page = block["page"]
        y_top, y_bottom = block["y_band"]

        # Normalize y position relative to page height
        # (assuming all pages roughly same height - check first page)
        if y_top < 100:  # Top margin (points)
            top_texts[text].append(page)
        elif y_bottom > 700:  # Bottom margin (points, typical letter ~792)
            bottom_texts[text].append(page)

    # Find texts that appear on many pages
    headers: set[str] = set()
    footers: set[str] = set()

    for text, pages in top_texts.items():
        if len(set(pages)) >= threshold:
            headers.add(text)
            logger.debug(f"Detected header: {text[:50]}... on {len(pages)} pages")

    for text, pages in bottom_texts.items():
        if len(set(pages)) >= threshold:
            footers.add(text)
            logger.debug(f"Detected footer: {text[:50]}... on {len(pages)} pages")

    # Also detect standalone page numbers
    page_num_pattern = re.compile(r"^\s*\d+\s*$")
    for block in blocks:
        text = block["text"].strip()
        if page_num_pattern.match(text):
            footers.add(text)

    return headers, footers


def extract_text_blocks(pdf_path: Path) -> list[TextBlock]:
    """Extract text blocks with position info from PDF."""
    blocks: list[TextBlock] = []

    try:
        doc = fitz.open(pdf_path)
        logger.info(f"Opened PDF: {pdf_path.name} ({len(doc)} pages)")

        for page_num, page in enumerate(doc):
            # Get text blocks with position
            text_dict = page.get_text("dict")
            block_no = 0

            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    text_lines = []
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text_lines.append(span.get("text", ""))

                    text = " ".join(text_lines).strip()
                    if text:
                        bbox = tuple(block["bbox"])  # type: ignore[arg-type]
                        blocks.append(
                            TextBlock(
                                text=text,
                                page=page_num,
                                bbox=bbox,  # type: ignore[arg-type]
                                block_no=block_no,
                            )
                        )
                        block_no += 1

        doc.close()
        logger.info(f"Extracted {len(blocks)} text blocks")
        return blocks

    except Exception as e:
        logger.error(f"Failed to extract text from {pdf_path}: {e}")
        raise


def remove_headers_footers(
    blocks: list[TextBlock], headers: set[str], footers: set[str]
) -> list[TextBlock]:
    """Remove detected headers and footers from blocks."""
    cleaned: list[TextBlock] = []

    for block in blocks:
        text = block["text"].strip()
        if text not in headers and text not in footers:
            cleaned.append(block)

    removed = len(blocks) - len(cleaned)
    logger.info(f"Removed {removed} header/footer blocks")
    return cleaned


def extract_document(pdf_path: Path) -> ExtractedDocument:
    """
    Extract text from PDF with header/footer cleanup.

    Returns document with positional mapping for change location.
    """
    logger.info(f"Extracting document: {pdf_path}")

    # Extract all text blocks
    blocks = extract_text_blocks(pdf_path)

    # Open again to get metadata
    doc = fitz.open(pdf_path)
    page_count = len(doc)

    # Get page dimensions
    page_dimensions = [(page.rect.width, page.rect.height) for page in doc]

    # Count figures
    figure_count = 0
    for page in doc:
        figure_count += len(page.get_images())

    doc.close()

    # Detect and remove headers/footers
    headers, footers = detect_headers_footers(blocks, page_count)
    cleaned_blocks = remove_headers_footers(blocks, headers, footers)

    # Compute file hash
    file_hash = compute_file_hash(pdf_path)

    # Create metadata
    metadata = DocumentMetadata(
        page_count=page_count,
        clause_count=0,  # Will be updated during segmentation
        table_count=0,  # Will be updated during table extraction
        figure_count=figure_count,
        file_hash=file_hash,
    )

    logger.info(
        f"Extraction complete: {page_count} pages, "
        f"{len(cleaned_blocks)} blocks, {figure_count} figures"
    )

    return ExtractedDocument(
        blocks=cleaned_blocks,
        metadata=metadata,
        page_dimensions=page_dimensions,
    )
