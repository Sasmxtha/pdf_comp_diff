"""Structural segmentation into clauses/sections."""

import hashlib
import logging
import re
from typing import Any

from specdiff.config import get_config
from specdiff.extract import ExtractedDocument, TextBlock
from specdiff.models import Segment

logger = logging.getLogger(__name__)


class SegmentedDocument:
    """Document split into hierarchical segments."""

    def __init__(self, segments: list[Segment], metadata: Any):
        self.segments = segments
        self.metadata = metadata
        self.metadata.clause_count = len([s for s in segments if s.clause_id])


def parse_clause_number(text: str) -> str | None:
    """
    Extract clause number from text using configured patterns.

    Returns clause_id like "1.2.3" or "A.1" or "Table 5" or None.
    """
    config = get_config()

    for pattern in config.segmentation.clause_patterns:
        match = re.match(pattern, text.strip(), re.IGNORECASE)
        if match:
            clause = match.group(0).strip()
            # Normalize spacing
            clause = re.sub(r"\s+", " ", clause)
            return clause

    return None


def extract_title(text: str, clause_id: str | None) -> str:
    """Extract title from text after removing clause number."""
    if clause_id:
        # Remove clause number from start of text
        text = text.strip()
        if text.startswith(clause_id):
            text = text[len(clause_id) :].strip()

    # Take first line or first N chars as title
    lines = text.split("\n")
    title = lines[0].strip() if lines else text[:100].strip()

    return title


def hash_text(text: str) -> str:
    """Generate short hash of text for efficient comparison."""
    return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def segment_document(doc: ExtractedDocument) -> SegmentedDocument:
    """
    Split document into clauses/sections based on numbering.

    Each segment maintains page range and position for change reporting.
    """
    logger.info("Segmenting document into clauses")

    segments: list[Segment] = []
    current_clause: str | None = None
    current_title: str = ""
    current_text: list[str] = []
    current_page_start: int = 0
    current_page_end: int = 0
    position: int = 0

    for block in doc.blocks:
        text = block["text"]
        page = block["page"]

        # Check if this block starts a new clause
        clause_id = parse_clause_number(text)

        if clause_id:
            # Save previous segment if exists
            if current_text:
                segment_text = "\n".join(current_text).strip()
                if segment_text:
                    segments.append(
                        Segment(
                            clause_id=current_clause,
                            title=current_title,
                            page_start=current_page_start,
                            page_end=current_page_end,
                            text=segment_text,
                            text_hash=hash_text(segment_text),
                            position=position,
                        )
                    )
                    position += 1

            # Start new segment
            current_clause = clause_id
            current_title = extract_title(text, clause_id)
            current_text = [text]
            current_page_start = page
            current_page_end = page

        else:
            # Continue current segment
            current_text.append(text)
            current_page_end = page

    # Save final segment
    if current_text:
        segment_text = "\n".join(current_text).strip()
        if segment_text:
            segments.append(
                Segment(
                    clause_id=current_clause,
                    title=current_title,
                    page_start=current_page_start,
                    page_end=current_page_end,
                    text=segment_text,
                    text_hash=hash_text(segment_text),
                    position=position,
                )
            )

    logger.info(f"Created {len(segments)} segments, {sum(1 for s in segments if s.clause_id)} with clause IDs")

    return SegmentedDocument(segments=segments, metadata=doc.metadata)
